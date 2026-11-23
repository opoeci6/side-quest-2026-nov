"""OpenAI-compatible connector, for OpenAI and any server that speaks its API."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar
from urllib.parse import urlparse

import openai
from pydantic import BaseModel, ValidationError

from headsup.llm.base import LLMError

log = logging.getLogger("headsup.llm")

T = TypeVar("T", bound=BaseModel)

_PROVIDER = "openai"


def _tokens(response: Any) -> tuple[object, object]:
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    return (
        prompt_tokens if isinstance(prompt_tokens, int) else "?",
        completion_tokens if isinstance(completion_tokens, int) else "?",
    )


def _log_call(model: str, operation: str, started: float, response: Any) -> None:
    prompt_tokens, completion_tokens = _tokens(response)
    log.info(
        "llm provider=%s model=%s operation=%s latency_ms=%d input_tokens=%s output_tokens=%s",
        _PROVIDER,
        model,
        operation,
        int((time.perf_counter() - started) * 1000),
        prompt_tokens,
        completion_tokens,
    )


def _content(response: Any) -> str:
    return response.choices[0].message.content or ""


def _check_finish_reason(response: Any) -> None:
    choices = getattr(response, "choices", None) or []
    if choices and getattr(choices[0], "finish_reason", None) == "length":
        raise LLMError("The model's answer was cut off.")


def _schema_prompt(system: str, schema: type[BaseModel]) -> str:
    return (
        system
        + "\n\nReply with only a JSON object that matches this JSON schema:\n"
        + json.dumps(schema.model_json_schema())
    )


class OpenAICompatLLM:
    """Talks to any chat-completions endpoint that accepts a JSON response format."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.name = f"{_PROVIDER}:{model}"
        if base_url:
            self.name = f"{self.name}@{urlparse(base_url).netloc}"
        self.client = (
            client
            if client is not None
            else openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=30.0)
        )

    def _complete(
        self, messages: list[dict[str, str]], operation: str, json_mode: bool
    ) -> Any:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except openai.RateLimitError as exc:
            raise LLMError("The AI service is busy. Try again in a minute.") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Couldn't reach the AI service. Check the internet connection.") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"The AI service returned an error ({exc.status_code}).") from exc
        _log_call(self.model, operation, started, response)
        return response

    def extract(self, system: str, user: str, schema: type[T]) -> T:
        """Fill ``schema`` from one message, retrying once if the JSON is unusable."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _schema_prompt(system, schema)},
            {"role": "user", "content": user},
        ]
        response = self._complete(messages, "extract", json_mode=True)
        _check_finish_reason(response)
        content = _content(response)
        try:
            return schema.model_validate_json(content)
        except (ValidationError, ValueError) as exc:
            retry_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"That was not valid: {str(exc)[:300]}. "
                        "Reply again with only the JSON object."
                    ),
                },
            ]
            retry = self._complete(retry_messages, "extract", json_mode=True)
            _check_finish_reason(retry)
            try:
                return schema.model_validate_json(_content(retry))
            except (ValidationError, ValueError) as retry_exc:
                raise LLMError(
                    "The model's answer didn't match the expected format."
                ) from retry_exc

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        """Answer a conversation as plain text."""
        response = self._complete(
            [{"role": "system", "content": system}, *messages], "chat", json_mode=False
        )
        return _content(response).strip()
