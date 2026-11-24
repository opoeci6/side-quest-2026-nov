"""Provider selection, both SDK connectors and the fake, all without a network."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import openai
import pytest
from pydantic import BaseModel

from headsup.llm import LLMConfigError, LLMError, get_llm
from headsup.llm.anthropic_provider import AnthropicLLM
from headsup.llm.fake import FakeLLM, demo_fake
from headsup.llm.openai_provider import OpenAICompatLLM
from headsup.models import LLMDeadline, LLMPlanChange, LLMTriage

KEY = "test-key-123"
REQUEST = httpx2.Request("POST", "https://example.invalid")


class Answer(BaseModel):
    text: str


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _http_error(module, kind: str) -> Exception:
    if kind == "rate_limit":
        return module.RateLimitError(
            "busy", response=httpx2.Response(429, request=REQUEST), body=None
        )
    if kind == "connection":
        return module.APIConnectionError(request=REQUEST)
    return module.APIStatusError(
        "bad", response=httpx2.Response(500, request=REQUEST), body=None
    )


def _anthropic_response(
    parsed: object = None,
    stop_reason: str = "end_turn",
    blocks: list[SimpleNamespace] | None = None,
) -> MagicMock:
    response = MagicMock()
    response.parsed_output = parsed
    response.stop_reason = stop_reason
    response.content = blocks or []
    response.usage = SimpleNamespace(input_tokens=11, output_tokens=22)
    return response


def _anthropic_client(response: MagicMock | None = None) -> MagicMock:
    client = MagicMock()
    if response is not None:
        client.messages.parse.return_value = response
        client.messages.create.return_value = response
    return client


def _openai_response(content: str | None, finish_reason: str = "stop") -> MagicMock:
    response = MagicMock()
    response.choices = [
        SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(content=content),
        )
    ]
    response.usage = SimpleNamespace(prompt_tokens=5, completion_tokens=7)
    return response


def _openai_client(*responses: MagicMock) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.side_effect = list(responses)
    return client


# --------------------------------------------------------------------------
# get_llm
# --------------------------------------------------------------------------


def test_get_llm_defaults_to_anthropic() -> None:
    llm = get_llm({"ANTHROPIC_API_KEY": KEY})
    assert isinstance(llm, AnthropicLLM)
    assert llm.name == "anthropic:claude-haiku-5-5"


def test_get_llm_default_without_a_key_raises() -> None:
    with pytest.raises(LLMConfigError) as info:
        get_llm({})
    assert "ANTHROPIC_API_KEY" in str(info.value)


def test_get_llm_uses_an_explicit_model_and_effort() -> None:
    llm = get_llm({"ANTHROPIC_API_KEY": KEY, "LLM_MODEL": "claude-sonnet-5", "LLM_EFFORT": "low"})
    assert isinstance(llm, AnthropicLLM)
    assert llm.name == "anthropic:claude-sonnet-5"
    assert llm.effort == "low"


def test_get_llm_provider_is_case_insensitive() -> None:
    llm = get_llm({"LLM_PROVIDER": "Anthropic", "ANTHROPIC_API_KEY": KEY})
    assert llm.name == "anthropic:claude-haiku-5-5"


def test_get_llm_empty_provider_means_anthropic() -> None:
    llm = get_llm({"LLM_PROVIDER": "", "ANTHROPIC_API_KEY": KEY})
    assert isinstance(llm, AnthropicLLM)


def test_get_llm_passes_the_key_from_the_mapping() -> None:
    llm = get_llm({"ANTHROPIC_API_KEY": KEY})
    assert isinstance(llm, AnthropicLLM)
    assert llm.client.api_key == KEY


def test_get_llm_unknown_provider_raises() -> None:
    with pytest.raises(LLMConfigError) as info:
        get_llm({"LLM_PROVIDER": "azure"})
    assert str(info.value) == "Unknown LLM_PROVIDER 'azure'. Use anthropic, openai or fake."


def test_get_llm_rejects_an_unknown_effort() -> None:
    with pytest.raises(LLMConfigError) as info:
        get_llm({"ANTHROPIC_API_KEY": KEY, "LLM_EFFORT": "turbo"})
    assert "LLM_EFFORT" in str(info.value)


def test_get_llm_openai_needs_a_model() -> None:
    with pytest.raises(LLMConfigError) as info:
        get_llm({"LLM_PROVIDER": "openai", "OPENAI_API_KEY": KEY})
    assert str(info.value) == "Set LLM_MODEL in .env (see docs/dev-setup.md)."


def test_get_llm_openai_needs_a_key() -> None:
    with pytest.raises(LLMConfigError) as info:
        get_llm({"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o-mini"})
    assert str(info.value) == "Set OPENAI_API_KEY in .env (see docs/dev-setup.md)."


def test_get_llm_openai_with_a_base_url() -> None:
    llm = get_llm(
        {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "deepseek-chat",
            "OPENAI_API_KEY": KEY,
            "LLM_BASE_URL": "https://api.example.com/v1",
        }
    )
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.name == "openai:deepseek-chat@api.example.com"


def test_get_llm_openai_without_a_base_url() -> None:
    llm = get_llm({"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o-mini", "OPENAI_API_KEY": KEY})
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.name == "openai:gpt-4o-mini"


def test_get_llm_openai_ignores_effort() -> None:
    llm = get_llm(
        {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o-mini",
            "OPENAI_API_KEY": KEY,
            "LLM_EFFORT": "turbo",
        }
    )
    assert isinstance(llm, OpenAICompatLLM)


def test_get_llm_fake() -> None:
    llm = get_llm({"LLM_PROVIDER": "fake"})
    assert isinstance(llm, FakeLLM)
    assert llm.name == "fake:demo"


def test_get_llm_reads_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert get_llm().name == "fake:demo"


# --------------------------------------------------------------------------
# AnthropicLLM.extract
# --------------------------------------------------------------------------


def test_anthropic_extract_returns_the_parsed_output() -> None:
    client = _anthropic_client(_anthropic_response(Answer(text="hello")))
    llm = AnthropicLLM("claude-haiku-5-5", api_key=KEY, client=client)
    assert llm.extract("SYS", "USER", Answer) == Answer(text="hello")


def test_anthropic_extract_passes_the_schema_and_prompt() -> None:
    client = _anthropic_client(_anthropic_response(Answer(text="hello")))
    llm = AnthropicLLM("claude-haiku-5-5", client=client)
    llm.extract("SYS", "USER", Answer)
    kwargs = client.messages.parse.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-5-5"
    assert kwargs["max_tokens"] == 2048
    assert kwargs["system"] == "SYS"
    assert kwargs["messages"] == [{"role": "user", "content": "USER"}]
    assert kwargs["output_format"] is Answer
    assert "output_config" not in kwargs


def test_anthropic_extract_sends_effort_only_when_set() -> None:
    client = _anthropic_client(_anthropic_response(Answer(text="hello")))
    llm = AnthropicLLM("m", effort="medium", client=client)
    llm.extract("SYS", "USER", Answer)
    assert client.messages.parse.call_args.kwargs["output_config"] == {"effort": "medium"}


@pytest.mark.parametrize(
    ("stop_reason", "message"),
    [
        ("refusal", "The model declined to answer."),
        ("max_tokens", "The model's answer was cut off."),
    ],
)
def test_anthropic_extract_rejects_bad_stop_reasons(stop_reason: str, message: str) -> None:
    client = _anthropic_client(_anthropic_response(Answer(text="hi"), stop_reason=stop_reason))
    llm = AnthropicLLM("m", client=client)
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "USER", Answer)
    assert str(info.value) == message


def test_anthropic_extract_without_parsed_output_raises() -> None:
    client = _anthropic_client(_anthropic_response(None))
    llm = AnthropicLLM("m", client=client)
    with pytest.raises(LLMError):
        llm.extract("SYS", "USER", Answer)


def test_anthropic_extract_maps_the_sdks_own_json_error() -> None:
    # The real parse() validates the JSON itself, so a cut-off answer raises
    # pydantic's ValidationError from inside the SDK call.
    def cut_off(**_kwargs: object) -> None:
        Answer.model_validate_json('{"text": "half')

    client = _anthropic_client()
    client.messages.parse.side_effect = cut_off
    llm = AnthropicLLM("m", client=client)
    with pytest.raises(LLMError, match="didn't match the expected format") as info:
        llm.extract("SYS", "USER", Answer)
    assert isinstance(info.value.__cause__, ValueError)


# --------------------------------------------------------------------------
# AnthropicLLM.chat and errors
# --------------------------------------------------------------------------


def test_anthropic_chat_joins_text_blocks_only() -> None:
    response = _anthropic_response(
        blocks=[
            SimpleNamespace(type="text", text="Hello "),
            SimpleNamespace(type="tool_use", text="ignored"),
            SimpleNamespace(type="text", text="there"),
        ]
    )
    client = _anthropic_client(response)
    llm = AnthropicLLM("m", client=client)
    messages = [{"role": "user", "content": "hi"}]
    assert llm.chat("SYS", messages) == "Hello there"
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["max_tokens"] == 1024
    assert kwargs["system"] == "SYS"
    assert kwargs["messages"] == messages


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("rate_limit", "The AI service is busy. Try again in a minute."),
        ("connection", "Couldn't reach the AI service. Check the internet connection."),
        ("status", "The AI service returned an error (500)."),
    ],
)
def test_anthropic_maps_sdk_errors(kind: str, message: str) -> None:
    client = MagicMock()
    client.messages.parse.side_effect = _http_error(anthropic, kind)
    llm = AnthropicLLM("m", client=client)
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "USER", Answer)
    assert str(info.value) == message
    assert isinstance(info.value.__cause__, anthropic.APIError)


# --------------------------------------------------------------------------
# OpenAICompatLLM.extract
# --------------------------------------------------------------------------


def test_openai_extract_parses_json() -> None:
    client = _openai_client(_openai_response('{"text": "hello"}'))
    llm = OpenAICompatLLM("m", client=client)
    assert llm.extract("SYS", "USER", Answer) == Answer(text="hello")


def test_openai_extract_sends_the_schema_and_json_mode() -> None:
    client = _openai_client(_openai_response('{"text": "hello"}'))
    llm = OpenAICompatLLM("deepseek-chat", client=client)
    llm.extract("SYS", "USER", Answer)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["response_format"] == {"type": "json_object"}
    system = kwargs["messages"][0]
    assert system["role"] == "system"
    assert system["content"].startswith(
        "SYS\n\nReply with only a JSON object that matches this JSON schema:\n"
    )
    assert json.dumps(Answer.model_json_schema()) in system["content"]
    assert kwargs["messages"][1] == {"role": "user", "content": "USER"}


def test_openai_extract_retries_once_with_the_bad_reply() -> None:
    client = _openai_client(_openai_response("not json"), _openai_response('{"text": "hello"}'))
    llm = OpenAICompatLLM("m", client=client)
    assert llm.extract("SYS", "USER", Answer) == Answer(text="hello")
    assert client.chat.completions.create.call_count == 2
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[2] == {"role": "assistant", "content": "not json"}
    assert messages[3]["role"] == "user"
    assert messages[3]["content"].startswith("That was not valid: ")
    assert messages[3]["content"].endswith("Reply again with only the JSON object.")


def test_openai_extract_raises_after_the_second_failure() -> None:
    client = _openai_client(_openai_response("nope"), _openai_response("still nope"))
    llm = OpenAICompatLLM("m", client=client)
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "USER", Answer)
    assert str(info.value) == "The model's answer didn't match the expected format."
    assert client.chat.completions.create.call_count == 2


def test_openai_extract_rejects_a_cut_off_answer() -> None:
    client = _openai_client(_openai_response('{"text": "hel', finish_reason="length"))
    llm = OpenAICompatLLM("m", client=client)
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "USER", Answer)
    assert str(info.value) == "The model's answer was cut off."


# --------------------------------------------------------------------------
# OpenAICompatLLM.chat and errors
# --------------------------------------------------------------------------


def test_openai_chat_sends_the_system_message_first() -> None:
    client = _openai_client(_openai_response("  Hello there  "))
    llm = OpenAICompatLLM("m", client=client)
    messages = [{"role": "user", "content": "hi"}]
    assert llm.chat("SYS", messages) == "Hello there"
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"] == [{"role": "system", "content": "SYS"}, *messages]
    assert "response_format" not in kwargs


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("rate_limit", "The AI service is busy. Try again in a minute."),
        ("connection", "Couldn't reach the AI service. Check the internet connection."),
        ("status", "The AI service returned an error (500)."),
    ],
)
def test_openai_maps_sdk_errors(kind: str, message: str) -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = _http_error(openai, kind)
    llm = OpenAICompatLLM("m", client=client)
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "USER", Answer)
    assert str(info.value) == message
    assert isinstance(info.value.__cause__, openai.APIError)


# --------------------------------------------------------------------------
# FakeLLM
# --------------------------------------------------------------------------


def test_fake_extract_calls_the_handler() -> None:
    llm = FakeLLM(extract=lambda system, user, schema: {"text": f"{system}/{user}"})
    assert llm.extract("SYS", "USER", Answer) == Answer(text="SYS/USER")


def test_fake_extract_takes_the_first_matching_substring() -> None:
    llm = FakeLLM(
        extract=[
            ("Ava", {"text": "ava"}),
            ("school", {"text": "school"}),
            ("", {"text": "default"}),
        ]
    )
    assert llm.extract("SYS", "the school called about Ava", Answer) == Answer(text="ava")


def test_fake_extract_uses_the_empty_substring_as_default() -> None:
    llm = FakeLLM(extract=[("Ava", {"text": "ava"}), ("", {"text": "default"})])
    assert llm.extract("SYS", "nothing to see", Answer) == Answer(text="default")


def test_fake_extract_without_a_match_raises() -> None:
    llm = FakeLLM(extract=[("Ava", {"text": "ava"})])
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "nothing to see", Answer)
    assert str(info.value) == "FakeLLM: no scripted response"


def test_fake_extract_without_a_script_raises() -> None:
    with pytest.raises(LLMError) as info:
        FakeLLM().extract("SYS", "USER", Answer)
    assert str(info.value) == "FakeLLM has no extract response"


def test_fake_extract_validates_dicts_into_the_schema() -> None:
    llm = FakeLLM(extract=lambda *_: {"text": "from a dict"})
    result = llm.extract("SYS", "USER", Answer)
    assert isinstance(result, Answer)
    assert result.text == "from a dict"


def test_fake_extract_returns_a_model_instance_as_is() -> None:
    answer = Answer(text="ready")
    llm = FakeLLM(extract=lambda *_: answer)
    assert llm.extract("SYS", "USER", Answer) is answer


def test_fake_extract_raises_a_scripted_exception() -> None:
    llm = FakeLLM(extract=[("", LLMError("boom"))])
    with pytest.raises(LLMError) as info:
        llm.extract("SYS", "USER", Answer)
    assert str(info.value) == "boom"


def test_fake_chat_returns_a_fixed_string() -> None:
    llm = FakeLLM(chat="hello")
    assert llm.chat("SYS", [{"role": "user", "content": "hi"}]) == "hello"


def test_fake_chat_calls_the_handler() -> None:
    llm = FakeLLM(chat=lambda system, messages: f"{system}/{len(messages)}")
    assert llm.chat("SYS", [{"role": "user", "content": "hi"}]) == "SYS/1"


def test_fake_chat_without_a_script() -> None:
    assert FakeLLM().chat("SYS", []) == "(fake) no answer scripted"


def test_fake_records_every_call() -> None:
    llm = FakeLLM(extract=lambda *_: {"text": "ok"}, chat="hi")
    messages = [{"role": "user", "content": "hi"}]
    llm.extract("SYS", "USER", Answer)
    llm.chat("SYS2", messages)
    assert llm.calls == [("extract", "SYS", "USER"), ("chat", "SYS2", messages)]


# --------------------------------------------------------------------------
# demo_fake
# --------------------------------------------------------------------------

DEMO_TABLE = [
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


@pytest.mark.parametrize(("prompt", "expected"), DEMO_TABLE)
def test_demo_fake_answers_match_the_table(prompt: str, expected: LLMTriage) -> None:
    result = demo_fake().extract("SYS", f"Text from the phone: {prompt}", LLMTriage)
    assert result == expected


def test_demo_fake_chat() -> None:
    assert demo_fake().chat("SYS", []) == (
        "(Demo mode) Connect a real AI model in .env to get answers about your week."
    )


# --------------------------------------------------------------------------
# keys stay private
# --------------------------------------------------------------------------


def test_keys_never_reach_logs_or_reprs(caplog: pytest.LogCaptureFixture) -> None:
    key = "sk-secret-XYZ"
    prompt = "PROMPT-TEXT-XYZ"
    caplog.set_level(logging.DEBUG)

    anthropic_llm = AnthropicLLM(
        "claude-haiku-5-5",
        api_key=key,
        client=_anthropic_client(_anthropic_response(Answer(text="hi"))),
    )
    anthropic_llm.extract("SYS", prompt, Answer)

    openai_llm = OpenAICompatLLM(
        "gpt-4o-mini",
        api_key=key,
        client=_openai_client(_openai_response('{"text": "hi"}')),
    )
    openai_llm.extract("SYS", prompt, Answer)

    assert "llm provider=" in caplog.text
    for text in (caplog.text, repr(anthropic_llm), repr(openai_llm)):
        assert key not in text
        assert prompt not in text
    for name in (anthropic_llm.name, openai_llm.name):
        assert key not in name
