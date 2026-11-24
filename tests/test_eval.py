"""The offline eval: the case file, the checks and the runner."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.run_eval import EvalCase, Expect, check_case, load_cases, main
from headsup import store
from headsup.llm.base import LLMError
from headsup.llm.fake import FakeLLM, demo_fake
from headsup.models import (
    AddEvent,
    AddReminder,
    RescheduleEvent,
    ScamWarning,
    SetReminderDue,
    TriageOutcome,
)

NOW = datetime(2026, 10, 21, 22, 48)

EXPECTED_PASSES = {
    "c01",
    "c02",
    "c03",
    "c04",
    "c05",
    "c10",
    "c11",
    "c12",
    "c13",
    "c15",
    "c16",
    "c18",
    "c19",
}


def make_case(expect: dict) -> EvalCase:
    return EvalCase(
        id="c01",
        sender="Michelle",
        contact_id="c-michelle",
        received_at=NOW,
        text="a text",
        expect=Expect(**expect),
    )


def make_outcome(actions=(), category: str = "plan_change") -> TriageOutcome:
    return TriageOutcome(
        message_id="c01", category=category, summary="s", actions=list(actions)
    )


def reschedule(
    event_id: str = "ev-ava",
    on_date: date = date(2026, 10, 22),
    new_start: time = time(14, 30),
) -> RescheduleEvent:
    return RescheduleEvent(
        id="a-reschedule",
        source_message_id="c01",
        question="q",
        reason="r",
        created_at=NOW,
        event_id=event_id,
        on_date=on_date,
        new_start=new_start,
        new_end=time(15, 0),
    )


def add_event(
    on_date: date = date(2026, 11, 3), start: time = time(10, 30)
) -> AddEvent:
    return AddEvent(
        id="a-add-event",
        source_message_id="c01",
        question="q",
        reason="r",
        created_at=NOW,
        title="A plan",
        on_date=on_date,
        start=start,
        end=time(11, 30),
    )


def set_due(
    reminder_id: str = "r-prescription", due: date = date(2026, 10, 23)
) -> SetReminderDue:
    return SetReminderDue(
        id="a-set-due",
        source_message_id="c01",
        question="q",
        reason="r",
        created_at=NOW,
        reminder_id=reminder_id,
        due=due,
        alert_at=datetime(2026, 10, 23, 9, 0),
    )


def add_reminder(due: date = date(2026, 10, 24)) -> AddReminder:
    return AddReminder(
        id="a-add-reminder",
        source_message_id="c01",
        question="q",
        reason="r",
        created_at=NOW,
        title="A task",
        due=due,
        alert_at=datetime(2026, 10, 24, 9, 0),
    )


def warning() -> ScamWarning:
    return ScamWarning(
        id="a-scam",
        source_message_id="c01",
        question="q",
        reason="r",
        created_at=NOW,
        signals=["s"],
        advice="a",
    )


# --------------------------------------------------------------------------
# the case file
# --------------------------------------------------------------------------


def test_load_cases_has_twenty_ids_in_order() -> None:
    cases = load_cases()
    assert len(cases) == 20
    assert [case.id for case in cases] == [f"c{index:02d}" for index in range(1, 21)]


def test_first_five_texts_match_the_fixtures() -> None:
    cases = {case.id: case for case in load_cases()}
    state = store.seed_state()
    pairs = {
        "c01": "m-michelle-1048",
        "c02": "m-pharmacy-1000",
        "c03": "m-scam-0914",
        "c04": "m-michelle-1452",
        "c05": "m-michelle-1558",
    }
    for case_id, message_id in pairs.items():
        message = store.find_message(state, message_id)
        assert message is not None
        assert cases[case_id].text == message.text


def test_every_contact_id_exists() -> None:
    contacts = {contact.id for contact in store.seed_state().contacts}
    for case in load_cases():
        if case.contact_id is not None:
            assert case.contact_id in contacts


def test_unknown_expect_key_raises() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(
            {
                "id": "c99",
                "sender": "Michelle",
                "contact_id": None,
                "received_at": "2026-10-21T22:48:00",
                "text": "hi",
                "expect": {"nope": True},
            }
        )


# --------------------------------------------------------------------------
# check_case
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expect", "outcome", "ok"),
    [
        ({"category": ["plan_change"]}, make_outcome(category="plan_change"), True),
        ({"category": ["social", "info"]}, make_outcome(category="plan_change"), False),
        ({"scam": True}, make_outcome(actions=[warning()]), True),
        ({"scam": True}, make_outcome(actions=[reschedule()]), False),
        ({"scam": False}, make_outcome(actions=[reschedule()]), True),
        ({"scam": False}, make_outcome(actions=[warning()]), False),
        (
            {"reschedule": {"event_id": "ev-ava", "on_date": "2026-10-22", "new_start": "14:30"}},
            make_outcome(actions=[reschedule()]),
            True,
        ),
        (
            {"reschedule": {"event_id": "ev-noah", "on_date": "2026-10-22", "new_start": "14:30"}},
            make_outcome(actions=[reschedule()]),
            False,
        ),
        (
            {"add_event": {"on_date": "2026-11-03", "start": "10:30"}},
            make_outcome(actions=[add_event()]),
            True,
        ),
        (
            {"add_event": {"on_date": "2026-11-04", "start": "10:30"}},
            make_outcome(actions=[add_event()]),
            False,
        ),
        (
            {"reminder_due": {"reminder_id": "r-prescription", "due": "2026-10-23"}},
            make_outcome(actions=[set_due()]),
            True,
        ),
        (
            {"reminder_due": {"reminder_id": "r-milk", "due": "2026-10-23"}},
            make_outcome(actions=[set_due()]),
            False,
        ),
        (
            {"reminder_due": {"reminder_id": None, "due": "2026-10-24"}},
            make_outcome(actions=[add_reminder()]),
            True,
        ),
        (
            {"reminder_due": {"reminder_id": None, "due": "2026-10-25"}},
            make_outcome(actions=[add_reminder()]),
            False,
        ),
        ({"forbid": ["reschedule_event"]}, make_outcome(actions=[add_event()]), True),
        ({"forbid": ["reschedule_event"]}, make_outcome(actions=[reschedule()]), False),
        ({"no_calendar_actions": True}, make_outcome(actions=[warning()]), True),
        ({"no_calendar_actions": True}, make_outcome(actions=[set_due()]), False),
    ],
)
def test_check_case(expect: dict, outcome: TriageOutcome, ok: bool) -> None:
    failures = check_case(make_case(expect), outcome)
    assert (failures == []) is ok


def test_check_case_reports_one_reason_per_failed_check() -> None:
    outcome = make_outcome(category="other", actions=[reschedule()])
    failures = check_case(
        make_case({"category": ["social"], "scam": True, "no_calendar_actions": True}),
        outcome,
    )
    assert len(failures) == 3


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def _report(out_dir: Path) -> dict:
    files = sorted(out_dir.glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_main_with_demo_fake(tmp_path: Path) -> None:
    assert main(["--out-dir", str(tmp_path)], llm=demo_fake()) == 0
    report = _report(tmp_path)
    assert report["total"] == 20
    assert report["model"] == "fake:demo"
    assert report["passed"] == 13
    passed = {result["id"] for result in report["results"] if result["passed"]}
    assert passed == EXPECTED_PASSES
    assert report["results"][0]["category"] == "plan_change"
    assert "set_reminder_due" in report["results"][1]["kinds"]


def test_main_below_the_minimum_accuracy(tmp_path: Path) -> None:
    code = main(["--out-dir", str(tmp_path), "--min-accuracy", "0.9"], llm=demo_fake())
    assert code == 1


def test_main_records_model_errors(tmp_path: Path) -> None:
    llm = FakeLLM(extract=[("", LLMError("model down"))])
    assert main(["--out-dir", str(tmp_path)], llm=llm) == 0
    report = _report(tmp_path)
    assert report["passed"] == 0
    assert all(result["failures"] == ["error: model down"] for result in report["results"])
