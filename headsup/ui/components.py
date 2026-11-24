"""Small, plain pieces of the large-print screen.

Nothing here imports Streamlit: every function returns a string or a list, so
the tests can check the wording and the escaping without a browser. Text that
came from a phone or from a model goes through :func:`text_html` first, so it
can never become a link or a piece of HTML.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta

from headsup import store
from headsup.fmt import fmt_date_long, fmt_time, fmt_weekday
from headsup.models import Alert, AppState, Message, Occurrence

# A due alert stays on screen this long, then goes away even if nobody tapped OK.
# Its text says "today", so it must not still be showing after the event or the next day.
ALERT_SHOWS_FOR = timedelta(hours=2)

CSS = """
html { font-size: 21px; }

.stApp { background: #ffffff; color: #111; }
.block-container { max-width: 46rem; padding-top: 2.2rem; padding-bottom: 3.5rem; }

h1 { font-size: 2.2rem !important; color: #111 !important; letter-spacing: 0; }
h2 { font-size: 1.5rem !important; color: #111 !important; margin-top: 1.6rem; }
h3 { font-size: 1.25rem !important; color: #111 !important; }

[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"] p { color: #111; }

.stButton > button,
[data-testid^="stBaseButton"] {
  min-height: 56px;
  font-size: 1.15rem;
  font-weight: 600;
  border-radius: 12px;
  padding: 0.5rem 1.1rem;
}
/* Streamlit puts the label in its own paragraph, which would otherwise stay small. */
.stButton > button p,
[data-testid^="stBaseButton"] p { font-size: 1.15rem; font-weight: 600; }
/* White label on the green Yes button; the near-black text rule above would hide it. */
[data-testid="stBaseButton-primary"] p { color: #fff; }

/* Wrap the tabs onto a second line on a phone instead of hiding some off-screen. */
[role="tablist"] { flex-wrap: wrap; gap: 0.2rem 0.6rem; }
[data-testid="stTab"] { min-height: 56px; padding: 0.4rem 0.6rem; }
[data-testid="stTab"] p { font-size: 1.1rem; font-weight: 600; color: #111; }

[data-testid="stVerticalBlockBorderWrapper"] { margin-bottom: 1.2rem; }

.hu-text,
.hu-message,
.hu-reason,
.hu-caption,
.hu-label,
.hu-signal,
.hu-advice { color: #111; font-size: 1.05rem; line-height: 1.5; }

.hu-text { margin: 0.2rem 0 0.9rem; }
.hu-reason { font-size: 1rem; margin: 0 0 0.8rem; }
.hu-caption { font-size: 0.95rem; font-weight: 600; margin: 0.2rem 0 0.4rem; }
.hu-label { font-size: 1.1rem; font-weight: 700; margin: 0.6rem 0 0.4rem; }
.hu-signal { margin: 0.1rem 0 0.35rem 0.4rem; }
.hu-signal::before { content: "• "; font-weight: 700; }
.hu-advice { font-weight: 600; margin: 0.7rem 0 0.9rem; }

.hu-question {
  color: #111;
  font-size: 1.3rem;
  font-weight: 700;
  line-height: 1.35;
  margin: 0.1rem 0 0.6rem;
}

.hu-message {
  background: #f1f1f1;
  border-left: 8px solid #555555;
  border-radius: 6px;
  padding: 0.85rem 1rem;
  margin: 0.3rem 0 1rem;
}

.hu-alert {
  background: #ffd97a;
  border: 4px solid #7a4b00;
  border-radius: 10px;
  padding: 0.9rem 1.1rem;
  margin: 0.4rem 0 0.9rem;
  font-size: 1.15rem;
  font-weight: 700;
  color: #111;
}

.hu-notice-success {
  background: #e2f3e5; border-left: 8px solid #1b6b2a;
  padding: 0.8rem 1rem; border-radius: 6px; font-weight: 600; margin: 0.6rem 0 1rem;
}
.hu-notice-info {
  background: #e6eefb; border-left: 8px solid #1c4f9c;
  padding: 0.8rem 1rem; border-radius: 6px; font-weight: 600; margin: 0.6rem 0 1rem;
}

[class*="st-key-scam-"] {
  background: #fdecea !important;
  border: 3px solid #b3261e !important;
  border-radius: 12px !important;
  padding: 0.5rem 0.7rem !important;
}
"""

_LINK_BREAK = re.compile(r"([./@])(?=\S)")


def text_html(text: str, css_class: str = "hu-text") -> str:
    """Return one block of text as escaped HTML that can never hold a link."""
    escaped = html.escape(text, quote=True)
    broken = _LINK_BREAK.sub("\\1\u200b", escaped)
    body = broken.replace("\n", "<br>")
    return f'<div class="{css_class}">{body}</div>'


def render_message_html(text: str) -> str:
    """Return a text message as a quoted block, ready to show."""
    return text_html(text, "hu-message")


def speak_button_html(text: str, label: str = "Read it to me") -> str:
    """Return a tiny page with one big button that reads ``text`` out loud."""
    spoken = json.dumps(text).replace("</", "<\\/")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en-CA">\n'
        '<head><meta charset="utf-8">\n'
        "<style>\n"
        "html,body{margin:0;background:transparent;"
        'font-family:system-ui,-apple-system,"Segoe UI",sans-serif}\n'
        "button{min-height:56px;width:100%;font-size:1.15rem;font-weight:600;"
        "color:#111;background:#fff;border:3px solid #111;border-radius:12px;"
        "cursor:pointer}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f'<button type="button" onclick="speak()">{html.escape(label, quote=True)}</button>\n'
        "<script>\n"
        f"var text = {spoken};\n"
        "function speak() {\n"
        "  window.speechSynthesis.cancel();\n"
        "  var words = new SpeechSynthesisUtterance(text);\n"
        '  words.lang = "en-CA";\n'
        "  words.rate = 0.9;\n"
        "  window.speechSynthesis.speak(words);\n"
        "}\n"
        "</script>\n"
        "</body>\n"
        "</html>"
    )


def header_text(now: datetime) -> str:
    """Return the line under the title, e.g. ``Thursday, October 22 · 1:30 PM``."""
    return f"{fmt_date_long(now.date())} · {fmt_time(now.time())}"


def day_heading(day: date, today: date) -> str:
    """Return a day heading that says today or tomorrow when it can."""
    if day == today:
        return f"Today, {fmt_date_long(day)}"
    if day == today + timedelta(days=1):
        return f"Tomorrow, {fmt_date_long(day)}"
    return fmt_date_long(day)


def _occurrence_line(occurrence: Occurrence) -> str:
    line = f"{fmt_time(occurrence.start)} {occurrence.title}"
    if occurrence.location:
        line += f" ({occurrence.location})"
    if occurrence.changed and occurrence.original_start is not None:
        line += f" (changed from {fmt_time(occurrence.original_start)})"
    return line


def week_view(state: AppState, now: datetime) -> list[tuple[str, list[str]]]:
    """Return one heading and its lines for today and the six days after it."""
    today = now.date()
    days: list[tuple[str, list[str]]] = []
    for offset in range(7):
        day = today + timedelta(days=offset)
        lines = [_occurrence_line(occ) for occ in store.occurrences(state, day, day)]
        due = [r for r in state.reminders if not r.done and r.due == day]
        due.sort(key=lambda reminder: reminder.title)
        for reminder in due:
            line = f"To do: {reminder.title}"
            if reminder.due_time is not None:
                line += f" by {fmt_time(reminder.due_time)}"
            lines.append(line)
        if not lines:
            lines.append("Nothing planned.")
        days.append((day_heading(day, today), lines))
    return days


def other_reminders(state: AppState) -> list[str]:
    """Return the open reminders that have no day, with their list name."""
    return [
        f"{reminder.title} ({reminder.list})"
        for reminder in state.reminders
        if not reminder.done and reminder.due is None
    ]


def visible_alerts(state: AppState, now: datetime) -> list[Alert]:
    """Return the due alerts that are still recent enough to show."""
    return [alert for alert in store.due_alerts(state, now) if now < alert.at + ALERT_SHOWS_FOR]


def check_summary(read: int, waiting: int, retries: int) -> str:
    """Return the notice after a check, e.g. ``Read 1 new text. 1 needs your OK.``."""
    if read == 0 and retries == 0:
        return "No new texts."
    text = (
        f"Read {read} new {'text' if read == 1 else 'texts'}. "
        f"{waiting} {'needs' if waiting == 1 else 'need'} your OK."
    )
    if retries:
        text += (
            f" {retries} {'text' if retries == 1 else 'texts'} couldn't be read"
            " and will be tried again."
        )
    return text


def received_line(message: Message) -> str:
    """Return who sent a message and when, e.g. ``Michelle · Wednesday 10:48 PM``."""
    received = message.received_at
    return f"{message.sender} · {fmt_weekday(received.date())} {fmt_time(received.time())}"
