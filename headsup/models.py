"""Shared data contract for Heads-Up.

Every module builds against these types. Change them only deliberately: other
modules, the saved state file and the LLM schema all depend on them.

Conventions:
- All datetimes are naive local time (Halifax). No time zones anywhere.
- Weekdays use Python's numbering: 0 = Monday ... 6 = Sunday.
- Times shown to Gloria are 12-hour ("2:30 PM"); stored values are datetime.time.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Her phone data
# --------------------------------------------------------------------------


class SenderKind(str, Enum):
    family = "family"
    friend = "friend"
    business = "business"
    app = "app"


class Contact(_Model):
    id: str
    name: str  # as shown on her phone, e.g. "Michelle"
    kind: SenderKind
    relation: str | None = None  # "daughter", "husband", "pharmacy", ...
    phone: str | None = None  # fictional 555 numbers only


class Message(_Model):
    """One notification on her phone: a text, a missed call or an app notice."""

    id: str
    sender: str  # display name as the phone shows it, e.g. "Michelle" or "+1 (902) 555-0148"
    contact_id: str | None = None  # None when the sender is not in her contacts
    channel: Literal["sms", "call", "app"] = "sms"
    app: str | None = None  # "Facebook", "Weather", "Solitaire" when channel == "app"
    received_at: dt.datetime
    text: str


class EventOverride(_Model):
    """A change to one day of an event. Never changes the rest of a series."""

    start: dt.time | None = None
    end: dt.time | None = None
    cancelled: bool = False
    note: str | None = None  # plain words, e.g. "Early dismissal (Michelle's text)"
    source_message_id: str | None = None

    @model_validator(mode="after")
    def _check_times(self) -> EventOverride:
        if self.start and self.end and self.start >= self.end:
            raise ValueError("override start must be before end")
        return self


class Event(_Model):
    """A calendar event: either one-off (`date`) or weekly (`repeat_weekdays`)."""

    id: str
    title: str
    location: str | None = None
    start: dt.time
    end: dt.time
    date: dt.date | None = None
    repeat_weekdays: list[int] = Field(default_factory=list)
    alert_minutes_before: int | None = None  # None = no alert, as on Gloria's phone
    calendar: str = "Gloria"
    overrides: dict[dt.date, EventOverride] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_shape(self) -> Event:
        if (self.date is None) == (not self.repeat_weekdays):
            raise ValueError("an event needs exactly one of `date` or `repeat_weekdays`")
        if any(d < 0 or d > 6 for d in self.repeat_weekdays):
            raise ValueError("repeat_weekdays must be 0..6 (Mon..Sun)")
        if self.start >= self.end:
            raise ValueError("event start must be before end")
        return self


class Occurrence(_Model):
    """An event placed on one day, with that day's override already applied."""

    event_id: str
    title: str
    location: str | None = None
    date: dt.date
    start: dt.time
    end: dt.time
    changed: bool = False  # True when an override moved this day's time
    original_start: dt.time | None = None  # set when changed
    note: str | None = None
    source_message_id: str | None = None
    alert_minutes_before: int | None = None


class Reminder(_Model):
    id: str
    title: str
    list: str = "Reminders"  # "Reminders" or "Groceries"
    notes: str | None = None
    due: dt.date | None = None
    due_time: dt.time | None = None
    alert_at: dt.datetime | None = None
    done: bool = False


class Alert(_Model):
    """A notification Heads-Up shows at a set time (the safety net)."""

    id: str
    at: dt.datetime
    text: str  # plain words for the banner
    action_id: str | None = None  # pending proposal this alert lets her approve
    source_message_id: str | None = None
    dismissed: bool = False


# --------------------------------------------------------------------------
# What Heads-Up proposes. Nothing changes until Gloria taps Yes.
# --------------------------------------------------------------------------

ActionStatus = Literal["pending", "approved", "rejected"]


class _ActionBase(_Model):
    id: str
    source_message_id: str
    question: str  # what the card asks, e.g. "Pick up Ava at 2:30 PM this Thursday instead of 3:15?"
    reason: str  # why, e.g. "Michelle texted last night: early dismissal."
    status: ActionStatus = "pending"
    created_at: dt.datetime


