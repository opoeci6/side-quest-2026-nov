"""Choosing the language-model connector the app talks to."""

from __future__ import annotations

import os
from collections.abc import Mapping

from headsup.llm.anthropic_provider import AnthropicLLM
from headsup.llm.base import LLM, LLMConfigError, LLMError
from headsup.llm.fake import demo_fake
from headsup.llm.openai_provider import OpenAICompatLLM

__all__ = ["LLM", "LLMError", "LLMConfigError", "get_llm"]

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"
_EFFORTS = ("low", "medium", "high")


def _anthropic(env: Mapping[str, str]) -> LLM:
    api_key = (env.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise LLMConfigError("Set ANTHROPIC_API_KEY in .env (see docs/dev-setup.md).")
    model = (env.get("LLM_MODEL") or "").strip() or DEFAULT_ANTHROPIC_MODEL
    effort = (env.get("LLM_EFFORT") or "").strip()
    if effort and effort not in _EFFORTS:
        raise LLMConfigError(f"Unknown LLM_EFFORT '{effort}'. Use low, medium or high.")
    return AnthropicLLM(model=model, api_key=api_key, effort=effort or None)


def _openai(env: Mapping[str, str]) -> LLM:
    model = (env.get("LLM_MODEL") or "").strip()
    if not model:
        raise LLMConfigError("Set LLM_MODEL in .env (see docs/dev-setup.md).")
    api_key = (env.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise LLMConfigError("Set OPENAI_API_KEY in .env (see docs/dev-setup.md).")
    base_url = (env.get("LLM_BASE_URL") or "").strip() or None
    return OpenAICompatLLM(model=model, api_key=api_key, base_url=base_url)


def get_llm(env: Mapping[str, str] | None = None) -> LLM:
    """Build the connector named by ``LLM_PROVIDER``, which defaults to anthropic."""
    source = os.environ if env is None else env
    requested = (source.get("LLM_PROVIDER") or "").strip()
    provider = requested.lower() or "anthropic"
    if provider == "fake":
        return demo_fake()
    if provider == "anthropic":
        return _anthropic(source)
    if provider == "openai":
        return _openai(source)
    raise LLMConfigError(
        f"Unknown LLM_PROVIDER '{requested}'. Use anthropic, openai or fake."
    )
