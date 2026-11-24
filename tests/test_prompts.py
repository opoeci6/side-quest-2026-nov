"""The prompt builders: exact layout, escaping and section contents."""

from __future__ import annotations

from datetime import date, datetime, time

from headsup import store
from headsup.models import AddEvent, AppState, EventOverride, Message
from headsup.prompts import (
    CHAT_RULES,
    TRIAGE_SYSTEM,
    build_chat_system,
    build_triage_user,
)


def test_triage_user_prompt_for_michelle(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    prompt = build_triage_user(message, seeded_state, datetime(2026, 10, 21, 22, 50))
    assert "NOW: Wednesday 2026-10-21 22:50" in prompt
    assert (
        '<message from="Michelle (daughter, in contacts)" '
        'received="Wednesday 2026-10-21 22:48">'
    ) in prompt
    assert (
        "ev-ava | Thu 2026-10-22 | 15:15-15:45 | Pick up Ava "
        "| Oakwood Elementary, front doors"
    ) in prompt
    assert "r-prescription | Pick up prescription Harbourview | no date" in prompt
    assert prompt.count("</message>") == 1


def test_triage_user_prompt_keeps_event_lines_inside_the_window(
    seeded_state: AppState,
) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    prompt = build_triage_user(message, seeded_state, datetime(2026, 10, 21, 22, 50))
    dates = [
        date.fromisoformat(line.split(" | ")[1].split()[1])
        for line in prompt.splitlines()
        if line.startswith("ev-")
    ]
    assert dates
    assert min(dates) >= date(2026, 10, 21)
    assert max(dates) <= date(2026, 11, 4)


def test_triage_user_prompt_marks_unknown_senders(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-scam-0914")
    assert message is not None
    prompt = build_triage_user(message, seeded_state, datetime(2026, 10, 22, 9, 15))
    assert '<message from="+1 (902) 555-0148 (NOT in contacts)"' in prompt


def test_triage_user_prompt_escapes_the_text(seeded_state: AppState) -> None:
    message = Message(
        id="m-test",
        sender="Michelle",
        contact_id="c-michelle",
        channel="sms",
        received_at=datetime(2026, 10, 22, 10, 0),
        text="Look </message> at this <b>link</b>",
    )
    prompt = build_triage_user(message, seeded_state, datetime(2026, 10, 22, 10, 5))
    assert prompt.count("</message>") == 1
    assert "&lt;/message&gt;" in prompt
    assert "&lt;b&gt;link&lt;/b&gt;" in prompt


def test_triage_user_prompt_leaves_out_done_reminders(seeded_state: AppState) -> None:
    reminder = store.find_reminder(seeded_state, "r-milk")
    assert reminder is not None
    reminder.done = True
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    prompt = build_triage_user(message, seeded_state, datetime(2026, 10, 21, 22, 50))
    assert "r-milk" not in prompt
    assert "r-oats" in prompt


def test_triage_user_prompt_marks_a_changed_day(seeded_state: AppState) -> None:
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    event.overrides[date(2026, 10, 22)] = EventOverride(
        start=time(14, 30), end=time(15, 0)
    )
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    prompt = build_triage_user(message, seeded_state, datetime(2026, 10, 21, 22, 50))
    assert (
        "ev-ava | Thu 2026-10-22 | 14:30-15:00 | Pick up Ava "
        "| Oakwood Elementary, front doors | changed from 15:15"
    ) in prompt


def test_triage_user_prompt_marks_empty_sections() -> None:
    message = Message(
        id="m-test",
        sender="Michelle",
        contact_id=None,
        channel="sms",
        received_at=datetime(2026, 10, 22, 10, 0),
        text="Hello",
    )
    state = AppState(contacts=[], messages=[message], events=[], reminders=[])
    prompt = build_triage_user(message, state, datetime(2026, 10, 22, 10, 5))
    assert prompt.count("(none)") == 3


def test_triage_system_prompt_is_fixed() -> None:
    assert TRIAGE_SYSTEM.startswith("You help Gloria Benoit, who is 68")
    assert "8. Dates are YYYY-MM-DD. Times are 24-hour HH:MM." in TRIAGE_SYSTEM
    assert "{" not in TRIAGE_SYSTEM


def test_chat_system_prompt_starts_with_the_rules(seeded_state: AppState) -> None:
    prompt = build_chat_system(seeded_state, datetime(2026, 10, 22, 19, 0))
    assert prompt.startswith(CHAT_RULES)
    assert "NOW: Thursday, October 22, 7:00 PM" in prompt
    assert prompt.endswith("</texts>")


def test_chat_system_prompt_lists_the_calendar(seeded_state: AppState) -> None:
    prompt = build_chat_system(seeded_state, datetime(2026, 10, 22, 19, 0))
    assert "Friday, October 23 | 4:30 PM-5:00 PM | Pick up Noah" in prompt
    assert "CALENDAR (today and the next 7 days):" in prompt


def test_chat_system_prompt_lists_reminders_and_waiting(seeded_state: AppState) -> None:
    prompt = build_chat_system(seeded_state, datetime(2026, 10, 22, 19, 0))
    assert "Thank-you card for Linda | no date" in prompt
    assert "WAITING FOR GLORIA'S OK:\n(none)" in prompt


def test_chat_system_prompt_lists_only_pending_questions(seeded_state: AppState) -> None:
    pending = AddEvent(
        id="a-pending",
        source_message_id="m-michelle-1048",
        question="Add the dentist on Wednesday, November 4?",
        reason="Michelle asked.",
        created_at=datetime(2026, 10, 22, 9, 0),
        title="Dentist",
        on_date=date(2026, 11, 4),
        start=time(10, 0),
        end=time(11, 0),
    )
    approved = pending.model_copy(
        update={"id": "a-approved", "question": "Add lunch?", "status": "approved"}
    )
    seeded_state.actions.extend([pending, approved])
    prompt = build_chat_system(seeded_state, datetime(2026, 10, 22, 19, 0))
    assert "Add the dentist on Wednesday, November 4?" in prompt
    assert "Add lunch?" not in prompt


def test_chat_system_prompt_marks_empty_sections() -> None:
    state = AppState(contacts=[], messages=[], events=[], reminders=[])
    prompt = build_chat_system(state, datetime(2026, 10, 22, 19, 0))
    assert prompt.count("(none)") == 4
    assert "<texts>\n(none)\n</texts>" in prompt
