"""Time and date wording for the large-print screens.

Strings are built by hand rather than with strftime flags such as ``%-I`` or
``%#I``, which do not work on every operating system.
"""

from __future__ import annotations

from datetime import date, time

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def fmt_time(t: time) -> str:
    """Return a 12-hour time with no leading zero, e.g. ``2:30 PM``."""
    hour = t.hour % 12 or 12
    meridiem = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {meridiem}"


def fmt_weekday(d: date) -> str:
    """Return the English weekday name, e.g. ``Friday``, whatever the locale."""
    return _WEEKDAYS[d.weekday()]


def fmt_date_long(d: date) -> str:
    """Return a long date without the year, e.g. ``Thursday, October 22``."""
    return f"{fmt_weekday(d)}, {_MONTHS[d.month - 1]} {d.day}"


def fmt_day(d: date, today: date) -> str:
    """Return a day relative to ``today``, e.g. ``tomorrow`` or ``on Saturday``."""
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if 2 <= delta <= 6:
        return f"on {fmt_weekday(d)}"
    return f"on {fmt_date_long(d)}"
