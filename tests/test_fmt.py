"""Wording helpers and the demo clock."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from headsup import clock, fmt


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (time(14, 30), "2:30 PM"),
        (time(10, 0), "10:00 AM"),
        (time(12, 0), "12:00 PM"),
        (time(0, 0), "12:00 AM"),
        (time(9, 5), "9:05 AM"),
        (time(13, 5), "1:05 PM"),
        (time(23, 59), "11:59 PM"),
    ],
)
def test_fmt_time(value: time, expected: str) -> None:
    assert fmt.fmt_time(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 10, 22), "Thursday, October 22"),
        (date(2026, 10, 25), "Sunday, October 25"),
        (date(2026, 1, 5), "Monday, January 5"),
        (date(2026, 11, 3), "Tuesday, November 3"),
        (date(2026, 12, 31), "Thursday, December 31"),
    ],
)
def test_fmt_date_long(value: date, expected: str) -> None:
    assert fmt.fmt_date_long(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 10, 21), "today"),
        (date(2026, 10, 22), "tomorrow"),
        (date(2026, 10, 20), "yesterday"),
        (date(2026, 10, 23), "on Friday"),
        (date(2026, 10, 24), "on Saturday"),
        (date(2026, 10, 27), "on Tuesday"),
        (date(2026, 10, 28), "on Wednesday, October 28"),
        (date(2026, 10, 18), "on Sunday, October 18"),
        (date(2027, 1, 2), "on Saturday, January 2"),
    ],
)
def test_fmt_day(value: date, expected: str) -> None:
    assert fmt.fmt_day(value, date(2026, 10, 21)) == expected


def test_demo_times() -> None:
    assert len(clock.DEMO_TIMES) == 5
    assert [label for label, _ in clock.DEMO_TIMES] == [
        "Wed Oct 21, 7:00 PM (evening check)",
        "Wed Oct 21, 10:50 PM (after Michelle's text)",
        "Thu Oct 22, 10:05 AM (morning texts)",
        "Thu Oct 22, 1:30 PM (alert time)",
        "Thu Oct 22, 7:00 PM (evening check)",
    ]
    assert [value for _, value in clock.DEMO_TIMES] == [
        datetime(2026, 10, 21, 19, 0),
        datetime(2026, 10, 21, 22, 50),
        datetime(2026, 10, 22, 10, 5),
        datetime(2026, 10, 22, 13, 30),
        datetime(2026, 10, 22, 19, 0),
    ]


def test_now_uses_the_env_value() -> None:
    assert clock.now({"HEADSUP_NOW": "2026-10-22T13:30:45"}) == datetime(2026, 10, 22, 13, 30)


def test_parse_now_zeroes_seconds_and_microseconds() -> None:
    parsed = clock.parse_now("2026-10-22T13:30:45.123456")
    assert parsed == datetime(2026, 10, 22, 13, 30)
    assert parsed.second == 0
    assert parsed.microsecond == 0


def test_now_falls_back_to_the_real_clock() -> None:
    before = datetime.now().replace(second=0, microsecond=0)
    value = clock.now({})
    after = datetime.now().replace(second=0, microsecond=0)
    assert before <= value <= after
    assert value.second == 0
    assert value.microsecond == 0


def test_now_treats_an_empty_value_as_unset() -> None:
    assert abs((clock.now({"HEADSUP_NOW": ""}) - datetime.now()).total_seconds()) < 120


def test_now_reads_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEADSUP_NOW", "2026-10-21T22:50:00")
    assert clock.now() == datetime(2026, 10, 21, 22, 50)
