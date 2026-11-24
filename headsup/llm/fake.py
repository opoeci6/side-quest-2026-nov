"""A scripted LLM for tests, the demo and anything that must not call a model."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from headsup.llm.base import LLMError
from headsup.models import LLMDeadline, LLMPlanChange, LLMTriage

T = TypeVar("T", bound=BaseModel)

ExtractHandler = Callable[[str, str, type[BaseModel]], Any]
ExtractPairs = list[tuple[str, Any]]
ChatHandler = Callable[[str, list[dict[str, str]]], str]


def _pick(script: list[tuple[str, Any]], user: str) -> Any:
    fallback = None
    for substring, response in script:
        if substring == "":
            if fallback is None:
                fallback = response
        elif substring in user:
            return response
    if fallback is not None:
        return fallback
    raise LLMError("FakeLLM: no scripted response")


def _as_model(response: Any, schema: type[T]) -> T:
    if isinstance(response, Exception):
        raise response
    if isinstance(response, BaseModel):
        return response
    return schema.model_validate(response)


class FakeLLM:
    """An LLM whose answers come from a script, and which remembers every call."""

    def __init__(
        self,
        extract: ExtractHandler | ExtractPairs | None = None,
        chat: ChatHandler | str | None = None,
        name: str = "fake",
    ) -> None:
        self.name = name
        self.calls: list[tuple[str, str, object]] = []
        self._extract = extract
        self._chat = chat

    def extract(self, system: str, user: str, schema: type[T]) -> T:
        """Return the scripted answer for ``user``, validated into ``schema``."""
        self.calls.append(("extract", system, user))
        script = self._extract
        if script is None:
            raise LLMError("FakeLLM has no extract response")
        if callable(script):
            response = script(system, user, schema)
        else:
            response = _pick(script, user)
        return _as_model(response, schema)

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        """Return the scripted chat answer, or a note that none was scripted."""
        self.calls.append(("chat", system, messages))
        script = self._chat
        if script is None:
            return "(fake) no answer scripted"
        if callable(script):
            return script(system, messages)
        return script


_DEMO_CHAT = "(Demo mode) Connect a real AI model in .env to get answers about your week."

_DEMO_EXTRACTS: list[tuple[str, LLMTriage]] = [
    (
        "Mom can you get Ava at 2:30 tomorrow",
        LLMTriage(
            category="plan_change",
            summary=(
                "Michelle asks you to pick up Ava at 2:30 tomorrow instead of 3:15, "
                "because of an early dismissal."
            ),
            plan_changes=[
                LLMPlanChange(
                    event_id="ev-ava",
                    title="Pick up Ava",
                    date="2026-10-22",
                    new_start="14:30",
                    new_end=None,
                )
            ],
            deadlines=[],
            looks_like_scam=False,
            scam_reasons=[],
        ),
    ),
    (
        "CanadaPost FINAL NOTICE",
        LLMTriage(
            category="scam",
            summary="A text pretending to be Canada Post asks you to pay a fee through a link.",
            plan_changes=[],
            deadlines=[],
            looks_like_scam=True,
            scam_reasons=["Canada Post doesn't ask for fees by text."],
        ),
    ),
    (
        "3rd reminder: Your prescription is ready",
        LLMTriage(
            category="deadline",
            summary="Your prescription at Harbourview must be picked up by Friday, October 23.",
            plan_changes=[],
            deadlines=[
                LLMDeadline(
                    reminder_id="r-prescription",
                    title="Pick up prescription Harbourview",
                    due_date="2026-10-23",
                    due_time=None,
                )
            ],
            looks_like_scam=False,
            scam_reasons=[],
        ),
    ),
    (
        "School called, Ava's waiting at the office",
        LLMTriage(
            category="info",
            summary="Michelle says the school called because Ava is waiting at the office.",
            plan_changes=[],
            deadlines=[],
            looks_like_scam=False,
            scam_reasons=[],
        ),
    ),
    (
        "Thanks for grabbing her",
        LLMTriage(
            category="social",
            summary="Michelle says thanks for picking up Ava.",
            plan_changes=[],
            deadlines=[],
            looks_like_scam=False,
            scam_reasons=[],
        ),
    ),
    (
        "",
        LLMTriage(
            category="other",
            summary="Nothing for you to do.",
            plan_changes=[],
            deadlines=[],
            looks_like_scam=False,
            scam_reasons=[],
        ),
    ),
]


def demo_fake() -> FakeLLM:
    """Return a fake with canned answers for the persona's texts, so no key is needed."""
    return FakeLLM(extract=_DEMO_EXTRACTS, chat=_DEMO_CHAT, name="fake:demo")
