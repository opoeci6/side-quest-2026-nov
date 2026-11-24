"""The evening "Tomorrow" summary, in writing and read aloud."""

from __future__ import annotations

from datetime import date, datetime, time

from headsup import scam_rules, store
from headsup.digest import build_digest, digest_to_speech
from headsup.models import AppState, RescheduleEvent, ScamWarning, SetReminderDue

WED_1900 = datetime(2026, 10, 21, 19, 0)
WED_2250 = datetime(2026, 10, 21, 22, 50)
THU_1900 = datetime(2026, 10, 22, 19, 0)


def reschedule_action() -> RescheduleEvent:
    return RescheduleEvent(
        id="a-reschedule",
        source_message_id="m-michelle-1048",
        question="Pick up Ava at 2:30 PM this Thursday instead of 3:15?",
        reason="Michelle texted last night: early dismissal.",
        created_at=WED_2250,
        event_id="ev-ava",
        on_date=date(2026, 10, 22),
        new_start=time(14, 30),
        new_end=time(15, 0),
    )


def set_reminder_action() -> SetReminderDue:
    return SetReminderDue(
        id="a-set-reminder",
        source_message_id="m-pharmacy-1000",
        question="Remind you to pick up the prescription on Friday?",
        reason="The pharmacy texted.",
        created_at=THU_1900,
        reminder_id="r-prescription",
        due=date(2026, 10, 23),
        due_time=time(16, 0),
        alert_at=datetime(2026, 10, 22, 9, 0),
    )


def scam_action() -> ScamWarning:
    return ScamWarning(
        id="a-scam",
        source_message_id="m-scam-0914",
        question="This text looks like a scam. Ignore it?",
        reason="It asks for money and tries to rush you.",
        created_at=datetime(2026, 10, 22, 9, 15),
        signals=[
            scam_rules.UNKNOWN_SENDER,
            scam_rules.HAS_LINK,
            scam_rules.ASKS_FOR_MONEY,
            scam_rules.RUSHES_YOU,
        ],
        advice="Don't tap the link. If you're unsure, ask Michelle.",
    )


def test_fresh_digest(seeded_state: AppState) -> None:
    digest = build_digest(seeded_state, WED_1900)
    assert digest.for_date == date(2026, 10, 22)
    assert digest.built_at == WED_1900
    assert digest.plan == ["3:15 PM Pick up Ava (Oakwood Elementary, front doors)"]
    assert digest.changes == []
    assert digest.deadlines == []
    assert digest.warnings == []


def test_digest_after_approving_the_reschedule(seeded_state: AppState) -> None:
    action = reschedule_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, WED_2250)
    digest = build_digest(seeded_state, WED_2250)
    assert len(digest.changes) == 1
    assert digest.changes[0].startswith("Pick up Ava: 2:30 PM instead of 3:15 PM.")
    assert digest.changes[0] == (
        "Pick up Ava: 2:30 PM instead of 3:15 PM. "
        "Michelle texted last night: early dismissal."
    )
    assert digest.plan == ["2:30 PM Pick up Ava (Oakwood Elementary, front doors)"]


def test_digest_with_a_pending_reschedule(seeded_state: AppState) -> None:
    seeded_state.actions.append(reschedule_action())
    digest = build_digest(seeded_state, WED_2250)
    assert len(digest.changes) == 1
    assert digest.changes[0].startswith("Not yet on your calendar: ")
    assert digest.changes[0].endswith("Tap Yes under Needs your OK.")
    assert digest.plan == ["3:15 PM Pick up Ava (Oakwood Elementary, front doors)"]


def test_digest_deadline_and_plan(seeded_state: AppState) -> None:
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    reminder.due = date(2026, 10, 23)
    digest = build_digest(seeded_state, THU_1900)
    assert digest.deadlines == ["Last day tomorrow: Pick up prescription Harbourview"]
    assert digest.plan == ["4:30 PM Pick up Noah"]
    assert digest.changes == []


