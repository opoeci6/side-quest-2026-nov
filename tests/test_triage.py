"""Triage guardrails: what becomes an action, what is dropped, and the alerts."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from headsup import scam_rules, store
from headsup.llm.base import LLMConfigError, LLMError
from headsup.llm.fake import FakeLLM, demo_fake
from headsup.models import (
    AddEvent,
    AddReminder,
    EventOverride,
    LLMDeadline,
    LLMPlanChange,
    LLMTriage,
    Message,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
    TriageOutcome,
)
from headsup.prompts import TRIAGE_SYSTEM
from headsup.triage import (
    RETRY_SUMMARY,
    SCAM_ADVICE,
    SCAM_QUESTION,
    check_new_messages,
    triage_message,
)

NOW = datetime(2026, 10, 22, 10, 5)


def make_message(
    text: str = "A text from Michelle",
    sender: str = "Michelle",
    contact_id: str | None = "c-michelle",
    received_at: datetime = datetime(2026, 10, 22, 9, 0),
    channel: str = "sms",
    app: str | None = None,
    message_id: str = "m-test",
) -> Message:
    return Message(
        id=message_id,
        sender=sender,
        contact_id=contact_id,
        channel=channel,
        app=app,
        received_at=received_at,
        text=text,
    )


def make_answer(
    category: str = "plan_change",
    summary: str = "A short summary.",
    plan_changes: list[LLMPlanChange] | None = None,
    deadlines: list[LLMDeadline] | None = None,
    looks_like_scam: bool = False,
    scam_reasons: list[str] | None = None,
) -> LLMTriage:
    return LLMTriage(
        category=category,
        summary=summary,
        plan_changes=plan_changes or [],
        deadlines=deadlines or [],
        looks_like_scam=looks_like_scam,
        scam_reasons=scam_reasons or [],
    )


def plan_change(
    event_id: str | None = None,
    title: str = "A plan",
    on_date: str = "2026-10-22",
    new_start: str = "14:30",
    new_end: str | None = None,
) -> LLMPlanChange:
    return LLMPlanChange(
        event_id=event_id,
        title=title,
        date=on_date,
        new_start=new_start,
        new_end=new_end,
    )


def deadline(
    reminder_id: str | None = None,
    title: str = "A task",
    due_date: str = "2026-10-23",
    due_time: str | None = None,
) -> LLMDeadline:
    return LLMDeadline(
        reminder_id=reminder_id,
        title=title,
        due_date=due_date,
        due_time=due_time,
    )


def run(
    message: Message,
    answer: LLMTriage,
    state,
    now: datetime = NOW,
) -> TriageOutcome:
    return triage_message(message, state, now, FakeLLM(extract=[("", answer)]))


def drop_codes(outcome: TriageOutcome) -> list[str]:
    return [note.split(":")[0] + ": " for note in outcome.dropped]


# --------------------------------------------------------------------------
# the two worked examples
# --------------------------------------------------------------------------


def test_michelle_case(seeded_state) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    outcome = triage_message(
        message, seeded_state, datetime(2026, 10, 21, 22, 50), demo_fake()
    )
    assert outcome.category == "plan_change"
    assert len(outcome.actions) == 1
    action = outcome.actions[0]
    assert isinstance(action, RescheduleEvent)
    assert action.new_start == time(14, 30)
    assert action.new_end == time(15, 0)
    assert action.question == "Pick up Ava at 2:30 PM this Thursday instead of 3:15 PM?"
    assert action.reason == (
        "From Michelle's text on Wednesday at 10:48 PM: Michelle asks you to pick up "
        "Ava at 2:30 tomorrow instead of 3:15, because of an early dismissal."
    )
    assert len(outcome.alerts) == 1
    alert = outcome.alerts[0]
    assert alert.at == datetime(2026, 10, 22, 13, 30)
    assert alert.text == "Michelle asked: Pick up Ava at 2:30 PM today, not 3:15 PM."
    assert alert.action_id == action.id
    assert alert.source_message_id == message.id


def test_pharmacy_case(seeded_state) -> None:
    message = store.find_message(seeded_state, "m-pharmacy-1000")
    assert message is not None
    outcome = triage_message(
        message, seeded_state, datetime(2026, 10, 22, 10, 5), demo_fake()
    )
    assert len(outcome.actions) == 1
    action = outcome.actions[0]
    assert isinstance(action, SetReminderDue)
    assert action.reminder_id == "r-prescription"
    assert action.due == date(2026, 10, 23)
    assert action.alert_at == datetime(2026, 10, 23, 9, 0)
    assert action.question == (
        "Due this Friday: Pick up prescription Harbourview. "
        "Add it to your reminders?"
    )
    assert outcome.alerts == []


def test_deadline_with_a_time_sets_the_alert_two_hours_early(seeded_state) -> None:
    message = store.find_message(seeded_state, "m-pharmacy-1000")
    assert message is not None
    answer = make_answer(
        category="deadline",
        deadlines=[deadline(reminder_id="r-prescription", due_time="16:00")],
    )
    outcome = run(message, answer, seeded_state)
    action = outcome.actions[0]
    assert isinstance(action, SetReminderDue)
    assert action.due_time == time(16, 0)
    assert action.alert_at == datetime(2026, 10, 23, 14, 0)


# --------------------------------------------------------------------------
# scams
# --------------------------------------------------------------------------


def test_rule_scam_wins_over_the_model(seeded_state) -> None:
    message = store.find_message(seeded_state, "m-scam-0914")
    assert message is not None
    answer = make_answer(
        plan_changes=[plan_change(event_id="ev-ava")],
        deadlines=[deadline(title="Pay a fee")],
        looks_like_scam=False,
    )
    outcome = run(message, answer, seeded_state, now=datetime(2026, 10, 22, 9, 15))
    assert outcome.category == "scam"
    assert len(outcome.actions) == 1
    warning = outcome.actions[0]
    assert isinstance(warning, ScamWarning)
    assert warning.signals[:4] == [
        scam_rules.UNKNOWN_SENDER,
        scam_rules.HAS_LINK,
        scam_rules.ASKS_FOR_MONEY,
        scam_rules.RUSHES_YOU,
    ]
    assert warning.question == SCAM_QUESTION
    assert warning.advice == SCAM_ADVICE
    assert outcome.dropped
    assert all(note.startswith("scam: ") for note in outcome.dropped)
    assert outcome.alerts == []


def test_model_only_scam_uses_its_reasons(seeded_state) -> None:
    message = make_message(text="Something odd happened")
    answer = make_answer(
        category="scam",
        looks_like_scam=True,
        scam_reasons=["It asks for money.", "It tries to rush you."],
    )
    outcome = run(message, answer, seeded_state)
    warning = outcome.actions[0]
    assert isinstance(warning, ScamWarning)
    assert warning.signals == ["It asks for money.", "It tries to rush you."]


def test_scam_reasons_are_cleaned_and_capped(seeded_state) -> None:
    message = make_message(text="Something odd happened")
    reasons = ["  It asks for money.  ", "", "It asks for money.", "a", "b", "c", "d"]
    answer = make_answer(category="scam", looks_like_scam=True, scam_reasons=reasons)
    outcome = run(message, answer, seeded_state)
    warning = outcome.actions[0]
    assert warning.signals == ["It asks for money.", "a", "b"]


# --------------------------------------------------------------------------
# unknown senders
# --------------------------------------------------------------------------


def test_unknown_sender_drops_calendar_actions(seeded_state) -> None:
    message = make_message(
        text="Bake sale after Sunday mass, all welcome!",
        sender="St. Brendan's",
        contact_id=None,
        received_at=datetime(2026, 10, 22, 8, 0),
    )
    answer = make_answer(
        plan_changes=[plan_change(title="Bake sale", on_date="2026-10-25", new_start="11:00")],
        deadlines=[deadline(title="Bring a plate", due_date="2026-10-25")],
    )
    outcome = run(message, answer, seeded_state)
    assert outcome.actions == []
    assert drop_codes(outcome) == ["unknown sender: ", "unknown sender: "]


# --------------------------------------------------------------------------
# plan change guardrails
# --------------------------------------------------------------------------


def test_bad_date_is_dropped(seeded_state) -> None:
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava", on_date="Oct 22")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("bad value: ")


def test_bad_time_is_dropped(seeded_state) -> None:
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava", new_start="2:30")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("bad value: ")


def test_past_date_is_dropped(seeded_state) -> None:
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava", on_date="2026-10-21")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("out of range: ")


def test_date_beyond_the_window_is_dropped(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(title="Dentist", on_date="2026-12-22", new_start="09:00")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("out of range: ")


def test_last_day_in_the_window_is_kept(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(title="Dentist", on_date="2026-12-21", new_start="09:00")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert len(outcome.actions) == 1
    assert outcome.dropped == []


def test_unknown_event_is_dropped(seeded_state) -> None:
    answer = make_answer(plan_changes=[plan_change(event_id="ev-nope")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("unknown event: ")


def test_event_on_another_day_is_dropped(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(event_id="ev-ava", on_date="2026-10-28")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("not on that day: ")


def test_cancelled_day_is_dropped(seeded_state) -> None:
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    event.overrides[date(2026, 10, 22)] = EventOverride(cancelled=True)
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("not on that day: ")


def test_end_before_start_is_dropped(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(event_id="ev-ava", new_start="15:00", new_end="14:00")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("bad times: ")


def test_same_time_is_dropped(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[
            plan_change(event_id="ev-noah", on_date="2026-10-23", new_start="16:30")
        ]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("same time: ")


def test_fourth_plan_change_is_dropped(seeded_state) -> None:
    changes = [
        plan_change(title=f"Plan {index}", on_date="2026-10-28", new_start="09:00")
        for index in range(4)
    ]
    outcome = run(make_message(), make_answer(plan_changes=changes), seeded_state)
    assert len(outcome.actions) == 3
    assert any(note.startswith("too many: ") for note in outcome.dropped)


def test_explicit_end_is_used(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(event_id="ev-ava", new_start="14:30", new_end="14:45")]
    )
    outcome = run(make_message(), answer, seeded_state)
    action = outcome.actions[0]
    assert isinstance(action, RescheduleEvent)
    assert action.new_end == time(14, 45)


def test_null_event_id_adds_an_event(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[
            plan_change(title="Ride to physio for Ray", on_date="2026-10-29", new_start="14:00")
        ]
    )
    outcome = run(make_message(), answer, seeded_state)
    action = outcome.actions[0]
    assert isinstance(action, AddEvent)
    assert action.end == time(15, 0)
    assert action.location is None
    assert action.alert_minutes_before == 60
    assert action.question == (
        "Add to your calendar: Ride to physio for Ray, on Thursday, October 29 at 2:00 PM?"
    )


# --------------------------------------------------------------------------
# deadline guardrails
# --------------------------------------------------------------------------


def test_unknown_reminder_is_dropped(seeded_state) -> None:
    answer = make_answer(deadlines=[deadline(reminder_id="r-nope")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("unknown reminder: ")


def test_done_reminder_is_dropped(seeded_state) -> None:
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    reminder.done = True
    answer = make_answer(deadlines=[deadline(reminder_id="r-prescription")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("reminder done: ")


def test_same_due_is_dropped(seeded_state) -> None:
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    reminder.due = date(2026, 10, 23)
    answer = make_answer(deadlines=[deadline(reminder_id="r-prescription")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("same due: ")


def test_bad_deadline_date_is_dropped(seeded_state) -> None:
    answer = make_answer(deadlines=[deadline(title="A task", due_date="Fri Oct 23")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("bad value: ")


def test_past_deadline_is_dropped(seeded_state) -> None:
    answer = make_answer(deadlines=[deadline(title="A task", due_date="2026-10-21")])
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions == []
    assert outcome.dropped[0].startswith("out of range: ")


def test_null_reminder_id_adds_a_reminder(seeded_state) -> None:
    answer = make_answer(
        category="deadline",
        deadlines=[deadline(title="Bring back Linda's casserole dish", due_date="2026-10-24")],
    )
    outcome = run(make_message(), answer, seeded_state)
    action = outcome.actions[0]
    assert isinstance(action, AddReminder)
    assert action.due == date(2026, 10, 24)
    assert action.question == (
        "Due this Saturday: Bring back Linda's casserole dish. Add a new reminder?"
    )


def test_fourth_deadline_is_dropped(seeded_state) -> None:
    deadlines = [
        deadline(title=f"Task {index}", due_date="2026-10-30") for index in range(4)
    ]
    outcome = run(make_message(), make_answer(deadlines=deadlines), seeded_state)
    assert len(outcome.actions) == 3
    assert any(note.startswith("too many: ") for note in outcome.dropped)


# --------------------------------------------------------------------------
# the safety net
# --------------------------------------------------------------------------


def test_alert_for_today(seeded_state) -> None:
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava")])
    outcome = run(make_message(), answer, seeded_state, now=datetime(2026, 10, 22, 10, 5))
    assert len(outcome.alerts) == 1
    assert outcome.alerts[0].at == datetime(2026, 10, 22, 13, 30)
    assert outcome.alerts[0].text == (
        "Michelle asked: Pick up Ava at 2:30 PM today, not 3:15 PM."
    )


def test_alert_for_tomorrow_after_the_evening_check(seeded_state) -> None:
    message = make_message(received_at=datetime(2026, 10, 21, 22, 48))
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava")])
    outcome = run(message, answer, seeded_state, now=datetime(2026, 10, 21, 22, 50))
    assert len(outcome.alerts) == 1


def test_no_alert_for_tomorrow_before_the_evening_check(seeded_state) -> None:
    message = make_message(received_at=datetime(2026, 10, 21, 18, 0))
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava")])
    outcome = run(message, answer, seeded_state, now=datetime(2026, 10, 21, 18, 5))
    assert outcome.alerts == []


def test_no_alert_two_days_ahead(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(event_id="ev-ava", on_date="2026-10-27", new_start="14:30")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions
    assert outcome.alerts == []


def test_alert_time_is_clamped_to_now(seeded_state) -> None:
    now = datetime(2026, 10, 22, 14, 0)
    answer = make_answer(plan_changes=[plan_change(event_id="ev-ava")])
    outcome = run(make_message(received_at=datetime(2026, 10, 22, 13, 50)), answer, seeded_state, now=now)
    assert outcome.alerts[0].at == now


def test_add_event_alert_text_has_no_comparison(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(title="Ride for Ray", new_start="15:00")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.alerts[0].text == "Michelle asked: Ride for Ray at 3:00 PM today."


def test_no_alert_for_deadlines(seeded_state) -> None:
    answer = make_answer(
        category="deadline",
        deadlines=[deadline(reminder_id="r-prescription", due_date="2026-10-22")],
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions
    assert outcome.alerts == []


# --------------------------------------------------------------------------
# wording
# --------------------------------------------------------------------------


def test_day_wording_within_the_week(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(title="Dentist", on_date="2026-10-28", new_start="09:00")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions[0].question == (
        "Add to your calendar: Dentist, this Wednesday at 9:00 AM?"
    )


def test_day_wording_beyond_the_week(seeded_state) -> None:
    answer = make_answer(
        plan_changes=[plan_change(title="Dentist", on_date="2026-10-29", new_start="09:00")]
    )
    outcome = run(make_message(), answer, seeded_state)
    assert outcome.actions[0].question == (
        "Add to your calendar: Dentist, on Thursday, October 29 at 9:00 AM?"
    )


def test_reason_is_cut_to_two_hundred_characters(seeded_state) -> None:
    answer = make_answer(
        summary="x" * 300, plan_changes=[plan_change(event_id="ev-ava")]
    )
    outcome = run(make_message(), answer, seeded_state)
    reason = outcome.actions[0].reason
    assert len(reason) == 200
    assert reason.endswith("…")


def test_summary_comes_from_the_model(seeded_state) -> None:
    message = make_message(
        text="Bake sale after Sunday mass, all welcome!",
        sender="St. Brendan's",
        contact_id=None,
    )
    outcome = run(message, make_answer(category="info"), seeded_state)
    assert outcome.actions == []
    assert outcome.summary == "A short summary."


# --------------------------------------------------------------------------
# the model call
# --------------------------------------------------------------------------


def test_app_and_call_messages_skip_the_model(seeded_state) -> None:
    llm = FakeLLM()
    facebook = store.find_message(seeded_state, "m-facebook-0830")
    weather = store.find_message(seeded_state, "m-weather-1605")
    call = store.find_message(seeded_state, "m-michelle-call-1447")
    assert facebook is not None and weather is not None and call is not None

    social = triage_message(facebook, seeded_state, datetime(2026, 10, 22, 10, 5), llm)
    assert social.category == "social"
    assert social.summary == facebook.text
    assert social.actions == []

    info = triage_message(weather, seeded_state, datetime(2026, 10, 22, 16, 10), llm)
    assert info.category == "other"
    assert info.summary == weather.text

    missed = triage_message(call, seeded_state, datetime(2026, 10, 22, 14, 50), llm)
    assert missed.category == "other"
    assert llm.calls == []


def test_the_model_is_called_once_with_the_triage_prompt(seeded_state) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    llm = FakeLLM(extract=[("", make_answer())])
    triage_message(message, seeded_state, datetime(2026, 10, 21, 22, 50), llm)
    assert len(llm.calls) == 1
    operation, system, user = llm.calls[0]
    assert operation == "extract"
    assert system == TRIAGE_SYSTEM
    assert "<message" in user


def test_triage_does_not_change_the_state(seeded_state) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    before = seeded_state.model_dump()
    triage_message(message, seeded_state, datetime(2026, 10, 21, 22, 50), demo_fake())
    assert seeded_state.model_dump() == before


def test_empty_summary_falls_back_to_the_text(seeded_state) -> None:
    outcome = run(make_message(text="Hello there"), make_answer(summary="   "), seeded_state)
    assert outcome.summary == "Hello there"


# --------------------------------------------------------------------------
# check_new_messages
# --------------------------------------------------------------------------


def test_check_new_messages_processes_the_morning_texts(seeded_state) -> None:
    llm = demo_fake()
    outcomes = check_new_messages(seeded_state, datetime(2026, 10, 22, 10, 5), llm)
    assert [outcome.message_id for outcome in outcomes] == [
        "m-michelle-1048",
        "m-solitaire-0800",
        "m-facebook-0830",
        "m-scam-0914",
        "m-pharmacy-1000",
    ]
    assert len([call for call in llm.calls if call[0] == "extract"]) == 3
    assert seeded_state.processed_message_ids == [
        "m-michelle-1048",
        "m-solitaire-0800",
        "m-facebook-0830",
        "m-scam-0914",
        "m-pharmacy-1000",
    ]
    kinds = [action.kind for action in seeded_state.actions]
    assert kinds.count("reschedule_event") == 1
    assert kinds.count("scam_warning") == 1
    assert kinds.count("set_reminder_due") == 1
    assert len(seeded_state.alerts) == 1


def test_check_new_messages_leaves_a_failed_message_unprocessed(seeded_state) -> None:
    llm = FakeLLM(
        extract=[
            ("CanadaPost", LLMError("model down")),
            ("", make_answer(category="other")),
        ]
    )
    outcomes = check_new_messages(seeded_state, datetime(2026, 10, 22, 10, 5), llm)
    assert "m-scam-0914" not in seeded_state.processed_message_ids
    assert len(seeded_state.processed_message_ids) == 4
    failed = next(outcome for outcome in outcomes if outcome.message_id == "m-scam-0914")
    assert failed.summary == RETRY_SUMMARY
    assert failed.dropped == ["llm error: model down"]
    assert failed.actions == []


def test_check_new_messages_propagates_a_config_error(seeded_state) -> None:
    llm = FakeLLM(extract=[("", LLMConfigError("Set ANTHROPIC_API_KEY in .env."))])
    with pytest.raises(LLMConfigError):
        check_new_messages(seeded_state, datetime(2026, 10, 22, 10, 5), llm)
    assert seeded_state.processed_message_ids == []
