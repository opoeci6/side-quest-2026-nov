"""Run the triage cases against one model and write a JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from headsup.llm import LLM, LLMConfigError, LLMError, get_llm
from headsup.models import (
    AddEvent,
    AddReminder,
    Category,
    Message,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
    TriageOutcome,
)
from headsup.store import seed_state
from headsup.triage import triage_message

CASES_PATH = REPO_ROOT / "eval" / "cases.jsonl"

ActionKind = Literal[
    "reschedule_event",
    "add_event",
    "set_reminder_due",
    "add_reminder",
    "scam_warning",
]

CALENDAR_KINDS = (
    "reschedule_event",
    "add_event",
    "set_reminder_due",
    "add_reminder",
)


class RescheduleExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    on_date: date
    new_start: time


class AddEventExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_date: date
    start: time


class ReminderDueExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminder_id: str | None
    due: date


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: list[Category] | None = None
    scam: bool | None = None
    reschedule: RescheduleExpect | None = None
    add_event: AddEventExpect | None = None
    reminder_due: ReminderDueExpect | None = None
    forbid: list[ActionKind] | None = None
    no_calendar_actions: bool | None = None


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sender: str
    contact_id: str | None
    received_at: datetime
    text: str
    expect: Expect


def load_cases(path: Path = CASES_PATH) -> list[EvalCase]:
    """Read the case file, one JSON object per line."""
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase.model_validate_json(line))
    return cases


def run_case(case: EvalCase, llm: LLM) -> TriageOutcome:
    """Run one case through triage against a fresh state."""
    state = seed_state()
    message = Message(
        id=case.id,
        sender=case.sender,
        contact_id=case.contact_id,
        channel="sms",
        received_at=case.received_at,
        text=case.text,
    )
    return triage_message(message, state, case.received_at + timedelta(minutes=1), llm)


def check_case(case: EvalCase, outcome: TriageOutcome) -> list[str]:
    """Return one short reason per failed expectation; empty means pass."""
    expect = case.expect
    failures: list[str] = []

    if expect.category is not None and outcome.category not in expect.category:
        failures.append(
            f"category is {outcome.category}, wanted {' or '.join(expect.category)}"
        )

    if expect.scam is not None:
        warned = any(isinstance(a, ScamWarning) for a in outcome.actions)
        if warned != expect.scam:
            failures.append("expected a scam warning" if expect.scam else "unexpected scam warning")

    if expect.reschedule is not None:
        wanted = expect.reschedule
        if not any(
            isinstance(a, RescheduleEvent)
            and a.event_id == wanted.event_id
            and a.on_date == wanted.on_date
            and a.new_start == wanted.new_start
            for a in outcome.actions
        ):
            failures.append(
                f"no reschedule of {wanted.event_id} on {wanted.on_date} "
                f"at {wanted.new_start:%H:%M}"
            )

    if expect.add_event is not None:
        wanted = expect.add_event
        if not any(
            isinstance(a, AddEvent)
            and a.on_date == wanted.on_date
            and a.start == wanted.start
            for a in outcome.actions
        ):
            failures.append(
                f"no new event on {wanted.on_date} at {wanted.start:%H:%M}"
            )

    if expect.reminder_due is not None:
        wanted = expect.reminder_due
        if wanted.reminder_id is not None:
            matched = any(
                isinstance(a, SetReminderDue)
                and a.reminder_id == wanted.reminder_id
                and a.due == wanted.due
                for a in outcome.actions
            )
        else:
            matched = any(
                isinstance(a, (SetReminderDue, AddReminder)) and a.due == wanted.due
                for a in outcome.actions
            )
        if not matched:
            failures.append(f"no reminder due {wanted.due}")

    if expect.forbid is not None:
        found = sorted({a.kind for a in outcome.actions if a.kind in expect.forbid})
        if found:
            failures.append(f"forbidden actions: {', '.join(found)}")

    if expect.no_calendar_actions:
        found = sorted({a.kind for a in outcome.actions if a.kind in CALENDAR_KINDS})
        if found:
            failures.append(f"calendar actions: {', '.join(found)}")

    return failures


def main(argv: list[str] | None = None, llm: LLM | None = None) -> int:
    """Run every case, print a line each, and save the results."""
    parser = argparse.ArgumentParser(description="Check triage against one model.")
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / ".cache" / "eval")
    parser.add_argument("--min-accuracy", type=float, default=None)
    args = parser.parse_args(argv)

    if llm is None:
        load_dotenv(REPO_ROOT / ".env")
        try:
            llm = get_llm()
        except LLMConfigError as exc:
            print(exc)
            return 2

    cases = load_cases(args.cases)
    results = []
    passed = 0
    for case in cases:
        try:
            outcome = run_case(case, llm)
        except LLMError as exc:
            failures = [f"error: {exc}"]
            print(f"FAIL {case.id}: {'; '.join(failures)}")
            results.append(
                {
                    "id": case.id,
                    "passed": False,
                    "failures": failures,
                    "category": None,
                    "kinds": [],
                    "dropped": [],
                }
            )
            continue
        failures = check_case(case, outcome)
        if failures:
            print(f"FAIL {case.id}: {'; '.join(failures)}")
        else:
            print(f"PASS {case.id}")
            passed += 1
        results.append(
            {
                "id": case.id,
                "passed": not failures,
                "failures": failures,
                "category": outcome.category,
                "kinds": [action.kind for action in outcome.actions],
                "dropped": outcome.dropped,
            }
        )

    total = len(cases)
    accuracy = passed / total if total else 0.0
    print(f"Accuracy: {passed}/{total} ({accuracy:.0%})")
    print(f"Model: {llm.name}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "model": llm.name,
        "accuracy": accuracy,
        "passed": passed,
        "total": total,
        "results": results,
    }
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    (args.out_dir / f"{stamp}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    if args.min_accuracy is not None and accuracy < args.min_accuracy:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
