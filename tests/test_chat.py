"""The read-only "Ask me" chat."""

from __future__ import annotations

from datetime import datetime

from headsup import store
from headsup.chat import EMPTY_QUESTION_REPLY, answer
from headsup.llm.fake import FakeLLM
from headsup.models import AppState, ScamWarning
from headsup.prompts import build_chat_system

NOW = datetime(2026, 10, 22, 19, 0)


def test_empty_question_reply_wording() -> None:
    assert EMPTY_QUESTION_REPLY == "Please type a question."


def test_answer_sends_the_system_prompt_and_the_question(seeded_state: AppState) -> None:
    llm = FakeLLM(chat="You pick up Noah tomorrow at 4:30 PM.")
    result = answer("What is tomorrow?", [], seeded_state, NOW, llm)
    assert result == "You pick up Noah tomorrow at 4:30 PM."
    operation, system, messages = llm.calls[0]
    assert operation == "chat"
    assert system == build_chat_system(seeded_state, NOW)
    assert messages[-1] == {"role": "user", "content": "What is tomorrow?"}


def test_empty_question_does_not_call_the_model(seeded_state: AppState) -> None:
    llm = FakeLLM(chat="unused")
    assert answer("   ", [], seeded_state, NOW, llm) == EMPTY_QUESTION_REPLY
    assert llm.calls == []


def test_history_is_trimmed_and_never_starts_with_the_assistant(
    seeded_state: AppState,
) -> None:
    history = [
        {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
        {"role": "assistant", "content": "a4"},
    ]
    llm = FakeLLM(chat="ok")
    answer("next", history, seeded_state, NOW, llm)
    messages = llm.calls[0][2]
    assert len(messages) == 6
    assert messages[0] == {"role": "user", "content": "u2"}
    assert messages[-1] == {"role": "user", "content": "next"}


def test_history_items_are_copied_without_extra_keys(seeded_state: AppState) -> None:
    history = [{"role": "user", "content": "hi", "note": "extra"}]
    llm = FakeLLM(chat="ok")
    answer("q", history, seeded_state, NOW, llm)
    assert llm.calls[0][2][0] == {"role": "user", "content": "hi"}


def test_state_and_history_are_unchanged(seeded_state: AppState) -> None:
    history = [{"role": "user", "content": "hi"}]
    before_state = seeded_state.model_dump()
    before_history = [dict(item) for item in history]
    answer("q", history, seeded_state, NOW, FakeLLM(chat="ok"))
    assert seeded_state.model_dump() == before_state
    assert history == before_history


def test_chat_system_holds_no_future_messages(seeded_state: AppState) -> None:
    prompt = build_chat_system(seeded_state, datetime(2026, 10, 22, 10, 0))
    assert "Mom can you get Ava" in prompt
    assert "Mom?? School called" not in prompt
    assert "Thanks for grabbing her" not in prompt
    assert "Rain starting around 5 PM" not in prompt


def test_a_scam_text_is_marked(seeded_state: AppState) -> None:
    seeded_state.actions.append(
        ScamWarning(
            id="a-scam",
            source_message_id="m-scam-0914",
            question="This text looks like a scam.",
            reason="It asks for money and a link.",
            created_at=datetime(2026, 10, 22, 9, 15),
            signals=["It has a link."],
            advice="Don't tap the link.",
        )
    )
    prompt = build_chat_system(seeded_state, NOW)
    scam_line = next(line for line in prompt.splitlines() if "CanadaPost" in line)
    assert "[looks like a scam]" in scam_line
    other_line = next(
        line for line in prompt.splitlines() if "prescription is ready" in line
    )
    assert "[looks like a scam]" not in other_line


def test_newlines_in_a_text_become_spaces(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-pharmacy-1000")
    assert message is not None
    message.text = "Line one\nLine two"
    prompt = build_chat_system(seeded_state, NOW)
    assert "Line one Line two" in prompt
