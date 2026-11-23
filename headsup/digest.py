"""The evening "Tomorrow" summary and the words to read it aloud."""

from __future__ import annotations

from datetime import datetime, timedelta

from headsup.fmt import fmt_date_long, fmt_time, fmt_weekday
from headsup.models import (
    AppState,
    Digest,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
)
from headsup.store import find_message, occurrences

_UNKNOWN_SENDER = "an unknown number"


def _change_lines(state: AppState, for_date) -> list[str]:
    lines = []
    for occ in occurrences(state, for_date, for_date):
        if not occ.changed:
            continue
        line = f"{occ.title}: {fmt_time(occ.start)} instead of {fmt_time(occ.original_start)}."
        if occ.note:
            line += f" {occ.note}"
        lines.append(line)
    for action in state.actions:
        if (
            isinstance(action, RescheduleEvent)
            and action.status == "pending"
            and action.on_date == for_date
        ):
            lines.append(
                f"Not yet on your calendar: {action.question} Tap Yes under Needs your OK."
            )
    return lines


def _plan_lines(state: AppState, for_date) -> list[str]:
    lines = []
    for occ in occurrences(state, for_date, for_date):
        line = f"{fmt_time(occ.start)} {occ.title}"
        if occ.location:
            line += f" ({occ.location})"
        lines.append(line)
    if not lines:
        return ["Nothing on your calendar."]
    return lines


def _deadline_lines(state: AppState, for_date) -> list[str]:
    day_after = for_date + timedelta(days=1)
    due_soon = [
        reminder
        for reminder in state.reminders
        if not reminder.done and reminder.due in (for_date, day_after)
    ]
    due_soon.sort(key=lambda reminder: (reminder.due, reminder.title))
    lines = []
    for reminder in due_soon:
        if reminder.due == for_date:
            lines.append(f"Last day tomorrow: {reminder.title}")
        else:
            lines.append(f"Due {fmt_weekday(reminder.due)}: {reminder.title}")
    for action in state.actions:
        if (
            isinstance(action, SetReminderDue)
            and action.status == "pending"
            and action.due in (for_date, day_after)
        ):
            lines.append(f"Not yet in your reminders: {action.question}")
    return lines


def _warning_lines(state: AppState) -> list[str]:
    lines = []
    for action in state.actions:
        if isinstance(action, ScamWarning) and action.status == "pending":
            message = find_message(state, action.source_message_id)
            sender = message.sender if message is not None else _UNKNOWN_SENDER
            lines.append(
                f"Be careful: the text from {sender} looks like a scam. Don't tap the link."
            )
    return lines


def build_digest(state: AppState, now: datetime) -> Digest:
    """Build tomorrow's summary as of ``now``."""
    for_date = now.date() + timedelta(days=1)
    return Digest(
        for_date=for_date,
        built_at=now,
        changes=_change_lines(state, for_date),
        plan=_plan_lines(state, for_date),
        deadlines=_deadline_lines(state, for_date),
        warnings=_warning_lines(state),
    )


def _as_sentence(line: str) -> str:
    if line.endswith((".", "!", "?")):
        return line
    return line + "."


def digest_to_speech(digest: Digest) -> str:
    """Turn a digest into one paragraph meant to be read aloud."""
    parts = [f"Here is tomorrow, {fmt_date_long(digest.for_date)}."]
    sections = (
        ("What changed: ", digest.changes),
        ("Your plan: ", digest.plan),
        ("To do: ", digest.deadlines),
        ("Warnings: ", digest.warnings),
    )
    for label, lines in sections:
        if not lines:
            continue
        parts.append(label + " ".join(_as_sentence(line) for line in lines))
    return " ".join(parts)