def test_digest_warning(seeded_state: AppState) -> None:
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    reminder.due = date(2026, 10, 23)
    seeded_state.actions.append(scam_action())
    digest = build_digest(seeded_state, THU_1900)
    assert digest.warnings == [
        "Be careful: the text from +1 (902) 555-0148 looks like a scam. Don't tap the link."
    ]


def test_digest_warning_for_a_missing_message(seeded_state: AppState) -> None:
    action = scam_action()
    action.source_message_id = "m-missing"
    seeded_state.actions.append(action)
    digest = build_digest(seeded_state, THU_1900)
    assert digest.warnings == [
        "Be careful: the text from an unknown number looks like a scam. Don't tap the link."
    ]


def test_digest_ignores_acknowledged_warnings(seeded_state: AppState) -> None:
    action = scam_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, THU_1900)
    assert build_digest(seeded_state, THU_1900).warnings == []


def test_digest_deadline_the_day_after(seeded_state: AppState) -> None:
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    reminder.due = date(2026, 10, 24)
    digest = build_digest(seeded_state, THU_1900)
    assert digest.deadlines == ["Due Saturday: Pick up prescription Harbourview"]


def test_digest_deadlines_are_sorted(seeded_state: AppState) -> None:
    later = store.find_reminder(seeded_state, "r-parcel")
    sooner = store.find_reminder(seeded_state, "r-prescription")
    assert later is not None and sooner is not None
    later.due = date(2026, 10, 24)
    sooner.due = date(2026, 10, 23)
    digest = build_digest(seeded_state, THU_1900)
    assert digest.deadlines == [
        "Last day tomorrow: Pick up prescription Harbourview",
        "Due Saturday: Ask Michelle about the parcel",
    ]


def test_digest_ignores_done_and_distant_reminders(seeded_state: AppState) -> None:
    done = store.find_reminder(seeded_state, "r-prescription")
    distant = store.find_reminder(seeded_state, "r-parcel")
    assert done is not None and distant is not None
    done.due = date(2026, 10, 23)
    done.done = True
    distant.due = date(2026, 10, 30)
    digest = build_digest(seeded_state, THU_1900)
    assert digest.deadlines == []


def test_digest_pending_set_reminder_due(seeded_state: AppState) -> None:
    action = set_reminder_action()
    seeded_state.actions.append(action)
    digest = build_digest(seeded_state, THU_1900)
    assert digest.deadlines == [f"Not yet in your reminders: {action.question}"]


def test_digest_empty_plan(seeded_state: AppState) -> None:
    digest = build_digest(seeded_state, datetime(2026, 10, 25, 19, 0))
    assert digest.for_date == date(2026, 10, 26)
    assert digest.plan == ["Nothing on your calendar."]


def test_digest_to_speech_fresh(seeded_state: AppState) -> None:
    speech = digest_to_speech(build_digest(seeded_state, WED_1900))
    assert speech == (
        "Here is tomorrow, Thursday, October 22. "
        "Your plan: 3:15 PM Pick up Ava (Oakwood Elementary, front doors)."
    )
    assert speech.startswith("Here is tomorrow, Thursday, October 22.")


def test_digest_to_speech_skips_empty_sections(seeded_state: AppState) -> None:
    speech = digest_to_speech(build_digest(seeded_state, datetime(2026, 10, 25, 19, 0)))
    assert speech == (
        "Here is tomorrow, Monday, October 26. Your plan: Nothing on your calendar."
    )


def test_digest_to_speech_with_every_section(seeded_state: AppState) -> None:
    action = reschedule_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, WED_2250)
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    reminder.due = date(2026, 10, 23)
    seeded_state.actions.append(scam_action())
    speech = digest_to_speech(build_digest(seeded_state, WED_2250))
    assert speech == (
        "Here is tomorrow, Thursday, October 22. "
        "What changed: Pick up Ava: 2:30 PM instead of 3:15 PM. "
        "Michelle texted last night: early dismissal. "
        "Your plan: 2:30 PM Pick up Ava (Oakwood Elementary, front doors). "
        "To do: Due Friday: Pick up prescription Harbourview. "
        "Warnings: Be careful: the text from +1 (902) 555-0148 looks like a scam. "
        "Don't tap the link."
    )
