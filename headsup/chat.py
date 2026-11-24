"""Read-only questions about Gloria's week."""

from __future__ import annotations

from datetime import datetime

from headsup.llm.base import LLM
from headsup.models import AppState
from headsup.prompts import build_chat_system

EMPTY_QUESTION_REPLY = "Please type a question."

_HISTORY_LIMIT = 6


def answer(
    question: str,
    history: list[dict[str, str]],
    state: AppState,
    now: datetime,
    llm: LLM,
) -> str:
    """Answer one question from the calendar and texts. Changes nothing."""
    text = question.strip()
    if not text:
        return EMPTY_QUESTION_REPLY
    recent = list(history[-_HISTORY_LIMIT:])
    while recent and recent[0].get("role") != "user":
        recent.pop(0)
    messages = [
        {"role": item["role"], "content": item["content"]} for item in recent
    ]
    messages.append({"role": "user", "content": text})
    return llm.chat(build_chat_system(state, now), messages)
