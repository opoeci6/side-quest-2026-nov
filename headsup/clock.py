"""The only place that reads the real clock.

Every other module takes ``now`` as a parameter, so the October 2026 replay and
the tests stay deterministic.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

DEMO_TIMES: list[tuple[str, datetime]] = [
    ("Wed Oct 21, 7:00 PM (evening check)", datetime(2026, 10, 21, 19, 0)),
    ("Wed Oct 21, 10:50 PM (after Michelle's text)", datetime(2026, 10, 21, 22, 50)),
    ("Thu Oct 22, 10:05 AM (morning texts)", datetime(2026, 10, 22, 10, 5)),
    ("Thu Oct 22, 1:30 PM (alert time)", datetime(2026, 10, 22, 13, 30)),
    ("Thu Oct 22, 7:00 PM (evening check)", datetime(2026, 10, 22, 19, 0)),
]


def parse_now(value: str) -> datetime:
    """Parse an ISO 8601 timestamp into a naive datetime without seconds."""
    return datetime.fromisoformat(value).replace(second=0, microsecond=0)


def now(env: Mapping[str, str] | None = None) -> datetime:
    """Return the current local time, or ``HEADSUP_NOW`` when it is set."""
    source = os.environ if env is None else env
    value = source.get("HEADSUP_NOW")
    if value:
        return parse_now(value)
    return datetime.now().replace(second=0, microsecond=0)