class RescheduleEvent(_ActionBase):
    """Move one day of an event. Approving writes an EventOverride for `on_date`."""

    kind: Literal["reschedule_event"] = "reschedule_event"
    event_id: str
    on_date: dt.date
    new_start: dt.time
    new_end: dt.time


class AddEvent(_ActionBase):
    """A new one-off event, e.g. "Can you take Ray to the dentist Nov 3 at 10:30?"."""

    kind: Literal["add_event"] = "add_event"
    title: str
    on_date: dt.date
    start: dt.time
    end: dt.time
    location: str | None = None
    alert_minutes_before: int | None = 60


class SetReminderDue(_ActionBase):
    """Give an existing reminder a due date and an alert."""

    kind: Literal["set_reminder_due"] = "set_reminder_due"
    reminder_id: str
    due: dt.date
    due_time: dt.time | None = None
    alert_at: dt.datetime


class AddReminder(_ActionBase):
    kind: Literal["add_reminder"] = "add_reminder"
    title: str
    due: dt.date | None = None
    due_time: dt.time | None = None
    alert_at: dt.datetime | None = None


class ScamWarning(_ActionBase):
    """Shown as a red card. "Got it" sets status to approved (= acknowledged)."""

    kind: Literal["scam_warning"] = "scam_warning"
    signals: list[str]  # plain words: "The sender isn't in your contacts", ...
    advice: str  # "Don't tap the link. If you're unsure, ask Michelle."


ProposedAction = Annotated[
    Union[RescheduleEvent, AddEvent, SetReminderDue, AddReminder, ScamWarning],
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------
# Whole app state (persisted to .cache/headsup/state.json)
# --------------------------------------------------------------------------


class AppState(_Model):
    contacts: list[Contact]
    messages: list[Message]  # every fixture message; those after "now" haven't arrived yet
    events: list[Event]
    reminders: list[Reminder]
    actions: list[ProposedAction] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    processed_message_ids: list[str] = Field(default_factory=list)
    evening_check: time = dt.time(19, 0)  # when she usually looks at her phone


# --------------------------------------------------------------------------
# Triage
# --------------------------------------------------------------------------

Category = Literal["plan_change", "deadline", "scam", "social", "info", "other"]


class TriageOutcome(_Model):
    message_id: str
    category: Category
    summary: str  # one plain sentence for Gloria
    actions: list[ProposedAction] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)  # guardrail notes; for logs/tests only


# LLM output schema. Flat, every field required (nullable where it may be
# missing), plain strings for dates/times, so it works on every provider's
# structured-output or JSON mode. triage.py converts it into ProposedActions.


class LLMPlanChange(_Model):
    event_id: str | None = Field(
        description="id of the matching event from the EVENTS list, or null if none matches"
    )
    title: str = Field(description="what the plan is, in a few plain words, e.g. 'Pick up Ava'")
    date: str = Field(description="the day it applies to, YYYY-MM-DD")
    new_start: str = Field(description="new start time, 24-hour HH:MM")
    new_end: str | None = Field(description="new end time, 24-hour HH:MM, or null if not stated")


class LLMDeadline(_Model):
    reminder_id: str | None = Field(
        description="id of the matching reminder from the REMINDERS list, or null if none matches"
    )
    title: str = Field(description="what has to be done, in a few plain words")
    due_date: str = Field(description="last day to do it, YYYY-MM-DD")
    due_time: str | None = Field(description="time it is due, 24-hour HH:MM, or null")


class LLMTriage(_Model):
    category: Category
    summary: str = Field(description="one short, plain sentence for a 68-year-old reader")
    plan_changes: list[LLMPlanChange]
    deadlines: list[LLMDeadline]
    looks_like_scam: bool
    scam_reasons: list[str] = Field(description="plain-words reasons; empty if not a scam")


# --------------------------------------------------------------------------
# Evening "Tomorrow" heads-up
# --------------------------------------------------------------------------


class Digest(_Model):
    for_date: dt.date
    built_at: dt.datetime
    changes: list[str] = Field(default_factory=list)  # what changed, and who changed it
    plan: list[str] = Field(default_factory=list)  # tomorrow's events, in time order
    deadlines: list[str] = Field(default_factory=list)  # due tomorrow or the day after
    warnings: list[str] = Field(default_factory=list)  # scam warnings not yet acknowledged
