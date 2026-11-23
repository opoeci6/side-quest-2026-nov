"""Reading, saving and changing Gloria's state.

State lives in one JSON file under ``.cache/headsup/``, or wherever
``HEADSUP_STATE`` points. Functions that change state do it in place and also
return it; the caller saves.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from headsup.models import (
    AddEvent,
    AddReminder,
    Alert,
    AppState,
    Contact,
    Event,
    EventOverride,
    Message,
    Occurrence,
    ProposedAction,
    Reminder,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
    TriageOutcome,
)

log = logging.getLogger(__name__)

# `AppState.evening_check` is annotated with a bare `time`, a name the shared
# contract module never imports, so the model cannot be built as written.
# Supplying the name here keeps the contract untouched.
AppState.model_rebuild(force=True, _types_namespace={"time": time})

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DATA_DIR: Path = Path(__file__).resolve().parent / "data" / "gloria"

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def default_state_path() -> Path:
    """Return the state file path, honouring ``HEADSUP_STATE`` at call time."""
    value = os.environ.get("HEADSUP_STATE")
    if value:
        return Path(value)
    return REPO_ROOT / ".cache" / "headsup" / "state.json"


def new_id(prefix: str) -> str:
    """Return a short unique id such as ``ev-1a2b3c4d``."""
    return f"{prefix}-{uuid4().hex[:8]}"


def _read_json_list(name: str, model: type[_ModelT]) -> list[_ModelT]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    return [model.model_validate(row) for row in rows if "_note" not in row]


def seed_state() -> AppState:
    """Build a fresh state from the persona files in ``data/gloria``."""
    return AppState(
        contacts=_read_json_list("contacts.json", Contact),
        messages=_read_json_list("messages.json", Message),
        events=_read_json_list("calendar.json", Event),
        reminders=_read_json_list("reminders.json", Reminder),
    )


def load_state(path: Path | None = None) -> AppState:
    """Load state from disk, seeding and saving the file first if it is missing."""
    target = default_state_path() if path is None else path
    if not target.exists():
        state = seed_state()
        save_state(state, target)
        return state
    return AppState.model_validate_json(target.read_text(encoding="utf-8"))


def save_state(state: AppState, path: Path | None = None) -> None:
    """Write state to disk atomically, creating parent folders as needed."""
    target = default_state_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(target) + ".tmp")
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)


def reset_state(path: Path | None = None) -> AppState:
    """Throw away saved state, start again from the fixtures and save it."""
    state = seed_state()
    save_state(state, path)
    return state


def _find(items: Iterable[_ModelT], item_id: str) -> _ModelT | None:
    return next((item for item in items if item.id == item_id), None)


def find_event(state: AppState, event_id: str) -> Event | None:
    """Return the event with this id, or None."""
    return _find(state.events, event_id)


def find_reminder(state: AppState, reminder_id: str) -> Reminder | None:
    """Return the reminder with this id, or None."""
    return _find(state.reminders, reminder_id)


def find_message(state: AppState, message_id: str) -> Message | None:
    """Return the message with this id, or None."""
    return _find(state.messages, message_id)


def find_action(state: AppState, action_id: str) -> ProposedAction | None:
    """Return the proposed action with this id, or None."""
    return _find(state.actions, action_id)


def contact_for(state: AppState, message: Message) -> Contact | None:
    """Return the contact a message came from, or None for unknown senders."""
    if message.contact_id is None:
        return None
    return _find(state.contacts, message.contact_id)


def occurs_on(event: Event, day: date) -> bool:
    """Say whether this event happens on ``day``."""
    if event.repeat_weekdays:
        return day.weekday() in event.repeat_weekdays
    return event.date == day


def occurrences(state: AppState, start: date, end: date) -> list[Occurrence]:
    """Place every event on every day from ``start`` to ``end``, overrides applied."""
    found: list[Occurrence] = []
    day = start
    while day <= end:
        for event in state.events:
            if not occurs_on(event, day):
                continue
            override = event.overrides.get(day)
            if override is not None and override.cancelled:
                continue
            if override is None:
                start_time, end_time = event.start, event.end
            else:
                start_time = override.start or event.start
                end_time = override.end or event.end
            changed = (start_time, end_time) != (event.start, event.end)
            found.append(
                Occurrence(
                    event_id=event.id,
                    title=event.title,
                    location=event.location,
                    date=day,
                    start=start_time,
                    end=end_time,
                    changed=changed,
                    original_start=event.start if changed else None,
                    note=None if override is None else override.note,
                    source_message_id=None if override is None else override.source_message_id,
                    alert_minutes_before=event.alert_minutes_before,
                )
            )
        day += timedelta(days=1)
    found.sort(key=lambda occ: (occ.date, occ.start, occ.title))
    return found


def arrived_unprocessed(state: AppState, now: datetime) -> list[Message]:
    """Return messages that have arrived and have not been triaged yet."""
    processed = set(state.processed_message_ids)
    arrived = [m for m in state.messages if m.received_at <= now and m.id not in processed]
    arrived.sort(key=lambda message: message.received_at)
    return arrived


def add_outcome(state: AppState, outcome: TriageOutcome) -> AppState:
    """Store what triage decided about one message."""
    state.actions.extend(outcome.actions)
    state.alerts.extend(outcome.alerts)
    if outcome.message_id not in state.processed_message_ids:
        state.processed_message_ids.append(outcome.message_id)
    return state


def pending_actions(state: AppState) -> list[ProposedAction]:
    """Return the proposals still waiting for Gloria's tap, in creation order."""
    return [action for action in state.actions if action.status == "pending"]


