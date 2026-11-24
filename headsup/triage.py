"""Turn one message into proposed actions, using the model's reading plus rules.

Nothing here changes Gloria's plans. Every proposal waits for her tap, and every
value the model returns is checked before it becomes an action.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from headsup.fmt import fmt_date_long, fmt_time, fmt_weekday
from headsup.llm.base import LLM, LLMConfigError, LLMError
from headsup.models import (
    AddEvent,
    AddReminder,
    Alert,
    AppState,
    Contact,
    LLMDeadline,
    LLMPlanChange,
    LLMTriage,
    Message,
    ProposedAction,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
    TriageOutcome,
)
from headsup.prompts import TRIAGE_SYSTEM, build_triage_user
from headsup.scam_rules import is_suspicious, scam_signals
from headsup.store import (
    add_outcome,
    arrived_unprocessed,
    contact_for,
    find_event,
    find_reminder,
    new_id,
    occurrences,
)

log = logging.getLogger(__name__)

SCAM_QUESTION = "This text looks like a scam."
SCAM_ADVICE = "Don't tap the link or reply. If you're not sure, ask Michelle."
RETRY_SUMMARY = "Heads-Up couldn't read this text yet. It will try again at the next check."
# Used when only the rules flagged a scam: the model's own summary may repeat
# the scammer's request in a friendly tone, right above the red card.
RULE_SCAM_SUMMARY = "This text has the signs of a scam."
MAX_ITEMS = 3
WINDOW_DAYS = 60

_MAX_REASONS = 3
_REASON_LIMIT = 200


def _day(day: date, now: datetime) -> str:
    delta = (day - now.date()).days
    if 0 <= delta <= 6:
        return f"this {fmt_weekday(day)}"
    return f"on {fmt_date_long(day)}"


def _reason(message: Message, contact: Contact | None, summary: str) -> str:
    name = contact.name if contact is not None else message.sender
    received = message.received_at
    text = (
        f"From {name}'s text on {fmt_weekday(received.date())} "
        f"at {fmt_time(received.time())}: {summary}"
    )
    if len(text) > _REASON_LIMIT:
        return text[: _REASON_LIMIT - 1] + "…"
    return text


def _finish(
    message_id: str,
    category: str,
    summary: str,
    actions: list[ProposedAction],
    alerts: list[Alert],
    dropped: list[str],
) -> TriageOutcome:
    log.info(
        "Triaged %s as %s with %d actions, %d dropped",
        message_id,
        category,
        len(actions),
        len(dropped),
    )
    return TriageOutcome(
        message_id=message_id,
        category=category,
        summary=summary,
        actions=actions,
        alerts=alerts,
        dropped=dropped,
    )


def _safety_alert(
    action: RescheduleEvent | AddEvent,
    title: str,
    old_start: time | None,
    message: Message,
    contact: Contact,
    state: AppState,
    now: datetime,
) -> Alert | None:
    on_date = action.on_date
    start = action.new_start if isinstance(action, RescheduleEvent) else action.start
    if on_date == now.date():
        pass
    elif on_date == now.date() + timedelta(days=1) and (
        message.received_at.time() > state.evening_check
    ):
        pass
    else:
        return None
    at = max(datetime.combine(on_date, start) - timedelta(minutes=60), now)
    if old_start is None:
        text = f"{contact.name} asked: {title} at {fmt_time(start)} today."
    else:
        text = (
            f"{contact.name} asked: {title} at {fmt_time(start)} today, "
            f"not {fmt_time(old_start)}."
        )
    return Alert(
        id=new_id("al"),
        at=at,
        text=text,
        action_id=action.id,
        source_message_id=message.id,
    )


def _plan_change_action(
    change: LLMPlanChange,
    message: Message,
    state: AppState,
    now: datetime,
    contact: Contact,
    reason: str,
    dropped: list[str],
) -> tuple[RescheduleEvent | AddEvent, Alert | None] | None:
    label = f"plan change for {change.date}"
    try:
        on_date = date.fromisoformat(change.date)
        new_start = time.fromisoformat(change.new_start)
        given_end = time.fromisoformat(change.new_end) if change.new_end is not None else None
    except (TypeError, ValueError):
        dropped.append(f"bad value: {label}")
        return None
    if on_date < now.date() or on_date > now.date() + timedelta(days=WINDOW_DAYS):
        dropped.append(f"out of range: {label}")
        return None

    if change.event_id:
        event = find_event(state, change.event_id)
        if event is None:
            dropped.append(f"unknown event: {change.event_id}")
            return None
        current = next(
            (
                occ
                for occ in occurrences(state, on_date, on_date)
                if occ.event_id == change.event_id
            ),
            None,
        )
        if current is None:
            dropped.append(f"not on that day: {change.event_id} on {on_date.isoformat()}")
            return None
        if given_end is not None:
            new_end = given_end
        else:
            duration = datetime.combine(on_date, current.end) - datetime.combine(
                on_date, current.start
            )
            end_at = datetime.combine(on_date, new_start) + duration
            if end_at.date() != on_date:
                dropped.append(f"bad times: {label}")
                return None
            new_end = end_at.time()
        if new_start >= new_end:
            dropped.append(f"bad times: {label}")
            return None
        if (new_start, new_end) == (current.start, current.end):
            dropped.append(f"same time: {label}")
            return None
        action = RescheduleEvent(
            id=new_id("act"),
            source_message_id=message.id,
            question=(
                f"{event.title} at {fmt_time(new_start)} {_day(on_date, now)} "
                f"instead of {fmt_time(current.start)}?"
            ),
            reason=reason,
            status="pending",
            created_at=now,
            event_id=event.id,
            on_date=on_date,
            new_start=new_start,
            new_end=new_end,
        )
        return action, _safety_alert(
            action, event.title, current.start, message, contact, state, now
        )

    title = change.title.strip()[:80]
    if not title:
        dropped.append(f"bad value: {label}")
        return None
    if given_end is not None:
        new_end = given_end
    else:
        end_at = datetime.combine(on_date, new_start) + timedelta(minutes=60)
        if end_at.date() != on_date:
            dropped.append(f"bad times: {label}")
            return None
        new_end = end_at.time()
    if new_start >= new_end:
        dropped.append(f"bad times: {label}")
        return None
    action = AddEvent(
        id=new_id("act"),
        source_message_id=message.id,
        question=(
            f"Add to your calendar: {title}, {_day(on_date, now)} "
            f"at {fmt_time(new_start)}?"
        ),
        reason=reason,
        status="pending",
        created_at=now,
        title=title,
        on_date=on_date,
        start=new_start,
        end=new_end,
        location=None,
        alert_minutes_before=60,
    )
    return action, _safety_alert(action, title, None, message, contact, state, now)


def _deadline_action(
    deadline: LLMDeadline,
    message: Message,
    state: AppState,
    now: datetime,
    reason: str,
    dropped: list[str],
) -> SetReminderDue | AddReminder | None:
    label = f"deadline for {deadline.due_date}"
    try:
        due = date.fromisoformat(deadline.due_date)
        due_time = (
            time.fromisoformat(deadline.due_time) if deadline.due_time is not None else None
        )
    except (TypeError, ValueError):
        dropped.append(f"bad value: {label}")
        return None
    if due < now.date() or due > now.date() + timedelta(days=WINDOW_DAYS):
        dropped.append(f"out of range: {label}")
        return None
    if due_time is not None:
        alert_at = datetime.combine(due, due_time) - timedelta(hours=2)
    else:
        alert_at = datetime.combine(due, time(9, 0))

    if deadline.reminder_id:
        reminder = find_reminder(state, deadline.reminder_id)
        if reminder is None:
            dropped.append(f"unknown reminder: {deadline.reminder_id}")
            return None
        if reminder.done:
            dropped.append(f"reminder done: {deadline.reminder_id}")
            return None
        if (reminder.due, reminder.due_time) == (due, due_time):
            dropped.append(f"same due: {deadline.reminder_id}")
            return None
        return SetReminderDue(
            id=new_id("act"),
            source_message_id=message.id,
            question=(
                f"Due {_day(due, now)}: {reminder.title}. Add it to your reminders?"
            ),
            reason=reason,
            status="pending",
            created_at=now,
            reminder_id=reminder.id,
            due=due,
            due_time=due_time,
            alert_at=alert_at,
        )

    title = deadline.title.strip()[:80]
    if not title:
        dropped.append(f"bad value: {label}")
        return None
    return AddReminder(
        id=new_id("act"),
        source_message_id=message.id,
        question=f"Due {_day(due, now)}: {title}. Add a new reminder?",
        reason=reason,
        status="pending",
        created_at=now,
        title=title,
        due=due,
        due_time=due_time,
        alert_at=alert_at,
    )


def triage_message(
    message: Message, state: AppState, now: datetime, llm: LLM
) -> TriageOutcome:
    """Read one message and propose what it means. Never changes ``state``."""
    if message.channel in ("app", "call"):
        category = "social" if message.app == "Facebook" else "other"
        return _finish(message.id, category, message.text, [], [], [])

    signals = scam_signals(message, state)
    rule_scam = is_suspicious(signals)
    contact = contact_for(state, message)
    result = llm.extract(TRIAGE_SYSTEM, build_triage_user(message, state, now), LLMTriage)

    summary = result.summary.strip()[:200] or message.text[:200]
    category = result.category
    dropped: list[str] = []
    reason = _reason(message, contact, summary)

    if rule_scam or result.looks_like_scam:
        if not result.looks_like_scam:
            summary = RULE_SCAM_SUMMARY
            reason = _reason(message, contact, summary)
        for _ in result.plan_changes:
            dropped.append("scam: plan change not used")
        for _ in result.deadlines:
            dropped.append("scam: deadline not used")
        combined = list(signals)
        added = 0
        for raw in result.scam_reasons:
            text = raw.strip()[:120]
            if not text or text in combined:
                continue
            combined.append(text)
            added += 1
            if added == _MAX_REASONS:
                break
        action = ScamWarning(
            id=new_id("act"),
            source_message_id=message.id,
            question=SCAM_QUESTION,
            reason=reason,
            status="pending",
            created_at=now,
            signals=combined,
            advice=SCAM_ADVICE,
        )
        return _finish(message.id, "scam", summary, [action], [], dropped)

    if contact is None:
        for _ in result.plan_changes:
            dropped.append("unknown sender: plan change not used")
        for _ in result.deadlines:
            dropped.append("unknown sender: deadline not used")
        return _finish(message.id, category, summary, [], [], dropped)

    actions: list[ProposedAction] = []
    alerts: list[Alert] = []

    for index, change in enumerate(result.plan_changes):
        if index >= MAX_ITEMS:
            dropped.append(f"too many: plan change {index + 1}")
            continue
        built = _plan_change_action(change, message, state, now, contact, reason, dropped)
        if built is None:
            continue
        action, alert = built
        actions.append(action)
        if alert is not None:
            alerts.append(alert)

    for index, deadline in enumerate(result.deadlines):
        if index >= MAX_ITEMS:
            dropped.append(f"too many: deadline {index + 1}")
            continue
        action = _deadline_action(deadline, message, state, now, reason, dropped)
        if action is not None:
            actions.append(action)

    return _finish(message.id, category, summary, actions, alerts, dropped)


def check_new_messages(
    state: AppState, now: datetime, llm: LLM
) -> list[TriageOutcome]:
    """Triage every message that has arrived and not been handled yet."""
    outcomes: list[TriageOutcome] = []
    for message in arrived_unprocessed(state, now):
        try:
            outcome = triage_message(message, state, now, llm)
        except LLMConfigError:
            raise
        except LLMError as exc:
            log.warning("Triage failed for message %s", message.id)
            outcomes.append(
                TriageOutcome(
                    message_id=message.id,
                    category="other",
                    summary=RETRY_SUMMARY,
                    dropped=[f"llm error: {exc}"],
                )
            )
            continue
        add_outcome(state, outcome)
        outcomes.append(outcome)
    return outcomes
