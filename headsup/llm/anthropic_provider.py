"""Anthropic connector, using the SDK's typed structured-output helper."""

from __future__ import annotations

import logging
import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from headsup.llm.base import LLMError

log = logging.getLogger("headsup.llm")

T = TypeVar("T", bound=BaseModel)

_PROVIDER = "anthropic"


def _tokens(response: Any) -> tuple[object, object]:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    return (
        input_tokens if isinstance(input_tokens, int) else "?",
        output_tokens if isinstance(output_tokens, int) else "?",
    )


def _log_call(model: str, operation: str, started: float, response: Any) -> None:
    input_tokens, output_tokens = _tokens(response)
    log.info(
        "llm provider=%s model=%s operation=%s latency_ms=%d input_tokens=%s output_tokens=%s",
        _PROVIDER,
        model,
        operation,
        int((time.perf_counter() - started) * 1000),
        input_tokens,
        output_tokens,
    )


def _check_stop_reason(response: Any) -> None:
    reason = getattr(response, "stop_reason", None)
    if reason == "refusal":
        raise LLMError("The model declined to answer.")
    if reason == "max_tokens":
        raise LLMError("The model's answer was cut off.")


class AnthropicLLM:
    """Talks to the Anthropic Messages API."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        effort: str | None = None,
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.name = f"{_PROVIDER}:{model}"
        self.client = (
            client if client is not None else anthropic.Anthropic(api_key=api_key, timeout=30.0)
        )

    def extract(self, system: str, user: str, schema: type[T]) -> T:
        """Fill ``schema`` from one message, letting the SDK validate the shape."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_format": schema,
        }
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        started = time.perf_counter()
        try:
            response = self.client.messages.parse(**kwargs)
        except anthropic.RateLimitError as exc:
            raise LLMError("The AI service is busy. Try again in a minute.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Couldn't reach the AI service. Check the internet connection.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"The AI service returned an error ({exc.status_code}).") from exc
        except ValueError as exc:
            # parse() validates the JSON itself, so a cut-off or refused answer
            # raises pydantic's ValidationError here, before stop_reason is seen.
            raise LLMError("The model's answer didn't match the expected format.") from exc
        _log_call(self.model, "extract", started, response)
        _check_stop_reason(response)
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("The model didn't return a usable answer.")
        return parsed

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        """Answer a conversation as plain text."""
        started = time.perf_counter()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=messages,
            )
        except anthropic.RateLimitError as exc:
            raise LLMError("The AI service is busy. Try again in a minute.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Couldn't reach the AI service. Check the internet connection.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"The AI service returned an error ({exc.status_code}).") from exc
        _log_call(self.model, "chat", started, response)
        _check_stop_reason(response)
        return "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