def _apply(state: AppState, action: ProposedAction) -> None:
    if isinstance(action, RescheduleEvent):
        event = find_event(state, action.event_id)
        if event is None:
            raise KeyError(action.event_id)
        if not occurs_on(event, action.on_date):
            raise ValueError(
                f"event {action.event_id} does not occur on {action.on_date.isoformat()}"
            )
        event.overrides[action.on_date] = EventOverride(
            start=action.new_start,
            end=action.new_end,
            note=action.reason,
            source_message_id=action.source_message_id,
        )
    elif isinstance(action, AddEvent):
        state.events.append(
            Event(
                id=new_id("ev"),
                title=action.title,
                location=action.location,
                start=action.start,
                end=action.end,
                date=action.on_date,
                alert_minutes_before=action.alert_minutes_before,
            )
        )
    elif isinstance(action, SetReminderDue):
        reminder = find_reminder(state, action.reminder_id)
        if reminder is None:
            raise KeyError(action.reminder_id)
        reminder.due = action.due
        reminder.due_time = action.due_time
        reminder.alert_at = action.alert_at
    elif isinstance(action, AddReminder):
        state.reminders.append(
            Reminder(
                id=new_id("r"),
                title=action.title,
                due=action.due,
                due_time=action.due_time,
                alert_at=action.alert_at,
            )
        )
    elif isinstance(action, ScamWarning):
        return


def approve(state: AppState, action_id: str, now: datetime) -> AppState:
    """Apply a pending proposal and mark it approved. Does nothing twice."""
    action = find_action(state, action_id)
    if action is None:
        raise KeyError(action_id)
    if action.status == "rejected":
        raise ValueError(f"action {action_id} was rejected and cannot be approved")
    if action.status == "approved":
        return state
    _apply(state, action)
    action.status = "approved"
    log.info("Approved action %s (%s)", action.id, action.kind)
    return state


def reject(state: AppState, action_id: str) -> AppState:
    """Turn a proposal down and dismiss the alerts that pointed at it."""
    action = find_action(state, action_id)
    if action is None:
        raise KeyError(action_id)
    if action.status == "approved":
        raise ValueError(f"action {action_id} was already approved")
    if action.status == "rejected":
        return state
    action.status = "rejected"
    for alert in state.alerts:
        if alert.action_id == action_id:
            alert.dismissed = True
    log.info("Rejected action %s", action.id)
    return state


def due_alerts(state: AppState, now: datetime) -> list[Alert]:
    """Return alerts that are due and not dismissed, soonest first."""
    due = [alert for alert in state.alerts if alert.at <= now and not alert.dismissed]
    due.sort(key=lambda alert: alert.at)
    return due


def dismiss_alert(state: AppState, alert_id: str) -> AppState:
    """Hide one alert for good."""
    alert = _find(state.alerts, alert_id)
    if alert is None:
        raise KeyError(alert_id)
    alert.dismissed = True
    return state
