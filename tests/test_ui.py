"""Tests for the large-print screen: the drawing helpers and the app itself.

Everything runs offline. The app is driven through Streamlit's own test
harness, with the fake model and a temporary state file, so no key is needed
and nothing touches the network.
"""

from __future__ import annotations

import html
import json
from datetime import date, datetime, time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from headsup import clock, store
from headsup.models import AppState, RescheduleEvent
from headsup.ui.components import (
    check_summary,
    day_heading,
    header_text,
    other_reminders,
    received_line,
    render_message_html,
    speak_button_html,
    text_html,
    visible_alerts,
    week_view,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(REPO_ROOT / "streamlit_app.py")
EVENING = datetime(2026, 10, 21, 19, 0)
SCAM_TEXT = (
    "CanadaPost FINAL NOTICE: Your parcel will be returned to sender. "
    "Pay the $1.99 redelivery fee: canadapost-redelivery.example/pay"
)
DEMO_ANSWER = "(Demo mode) Connect a real AI model in .env to get answers about your week."
AVA_LINE = "3:15 PM Pick up Ava (Oakwood Elementary, front doors)"
AVA_MOVED = "2:30 PM Pick up Ava (Oakwood Elementary, front doors) (changed from 3:15 PM)"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


@pytest.fixture
def state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a fresh state file, a fake model and no keys."""
    path = tmp_path / "state.json"
    monkeypatch.setenv("HEADSUP_SKIP_DOTENV", "1")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("HEADSUP_STATE", str(path))
    for name in (
        "HEADSUP_NOW",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    return path


def start_app() -> AppTest:
    """Open the app once at the default demo time."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    return at


def pick_preset(at: AppTest, index: int) -> None:
    """Choose one of the demo times in the sidebar and redraw."""
    at.selectbox(key="clock-preset").select(clock.DEMO_TIMES[index][0]).run()


def texts(at: AppTest) -> list[str]:
    """Every block of text the page shows, in order, as written."""
    return [element.value for element in at.markdown]


def page_text(at: AppTest) -> str:
    """All the text on the page as Gloria reads it.

    The invisible breaks that keep a link from forming are taken out, and the
    escaping is undone, so a test can look for the words themselves.
    """
    raw = "\n".join(texts(at))
    return html.unescape(raw).replace("\u200b", "")


def shows(at: AppTest, needle: str) -> bool:
    """Say whether any block of text on the page shows ``needle``."""
    return needle in page_text(at)


def button_keys(at: AppTest) -> set[str]:
    """The keys of every button on the page."""
    return {button.key for button in at.button if button.key}


def tab_labels(at: AppTest) -> list[str]:
    """The labels of the five tabs, in order."""
    return [tab.label for tab in at.tabs]


def saved(path: Path) -> dict:
    """Read the state file the app just wrote."""
    return json.loads(path.read_text(encoding="utf-8"))


def pending(path: Path) -> list[dict]:
    """The proposals still waiting for a tap, in the saved file."""
    return [action for action in saved(path)["actions"] if action["status"] == "pending"]


def eval_case(case_id: str) -> dict:
    """Read one case from the triage case file."""
    path = REPO_ROOT / "eval" / "cases.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            if case["id"] == case_id:
                return case
    raise AssertionError(f"no eval case {case_id}")


# --------------------------------------------------------------------------
# 1. text_html and render_message_html
# --------------------------------------------------------------------------


def test_text_html_leaves_no_link_in_a_scam_text() -> None:
    out = text_html(SCAM_TEXT)
    assert "<a" not in out
    assert "canadapost-redelivery.example/pay" not in out
    assert "canadapost-redelivery.\u200bexample/\u200bpay" in out


def test_text_html_escapes_html_in_the_text() -> None:
    out = text_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_text_html_turns_newlines_into_breaks_without_a_blank_line() -> None:
    out = text_html("first line\nsecond line\n\nthird line")
    assert "<br>" in out
    assert "\n" not in out


def test_text_html_changes_nothing_but_the_escaping() -> None:
    out = text_html("St. Brendan's at 2:30 PM")
    assert out == '<div class="hu-text">St. Brendan&#x27;s at 2:30 PM</div>'


def test_render_message_html_uses_the_message_box() -> None:
    out = render_message_html("See you at 3:15.")
    assert out == text_html("See you at 3:15.", "hu-message")
    assert 'class="hu-message"' in out


# --------------------------------------------------------------------------
# 2. speak_button_html
# --------------------------------------------------------------------------


def test_speak_button_holds_the_text_and_the_speech_call() -> None:
    out = speak_button_html("Pick up Ava at 2:30 PM.")
    assert json.dumps("Pick up Ava at 2:30 PM.") in out
    assert "speechSynthesis" in out
    assert 'words.lang = "en-CA"' in out
    assert "words.rate = 0.9" in out
    assert "Read it to me" in out


def test_speak_button_cannot_be_closed_early() -> None:
    out = speak_button_html("nasty </script><script>alert(1)</script>")
    assert out.count("</script>") == 1
    assert "<\\/script>" in out


# --------------------------------------------------------------------------
# 3. header_text and day_heading
# --------------------------------------------------------------------------


def test_header_text_reads_like_a_clock() -> None:
    assert header_text(datetime(2026, 10, 22, 13, 30)) == "Thursday, October 22 · 1:30 PM"


def test_day_heading_names_today_and_tomorrow() -> None:
    today = date(2026, 10, 21)
    assert day_heading(today, today) == "Today, Wednesday, October 21"
    assert day_heading(date(2026, 10, 22), today) == "Tomorrow, Thursday, October 22"
    assert day_heading(date(2026, 10, 26), today) == "Monday, October 26"


# --------------------------------------------------------------------------
# 4. week_view and other_reminders
# --------------------------------------------------------------------------


def test_week_view_covers_today_and_six_more_days(seeded_state: AppState) -> None:
    view = week_view(seeded_state, EVENING)
    assert len(view) == 7
    assert view[0][0] == "Today, Wednesday, October 21"
    assert view[1] == ("Tomorrow, Thursday, October 22", [AVA_LINE])
    assert view[5] == ("Monday, October 26", ["Nothing planned."])


def test_week_view_shows_a_change_and_leaves_the_other_day_alone(
    seeded_state: AppState,
) -> None:
    action = RescheduleEvent(
        id="act-test",
        source_message_id="m-michelle-1048",
        question="Pick up Ava at 2:30 PM this Thursday instead of 3:15 PM?",
        reason="Michelle texted.",
        created_at=EVENING,
        event_id="ev-ava",
        on_date=date(2026, 10, 22),
        new_start=time(14, 30),
        new_end=time(15, 0),
    )
    seeded_state.actions.append(action)
    store.approve(seeded_state, "act-test", EVENING)

    view = week_view(seeded_state, EVENING)
    assert view[1][1] == [AVA_MOVED]
    assert view[6] == ("Tuesday, October 27", [AVA_LINE])


def test_week_view_puts_a_reminder_on_its_day(seeded_state: AppState) -> None:
    reminder = next(item for item in seeded_state.reminders if item.id == "r-prescription")
    reminder.due = date(2026, 10, 23)
    reminder.due_time = time(16, 0)

    friday = week_view(seeded_state, EVENING)[2]
    assert friday[0] == "Friday, October 23"
    assert "To do: Pick up prescription Harbourview by 4:00 PM" in friday[1]


def test_other_reminders_lists_the_ones_without_a_day(seeded_state: AppState) -> None:
    entries = other_reminders(seeded_state)
    assert entries[0] == "Thank-you card for Linda (Reminders)"
    assert "Milk (Groceries)" in entries
    assert len(entries) == len(seeded_state.reminders)


def test_received_line_names_the_sender_and_the_time(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    assert received_line(message) == "Michelle · Wednesday 10:48 PM"


# --------------------------------------------------------------------------
# 5. The app runs
# --------------------------------------------------------------------------


def test_app_runs_at_the_default_clock(state_file: Path) -> None:
    at = start_app()
    assert not at.exception
    assert [title.value for title in at.title] == ["Hi Gloria"]
    assert at.subheader[0].value == "Wednesday, October 21 · 7:00 PM"
    assert shows(at, AVA_LINE)
    assert tab_labels(at)[0] == "Needs your OK (0)"


# --------------------------------------------------------------------------
# 6. Demo steps 2 to 4
# --------------------------------------------------------------------------


def test_demo_steps_two_to_four(state_file: Path) -> None:
    at = start_app()

    pick_preset(at, 1)
    at.button(key="check").click().run()
    assert not at.exception
    assert shows(at, "Pick up Ava at 2:30 PM this Thursday instead of 3:15 PM?")
    assert tab_labels(at)[0] == "Needs your OK (1)"

    action_id = pending(state_file)[0]["id"]
    at.button(key=f"yes-{action_id}").click().run()
    assert not at.exception
    ava = next(event for event in saved(state_file)["events"] if event["id"] == "ev-ava")
    assert ava["overrides"]["2026-10-22"]["start"] == "14:30:00"
    assert tab_labels(at)[0] == "Needs your OK (0)"

    week = week_view(store.load_state(state_file), at.session_state["now"])
    assert week[1][1] == [AVA_MOVED]
    assert week[6] == ("Tuesday, October 27", [AVA_LINE])

    pick_preset(at, 3)
    assert not at.exception
    assert shows(at, "Michelle asked: Pick up Ava at 2:30 PM today, not 3:15 PM.")
    alert_id = saved(state_file)["alerts"][0]["id"]
    assert f"alert-ok-{alert_id}" in button_keys(at)
    assert f"alert-yes-{alert_id}" not in button_keys(at)


# --------------------------------------------------------------------------
# 7. Demo step 5: the scam card
# --------------------------------------------------------------------------


def test_scam_card_is_red_and_holds_no_link(state_file: Path) -> None:
    at = start_app()
    pick_preset(at, 2)
    at.button(key="check").click().run()
    assert not at.exception

    waiting = pending(state_file)
    scam = next(action for action in waiting if action["kind"] == "scam_warning")
    pharmacy = next(action for action in waiting if action["kind"] == "set_reminder_due")

    assert at.get_by_key(f"scam-{scam['id']}") is not None
    assert {f"yes-{pharmacy['id']}", f"no-{pharmacy['id']}"} <= button_keys(at)

    for text in texts(at):
        assert "<a " not in text
        assert "canadapost-redelivery.example/pay" not in text

    at.button(key=f"gotit-{scam['id']}").click().run()
    assert not at.exception
    assert not any(action["id"] == scam["id"] for action in pending(state_file))
    assert f"gotit-{scam['id']}" not in button_keys(at)


# --------------------------------------------------------------------------
# 8. The alert lets her approve a change she missed
# --------------------------------------------------------------------------


def test_alert_can_approve_the_change(state_file: Path) -> None:
    at = start_app()
    pick_preset(at, 1)
    at.button(key="check").click().run()
    alert_id = saved(state_file)["alerts"][0]["id"]

    pick_preset(at, 3)
    assert f"alert-yes-{alert_id}" in button_keys(at)

    at.button(key=f"alert-yes-{alert_id}").click().run()
    assert not at.exception
    data = saved(state_file)
    ava = next(event for event in data["events"] if event["id"] == "ev-ava")
    assert ava["overrides"]["2026-10-22"]["start"] == "14:30:00"
    assert data["alerts"][0]["dismissed"] is True
    assert not shows(at, "Michelle asked")


# --------------------------------------------------------------------------
# 9. Ask me
# --------------------------------------------------------------------------


def test_ask_me_answers_with_the_fake_model(state_file: Path) -> None:
    at = start_app()
    at.button(key="ask-example-1").click().run()
    assert not at.exception
    assert at.session_state["chat"] == [
        {"role": "user", "content": "When do I get Noah?"},
        {"role": "assistant", "content": DEMO_ANSWER},
    ]
    assert shows(at, DEMO_ANSWER)


# --------------------------------------------------------------------------
# 10. Check a text
# --------------------------------------------------------------------------


def test_check_a_text_keeps_a_harmless_text_out_of_the_calendar(state_file: Path) -> None:
    case = eval_case("c18")
    at = start_app()
    before = tab_labels(at)[0]

    at.text_area(key="check-text").set_value(case["text"])
    at.selectbox(key="check-from").select("Someone not in my contacts")
    at.button(key="check-go").click().run()

    assert not at.exception
    assert tab_labels(at)[0] == before
    assert pending(state_file) == []
    assert shows(at, "Nothing to add to your calendar.")


def test_check_a_text_needs_some_text(state_file: Path) -> None:
    at = start_app()
    at.button(key="check-go").click().run()
    assert not at.exception
    assert [warning.value for warning in at.warning] == ["Paste a text first."]


# --------------------------------------------------------------------------
# 11. No key
# --------------------------------------------------------------------------


def test_missing_key_leaves_the_rest_of_the_app_working(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEADSUP_SKIP_DOTENV", "1")
    monkeypatch.setenv("HEADSUP_STATE", str(tmp_path / "state.json"))
    for name in (
        "LLM_PROVIDER",
        "HEADSUP_NOW",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    at = start_app()
    assert [caption.value for caption in at.caption] == ["AI model: not set up (see .env)"]

    at.button(key="check").click().run()
    assert not at.exception
    assert any("ANTHROPIC_API_KEY" in error.value for error in at.error)
    assert shows(at, AVA_LINE)


# --------------------------------------------------------------------------
# The sidebar's Check button
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("read", "waiting", "retries", "expected"),
    [
        (0, 0, 0, "No new texts."),
        (1, 1, 0, "Read 1 new text. 1 needs your OK."),
        (5, 3, 0, "Read 5 new texts. 3 need your OK."),
        (3, 0, 1, "Read 3 new texts. 0 need your OK. 1 text couldn't be read and will be tried again."),
        (0, 2, 2, "Read 0 new texts. 2 need your OK. 2 texts couldn't be read and will be tried again."),
    ],
)
def test_check_summary_counts_with_the_right_words(
    read: int, waiting: int, retries: int, expected: str
) -> None:
    assert check_summary(read, waiting, retries) == expected


def test_css_holds_no_markup() -> None:
    # st.html sanitizes its input: a "<" anywhere in the style text (even in a
    # comment) makes it drop the whole style block, and the page loses its large print.
    from headsup.ui.components import CSS

    assert "<" not in CSS


def test_alerts_go_away_two_hours_after_they_are_due() -> None:
    from headsup.models import Alert

    state = store.seed_state()
    state.alerts.append(
        Alert(id="al-1", at=datetime(2026, 10, 22, 13, 30), text="Michelle asked: …")
    )
    assert visible_alerts(state, datetime(2026, 10, 22, 13, 0)) == []
    assert [a.id for a in visible_alerts(state, datetime(2026, 10, 22, 13, 30))] == ["al-1"]
    assert [a.id for a in visible_alerts(state, datetime(2026, 10, 22, 15, 29))] == ["al-1"]
    assert visible_alerts(state, datetime(2026, 10, 22, 15, 30)) == []
    assert visible_alerts(state, datetime(2026, 10, 22, 19, 0)) == []


def test_a_second_check_says_there_is_nothing_new(state_file: Path) -> None:
    at = start_app()
    pick_preset(at, 1)
    at.button(key="check").click().run()
    assert shows(at, "Read 1 new text. 1 needs your OK.")

    at.button(key="check").click().run()
    assert shows(at, "No new texts.")


# --------------------------------------------------------------------------
# 12. Reset
# --------------------------------------------------------------------------


def test_reset_puts_the_phone_back_the_way_it_was(state_file: Path) -> None:
    at = start_app()
    pick_preset(at, 1)
    at.button(key="check").click().run()
    at.button(key="ask-example-0").click().run()
    assert at.session_state["chat"]

    at.button(key="reset").click().run()
    assert not at.exception

    data = saved(state_file)
    assert data["actions"] == []
    assert data["alerts"] == []
    assert data["processed_message_ids"] == []
    assert at.session_state["chat"] == []
    assert at.session_state["now"] == clock.DEMO_TIMES[1][1]
    assert shows(at, "Demo reset to Gloria's phone as it was.")
