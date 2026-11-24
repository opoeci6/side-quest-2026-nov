"""The small surface the rest of Heads-Up needs from a language model."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Any failure talking to a model. The message is short and safe to show."""


class LLMConfigError(LLMError):
    """A missing key or an unknown provider. The message says what to set."""


class LLM(Protocol):
    """One structured call and one free-text call, nothing else."""

    name: str

    def extract(self, system: str, user: str, schema: type[T]) -> T:
        """Fill ``schema`` from ``user``, with ``system`` as the instructions."""
        ...

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        """Answer a conversation, oldest message first."""
        ...
