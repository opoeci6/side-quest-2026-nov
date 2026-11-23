"""Calendar, triage bookkeeping, approvals and the state file."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pytest

from headsup import scam_rules, store
from headsup.models import (
    AddEvent,
    AddReminder,
    Alert,
    AppState,
    EventOverride,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
    TriageOutcome,
)

NOW = datetime(2026, 10, 21, 22, 50)


def reschedule_action(
    action_id: str = "a-reschedule",
    event_id: str = "ev-ava",
    on_date: date = date(2026, 10, 22),
) -> RescheduleEvent:
    return RescheduleEvent(
        id=action_id,
        source_message_id="m-michelle-1048",
        question="Pick up Ava at 2:30 PM this Thursday instead of 3:15?",
        reason="Michelle texted last night: early dismissal.",
        created_at=NOW,
        event_id=event_id,
        on_date=on_date,
        new_start=time(14, 30),
        new_end=time(15, 0),
    )


def add_event_action(action_id: str = "a-add-event") -> AddEvent:
    return AddEvent(
        id=action_id,
        source_message_id="m-michelle-1048",
        question="Add the dentist on Wednesday, November 4 at 10:30 AM?",
        reason="Michelle asked in her text.",
        created_at=NOW,
        title="Ray - dentist",
        on_date=date(2026, 11, 4),
        start=time(10, 30),
        end=time(11, 30),
        location="Dentist office",
        alert_minutes_before=60,
    )


def set_reminder_action(
    action_id: str = "a-set-reminder",
    reminder_id: str = "r-prescription",
) -> SetReminderDue:
    return SetReminderDue(
        id=action_id,
        source_message_id="m-pharmacy-1000",
        question="Remind you to pick up the prescription on Friday?",
        reason="The pharmacy texted.",
        created_at=NOW,
        reminder_id=reminder_id,
        due=date(2026, 10, 23),
        due_time=time(16, 0),
        alert_at=datetime(2026, 10, 22, 9, 0),
    )


def add_reminder_action(action_id: str = "a-add-reminder") -> AddReminder:
    return AddReminder(
        id=action_id,
        source_message_id="m-pharmacy-1000",
        question="Add 'Pick up prescription' to your reminders?",
        reason="The pharmacy texted.",
        created_at=NOW,
        title="Pick up prescription",
        due=date(2026, 10, 23),
    )


def scam_action(action_id: str = "a-scam") -> ScamWarning:
    return ScamWarning(
        id=action_id,
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


# --------------------------------------------------------------------------
# ids and lookups
# --------------------------------------------------------------------------


def test_new_id() -> None:
    first = store.new_id("ev")
    second = store.new_id("ev")
    assert first.startswith("ev-")
    assert len(first) == len("ev-") + 8
    assert first != second


def test_find_helpers_return_none_for_unknown_ids(seeded_state: AppState) -> None:
    assert store.find_event(seeded_state, "ev-missing") is None
    assert store.find_reminder(seeded_state, "r-missing") is None
    assert store.find_message(seeded_state, "m-missing") is None
    assert store.find_action(seeded_state, "a-missing") is None


def test_contact_for(seeded_state: AppState) -> None:
    known = store.find_message(seeded_state, "m-michelle-1048")
    assert known is not None
    contact = store.contact_for(seeded_state, known)
    assert contact is not None
    assert contact.id == "c-michelle"
    unknown = store.find_message(seeded_state, "m-scam-0914")
    assert unknown is not None
    assert store.contact_for(seeded_state, unknown) is None
    stale = known.model_copy(update={"contact_id": "c-missing"})
    assert store.contact_for(seeded_state, stale) is None


# --------------------------------------------------------------------------
# occurrences
# --------------------------------------------------------------------------


def test_occurrences_pickups(seeded_state: AppState) -> None:
    found = store.occurrences(seeded_state, date(2026, 10, 20), date(2026, 10, 27))
    ava = [(occ.date, occ.start, occ.end) for occ in found if occ.event_id == "ev-ava"]
    assert ava == [
        (date(2026, 10, 20), time(15, 15), time(15, 45)),
        (date(2026, 10, 22), time(15, 15), time(15, 45)),
        (date(2026, 10, 27), time(15, 15), time(15, 45)),
    ]
    noah = [(occ.date, occ.start) for occ in found if occ.event_id == "ev-noah"]
    assert noah == [(date(2026, 10, 23), time(16, 30))]


def test_occurrences_cover_the_whole_range_inclusively(seeded_state: AppState) -> None:
    found = store.occurrences(seeded_state, date(2026, 10, 22), date(2026, 10, 22))
    assert [(occ.date, occ.title) for occ in found] == [
        (date(2026, 10, 22), "Pick up Ava"),
    ]
    found = store.occurrences(seeded_state, date(2026, 10, 25), date(2026, 10, 25))
    assert [(occ.start, occ.title) for occ in found] == [
        (time(10, 30), "Church"),
        (time(13, 0), "Family lunch at Michelle's"),
    ]


def test_occurrences_are_sorted(seeded_state: AppState) -> None:
    found = store.occurrences(seeded_state, date(2026, 10, 19), date(2026, 10, 25))
    keys = [(occ.date, occ.start, occ.title) for occ in found]
    assert keys == sorted(keys)


def test_occurrences_carry_event_details(seeded_state: AppState) -> None:
    found = store.occurrences(seeded_state, date(2026, 10, 22), date(2026, 10, 22))
    occ = found[0]
    assert occ.location == "Oakwood Elementary, front doors"
    assert occ.changed is False
    assert occ.original_start is None
    assert occ.note is None
    assert occ.source_message_id is None
    assert occ.alert_minutes_before is None


def test_override_changes_only_that_day(seeded_state: AppState) -> None:
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    event.overrides[date(2026, 10, 22)] = EventOverride(
        start=time(14, 30),
        end=time(15, 0),
        note="Early dismissal (Michelle's text)",
        source_message_id="m-michelle-1048",
    )
    found = {
        occ.date: occ
        for occ in store.occurrences(seeded_state, date(2026, 10, 20), date(2026, 10, 27))
        if occ.event_id == "ev-ava"
    }
    changed = found[date(2026, 10, 22)]
    assert changed.changed is True
    assert (changed.start, changed.end) == (time(14, 30), time(15, 0))
    assert changed.original_start == time(15, 15)
    assert changed.note == "Early dismissal (Michelle's text)"
    assert changed.source_message_id == "m-michelle-1048"

    for day in (date(2026, 10, 20), date(2026, 10, 27)):
        untouched = found[day]
        assert untouched.changed is False
        assert (untouched.start, untouched.end) == (time(15, 15), time(15, 45))
        assert untouched.original_start is None
        assert untouched.note is None
        assert untouched.source_message_id is None


def test_cancelled_override_removes_only_that_day(seeded_state: AppState) -> None:
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    event.overrides[date(2026, 10, 22)] = EventOverride(cancelled=True)
    days = [
        occ.date
        for occ in store.occurrences(seeded_state, date(2026, 10, 20), date(2026, 10, 27))
        if occ.event_id == "ev-ava"
    ]
    assert days == [date(2026, 10, 20), date(2026, 10, 27)]


def test_occurs_on(seeded_state: AppState) -> None:
    ava = store.find_event(seeded_state, "ev-ava")
    assert ava is not None
    assert store.occurs_on(ava, date(2026, 10, 22)) is True
    assert store.occurs_on(ava, date(2026, 10, 21)) is False
    church = store.find_event(seeded_state, "ev-church")
    assert church is not None
    assert store.occurs_on(church, date(2026, 10, 25)) is True
    assert store.occurs_on(church, date(2026, 10, 18)) is False


# --------------------------------------------------------------------------
# arrived messages and triage outcomes
# --------------------------------------------------------------------------


def test_arrived_unprocessed_at_1005(seeded_state: AppState) -> None:
    ids = [
        message.id
        for message in store.arrived_unprocessed(seeded_state, datetime(2026, 10, 22, 10, 5))
    ]
    assert ids == [
        "m-michelle-1048",
        "m-solitaire-0800",
        "m-facebook-0830",
        "m-scam-0914",
        "m-pharmacy-1000",
    ]


def test_arrived_unprocessed_respects_now(seeded_state: AppState) -> None:
    ids = [
        message.id
        for message in store.arrived_unprocessed(seeded_state, datetime(2026, 10, 21, 23, 0))
    ]
    assert ids == ["m-michelle-1048"]


def test_arrived_unprocessed_skips_processed_messages(seeded_state: AppState) -> None:
    store.add_outcome(
        seeded_state,
        TriageOutcome(message_id="m-scam-0914", category="scam", summary="Looks like a scam."),
    )
    ids = [
        message.id
        for message in store.arrived_unprocessed(seeded_state, datetime(2026, 10, 22, 10, 5))
    ]
    assert ids == [
        "m-michelle-1048",
        "m-solitaire-0800",
        "m-facebook-0830",
        "m-pharmacy-1000",
    ]


def test_add_outcome_appends_and_marks_processed(seeded_state: AppState) -> None:
    action = add_event_action()
    alert = Alert(id="al-1", at=datetime(2026, 10, 22, 13, 30), text="Check your calendar")
    outcome = TriageOutcome(
        message_id="m-michelle-1048",
        category="plan_change",
        summary="Ava comes home early tomorrow.",
        actions=[action],
        alerts=[alert],
    )
    store.add_outcome(seeded_state, outcome)
    assert seeded_state.actions == [action]
    assert seeded_state.alerts == [alert]
    assert seeded_state.processed_message_ids == ["m-michelle-1048"]
    store.add_outcome(seeded_state, outcome)
    assert seeded_state.processed_message_ids == ["m-michelle-1048"]


def test_pending_actions_in_order(seeded_state: AppState) -> None:
    first = add_event_action("a-1")
    second = scam_action("a-2")
    third = add_reminder_action("a-3")
    seeded_state.actions.extend([first, second, third])
    store.approve(seeded_state, second.id, NOW)
    assert store.pending_actions(seeded_state) == [first, third]


# --------------------------------------------------------------------------
# approve
# --------------------------------------------------------------------------


def test_approve_reschedule_writes_the_override(seeded_state: AppState) -> None:
    action = reschedule_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, NOW)
    assert action.status == "approved"
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    override = event.overrides[date(2026, 10, 22)]
    assert (override.start, override.end) == (time(14, 30), time(15, 0))
    assert override.cancelled is False
    assert override.note == action.reason
    assert override.source_message_id == "m-michelle-1048"
    occ = store.occurrences(seeded_state, date(2026, 10, 22), date(2026, 10, 22))[0]
    assert occ.changed is True
    assert occ.start == time(14, 30)


def test_approve_add_event(seeded_state: AppState) -> None:
    action = add_event_action()
    seeded_state.actions.append(action)
    before = len(seeded_state.events)
    store.approve(seeded_state, action.id, NOW)
    assert len(seeded_state.events) == before + 1
    event = seeded_state.events[-1]
    assert event.id.startswith("ev-")
    assert event.title == "Ray - dentist"
    assert event.location == "Dentist office"
    assert (event.start, event.end) == (time(10, 30), time(11, 30))
    assert event.date == date(2026, 11, 4)
    assert event.repeat_weekdays == []
    assert event.alert_minutes_before == 60
    assert action.status == "approved"
    found = store.occurrences(seeded_state, date(2026, 11, 4), date(2026, 11, 4))
    assert [(occ.title, occ.start) for occ in found] == [("Ray - dentist", time(10, 30))]


def test_approve_set_reminder_due(seeded_state: AppState) -> None:
    action = set_reminder_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, NOW)
    reminder = store.find_reminder(seeded_state, "r-prescription")
    assert reminder is not None
    assert reminder.due == date(2026, 10, 23)
    assert reminder.due_time == time(16, 0)
    assert reminder.alert_at == datetime(2026, 10, 22, 9, 0)
    assert action.status == "approved"


def test_approve_add_reminder(seeded_state: AppState) -> None:
    action = add_reminder_action()
    seeded_state.actions.append(action)
    before = len(seeded_state.reminders)
    store.approve(seeded_state, action.id, NOW)
    assert len(seeded_state.reminders) == before + 1
    reminder = seeded_state.reminders[-1]
    assert reminder.id.startswith("r-")
    assert reminder.title == "Pick up prescription"
    assert reminder.due == date(2026, 10, 23)
    assert reminder.due_time is None
    assert reminder.alert_at is None
    assert reminder.done is False
    assert action.status == "approved"


def test_approve_scam_warning_only_acknowledges(seeded_state: AppState) -> None:
    action = scam_action()
    seeded_state.actions.append(action)
    events_before = len(seeded_state.events)
    reminders_before = len(seeded_state.reminders)
    store.approve(seeded_state, action.id, NOW)
    assert action.status == "approved"
    assert len(seeded_state.events) == events_before
    assert len(seeded_state.reminders) == reminders_before
    assert seeded_state.events[3].overrides == {}


def test_approve_is_idempotent_for_add_event(seeded_state: AppState) -> None:
    action = add_event_action()
    seeded_state.actions.append(action)
    before = len(seeded_state.events)
    store.approve(seeded_state, action.id, NOW)
    store.approve(seeded_state, action.id, NOW)
    assert len(seeded_state.events) == before + 1


def test_approve_is_idempotent_for_reschedule(seeded_state: AppState) -> None:
    action = reschedule_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, NOW)
    store.approve(seeded_state, action.id, NOW)
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    assert len(event.overrides) == 1


def test_approve_unknown_id_raises(seeded_state: AppState) -> None:
    with pytest.raises(KeyError):
        store.approve(seeded_state, "a-missing", NOW)


def test_approve_rejected_action_raises(seeded_state: AppState) -> None:
    action = add_event_action()
    seeded_state.actions.append(action)
    store.reject(seeded_state, action.id)
    with pytest.raises(ValueError):
        store.approve(seeded_state, action.id, NOW)


def test_approve_reschedule_on_a_day_without_the_event_raises(seeded_state: AppState) -> None:
    action = reschedule_action(on_date=date(2026, 10, 21))
    seeded_state.actions.append(action)
    with pytest.raises(ValueError):
        store.approve(seeded_state, action.id, NOW)
    assert action.status == "pending"
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    assert event.overrides == {}


def test_approve_reschedule_for_unknown_event_raises(seeded_state: AppState) -> None:
    action = reschedule_action(event_id="ev-missing")
    seeded_state.actions.append(action)
    with pytest.raises(KeyError):
        store.approve(seeded_state, action.id, NOW)
    assert action.status == "pending"


def test_approve_set_reminder_for_unknown_reminder_raises(seeded_state: AppState) -> None:
    action = set_reminder_action(reminder_id="r-missing")
    seeded_state.actions.append(action)
    with pytest.raises(KeyError):
        store.approve(seeded_state, action.id, NOW)
    assert action.status == "pending"


# --------------------------------------------------------------------------
# reject
# --------------------------------------------------------------------------


def test_reject_sets_status_and_dismisses_linked_alerts(seeded_state: AppState) -> None:
    action = add_event_action()
    seeded_state.actions.append(action)
    seeded_state.alerts.extend(
        [
            Alert(
                id="al-linked",
                at=datetime(2026, 10, 22, 13, 30),
                text="Check your calendar",
                action_id=action.id,
            ),
            Alert(id="al-other", at=datetime(2026, 10, 22, 14, 0), text="Something else"),
        ]
    )
    store.reject(seeded_state, action.id)
    assert action.status == "rejected"
    assert seeded_state.alerts[0].dismissed is True
    assert seeded_state.alerts[1].dismissed is False


def test_reject_approved_action_raises(seeded_state: AppState) -> None:
    action = add_event_action()
    seeded_state.actions.append(action)
    store.approve(seeded_state, action.id, NOW)
    with pytest.raises(ValueError):
        store.reject(seeded_state, action.id)


def test_reject_twice_changes_nothing(seeded_state: AppState) -> None:
    action = add_event_action()
    seeded_state.actions.append(action)
    store.reject(seeded_state, action.id)
    after_first = seeded_state.model_dump()
    store.reject(seeded_state, action.id)
    assert seeded_state.model_dump() == after_first


def test_reject_unknown_id_raises(seeded_state: AppState) -> None:
    with pytest.raises(KeyError):
        store.reject(seeded_state, "a-missing")


# --------------------------------------------------------------------------
# alerts
# --------------------------------------------------------------------------


def test_due_alerts_filters_and_sorts(seeded_state: AppState) -> None:
    seeded_state.alerts.extend(
        [
            Alert(id="al-late", at=datetime(2026, 10, 22, 14, 0), text="late"),
            Alert(id="al-early", at=datetime(2026, 10, 22, 12, 0), text="early"),
            Alert(id="al-hidden", at=datetime(2026, 10, 22, 11, 0), text="hidden", dismissed=True),
            Alert(id="al-future", at=datetime(2026, 10, 22, 20, 0), text="future"),
        ]
    )
    due = store.due_alerts(seeded_state, datetime(2026, 10, 22, 15, 0))
    assert [alert.id for alert in due] == ["al-early", "al-late"]


def test_dismiss_alert(seeded_state: AppState) -> None:
    seeded_state.alerts.append(
        Alert(id="al-1", at=datetime(2026, 10, 22, 12, 0), text="Check your calendar")
    )
    store.dismiss_alert(seeded_state, "al-1")
    assert seeded_state.alerts[0].dismissed is True
    assert store.due_alerts(seeded_state, datetime(2026, 10, 22, 15, 0)) == []
    with pytest.raises(KeyError):
        store.dismiss_alert(seeded_state, "al-missing")


# --------------------------------------------------------------------------
# the state file
# --------------------------------------------------------------------------


def test_save_and_load_round_trip(seeded_state: AppState, state_path: Path) -> None:
    event = store.find_event(seeded_state, "ev-ava")
    assert event is not None
    event.overrides[date(2026, 10, 22)] = EventOverride(
        start=time(14, 30),
        end=time(15, 0),
        note="Early dismissal (Michelle's text)",
        source_message_id="m-michelle-1048",
    )
    approved = reschedule_action()
    seeded_state.actions.append(approved)
    store.approve(seeded_state, approved.id, NOW)
    warning = scam_action()
    seeded_state.actions.append(warning)
    seeded_state.alerts.append(
        Alert(
            id="al-1",
            at=datetime(2026, 10, 22, 13, 30),
            text="Check your calendar",
            action_id=approved.id,
            source_message_id="m-michelle-1048",
        )
    )

    store.save_state(seeded_state)
    assert state_path.exists()
    loaded = store.load_state()

    assert loaded == seeded_state
    assert loaded.events[3].overrides[date(2026, 10, 22)].start == time(14, 30)
    assert loaded.actions[0].status == "approved"
    assert loaded.actions[1].status == "pending"
    assert loaded.alerts[0].dismissed is False


def test_save_state_leaves_no_temp_file(seeded_state: AppState, state_path: Path) -> None:
    store.save_state(seeded_state)
    assert not Path(str(state_path) + ".tmp").exists()


def test_save_state_creates_parent_folders(seeded_state: AppState, tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "state.json"
    store.save_state(seeded_state, target)
    assert target.exists()


def test_load_state_seeds_a_missing_file(seeded_state: AppState, state_path: Path) -> None:
    assert not state_path.exists()
    state = store.load_state()
    assert state_path.exists()
    assert len(state.messages) == 9
    assert len(store.load_state().messages) == 9


def test_load_state_reads_back_changes(seeded_state: AppState, state_path: Path) -> None:
    seeded_state.events[0].title = "Hair appointment (moved)"
    store.save_state(seeded_state)
    assert store.load_state().events[0].title == "Hair appointment (moved)"


def test_default_state_path_honours_the_env_set_after_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "late.json"
    monkeypatch.setenv("HEADSUP_STATE", str(target))
    assert store.default_state_path() == target


def test_default_state_path_without_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEADSUP_STATE", raising=False)
    assert store.default_state_path() == (
        store.REPO_ROOT / ".cache" / "headsup" / "state.json"
    )


def test_reset_state_restores_the_fixtures(seeded_state: AppState, state_path: Path) -> None:
    seeded_state.events.clear()
    store.save_state(seeded_state)
    fresh = store.reset_state()
    assert len(fresh.events) == 8
    assert len(store.load_state().events) == 8
