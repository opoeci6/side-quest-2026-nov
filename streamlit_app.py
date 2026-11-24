"""Heads-Up for Gloria: the large-print screen she taps on.

This module is wiring and layout only. Everything it shows comes from
``store``, ``digest``, ``triage`` and ``chat``; everything it draws comes from
``headsup.ui.components``. Nothing here reads the real clock except through
``clock``.
"""

from __future__ import annotations

import datetime as dt
import os

import streamlit as st
from dotenv import load_dotenv

from headsup import chat as chat_mod
from headsup import clock, digest as digest_mod, store, triage
from headsup.llm import LLM, LLMConfigError, LLMError, get_llm
from headsup.models import AppState, Message, ProposedAction, ScamWarning, TriageOutcome
from headsup.ui.components import (
    CSS,
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

CUSTOM_TIME = "Custom time"
SOMEONE_NEW = "Someone not in my contacts"
UNKNOWN_SENDER = "Unknown number"
CANNOT_APPROVE = "That change can't be made any more. Tap No thanks to clear it."
RESET_NOTICE = "Demo reset to Gloria's phone as it was."
SCAM_BANNER = "This looks like a scam. Don't tap any link or reply."
NOT_SET_UP = "not set up (see .env)"
NOTICE_CLASSES = {"success": "hu-notice-success", "info": "hu-notice-info"}


# --------------------------------------------------------------------------
# Startup and session
# --------------------------------------------------------------------------


def setup_page() -> None:
    """Set the page up, load the developer's .env unless told not to, add the CSS."""
    st.set_page_config(page_title="Heads-Up for Gloria", page_icon="🔔", layout="centered")
    if os.environ.get("HEADSUP_SKIP_DOTENV") != "1":
        load_dotenv(store.REPO_ROOT / ".env")
    st.html(f"<style>{CSS}</style>")


def start_session() -> None:
    """Give the session its clock, chat history, notice and last check."""
    if "now" not in st.session_state:
        st.session_state["now"] = (
            clock.now() if os.environ.get("HEADSUP_NOW") else clock.DEMO_TIMES[0][1]
        )
    if "chat" not in st.session_state:
        st.session_state["chat"] = []
    if "notice" not in st.session_state:
        st.session_state["notice"] = None
    if "checked" not in st.session_state:
        st.session_state["checked"] = None


def model() -> LLM:
    """Return the model connector, building it the first time it is needed."""
    if "llm" not in st.session_state:
        st.session_state["llm"] = get_llm()
    return st.session_state["llm"]


def show_notice() -> None:
    """Show the one-shot notice at the top of the page, then clear it."""
    notice = st.session_state["notice"]
    if notice is None:
        return
    st.session_state["notice"] = None
    kind, text = notice
    if kind == "error":
        st.error(text)
        return
    show(text_html(text, NOTICE_CLASSES.get(kind, "hu-text")))


def show(html_text: str) -> None:
    """Draw one already-escaped block of HTML."""
    st.markdown(html_text, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Sidebar: the presenter's controls
# --------------------------------------------------------------------------


def apply_preset() -> None:
    """Move the demo clock to the preset the presenter picked."""
    chosen = st.session_state["clock-preset"]
    for label, moment in clock.DEMO_TIMES:
        if label == chosen:
            st.session_state["now"] = moment
            return


def apply_custom_date() -> None:
    """Keep the time of day and take the new date."""
    st.session_state["now"] = dt.datetime.combine(
        st.session_state["clock-date"], st.session_state["now"].time()
    )


def apply_custom_time() -> None:
    """Keep the date and take the new time of day."""
    st.session_state["now"] = dt.datetime.combine(
        st.session_state["now"].date(), st.session_state["clock-time"]
    )


def preset_index(now: dt.datetime) -> int:
    """Return the preset that matches ``now``, or the custom entry."""
    for index, (_, moment) in enumerate(clock.DEMO_TIMES):
        if moment == now:
            return index
    return len(clock.DEMO_TIMES)


def clock_controls(now: dt.datetime) -> None:
    """Draw the demo-time picker and, for a custom time, its two inputs."""
    labels = [label for label, _ in clock.DEMO_TIMES] + [CUSTOM_TIME]
    st.selectbox(
        "Demo time",
        labels,
        index=preset_index(now),
        key="clock-preset",
        on_change=apply_preset,
    )
    if st.session_state["clock-preset"] != CUSTOM_TIME:
        return
    if "clock-date" not in st.session_state:
        st.session_state["clock-date"] = now.date()
    if "clock-time" not in st.session_state:
        st.session_state["clock-time"] = now.time()
    st.date_input("Date", key="clock-date", on_change=apply_custom_date)
    st.time_input(
        "Time",
        key="clock-time",
        step=300,
        format="12h",
        on_change=apply_custom_time,
    )


def check_notice(state: AppState, outcomes: list[TriageOutcome]) -> tuple[str, str]:
    """Return the notice that says what the last check found."""
    retries = sum(1 for outcome in outcomes if outcome.summary == triage.RETRY_SUMMARY)
    read = len(outcomes) - retries
    text = check_summary(read, len(store.pending_actions(state)), retries)
    return ("info" if read == 0 and retries == 0 else "success"), text


def check_messages(state: AppState, now: dt.datetime) -> None:
    """Read the texts that have arrived and keep what triage proposed."""
    try:
        llm = model()
        with st.spinner("Reading new texts…"):
            outcomes = triage.check_new_messages(state, now, llm)
    except LLMConfigError as exc:
        st.session_state["notice"] = ("error", str(exc))
        st.rerun()
        return
    store.save_state(state)
    st.session_state["notice"] = check_notice(state, outcomes)
    st.rerun()


def reset_demo() -> None:
    """Put Gloria's phone back the way it was and empty the chat."""
    store.reset_state()
    st.session_state["chat"] = []
    st.session_state["checked"] = None
    st.session_state["notice"] = ("info", RESET_NOTICE)
    st.rerun()


def sidebar(state: AppState, now: dt.datetime) -> None:
    """Draw the presenter's controls."""
    with st.sidebar:
        st.header("Demo controls (for the presenter)", anchor=False)
        clock_controls(now)
        if st.button("Check new messages", key="check"):
            check_messages(state, now)
        if st.button("Reset demo", key="reset"):
            reset_demo()
        try:
            st.caption(f"AI model: {model().name}")
        except LLMConfigError:
            st.caption(f"AI model: {NOT_SET_UP}")


# --------------------------------------------------------------------------
# Main area
# --------------------------------------------------------------------------


def alerts(state: AppState, now: dt.datetime) -> None:
    """Draw the safety-net banners that are due."""
    for alert in visible_alerts(state, now):
        with st.container(border=True, key=f"alert-{alert.id}"):
            show(text_html(alert.text, "hu-alert"))
            action = store.find_action(state, alert.action_id) if alert.action_id else None
            if action is not None and action.status == "pending":
                st.caption("This change isn't on your calendar yet.")
                if st.button("Yes, update my calendar", key=f"alert-yes-{alert.id}"):
                    store.approve(state, alert.action_id, now)
                    store.dismiss_alert(state, alert.id)
                    store.save_state(state)
                    st.rerun()
            if st.button("OK", key=f"alert-ok-{alert.id}"):
                store.dismiss_alert(state, alert.id)
                store.save_state(state)
                st.rerun()


def source_text(state: AppState, action: ProposedAction) -> None:
    """Draw the text message a proposal came from."""
    message = store.find_message(state, action.source_message_id)
    if message is None:
        return
    show(text_html(received_line(message), "hu-caption"))
    show(render_message_html(message.text))


def scam_card(state: AppState, now: dt.datetime, action: ScamWarning) -> None:
    """Draw the signals, the advice and the one button a scam card needs."""
    show(text_html("Why it looks like a scam:", "hu-label"))
    for signal in action.signals:
        show(text_html(signal, "hu-signal"))
    show(text_html(action.advice, "hu-advice"))
    if st.button("Got it", key=f"gotit-{action.id}"):
        store.approve(state, action.id, now)
        store.save_state(state)
        st.rerun()


def choice_buttons(state: AppState, now: dt.datetime, action: ProposedAction) -> None:
    """Draw Yes and No thanks, and apply whichever she taps."""
    left, right = st.columns(2)
    if left.button("Yes", key=f"yes-{action.id}", type="primary", width="stretch"):
        try:
            store.approve(state, action.id, now)
        except ValueError:
            st.session_state["notice"] = ("error", CANNOT_APPROVE)
            st.rerun()
        store.save_state(state)
        st.rerun()
    if right.button("No thanks", key=f"no-{action.id}", width="stretch"):
        store.reject(state, action.id)
        store.save_state(state)
        st.rerun()


def needs_ok_tab(state: AppState, now: dt.datetime) -> None:
    """Draw one card per proposal that is still waiting for her."""
    pending = store.pending_actions(state)
    if not pending:
        show(text_html("Nothing needs your OK right now."))
        return
    for action in pending:
        scam = isinstance(action, ScamWarning)
        key = f"scam-{action.id}" if scam else f"card-{action.id}"
        with st.container(border=True, key=key):
            show(text_html(action.question, "hu-question"))
            show(text_html(action.reason, "hu-reason"))
            source_text(state, action)
            if isinstance(action, ScamWarning):
                scam_card(state, now, action)
            else:
                choice_buttons(state, now, action)


def tomorrow_tab(state: AppState, now: dt.datetime) -> None:
    """Draw tomorrow's summary and the button that reads it out loud."""
    summary = digest_mod.build_digest(state, now)
    st.subheader(day_heading(summary.for_date, now.date()), anchor=False)
    sections = (
        ("What changed", summary.changes, False),
        ("Your plan", summary.plan, True),
        ("To do", summary.deadlines, False),
        ("Be careful", summary.warnings, False),
    )
    for title, lines, always in sections:
        if not lines and not always:
            continue
        st.subheader(title, anchor=False)
        for line in lines:
            show(text_html(line))
    # The page is our own fixed template; the digest text sits in it JSON-encoded.
    st.iframe(speak_button_html(digest_mod.digest_to_speech(summary)), height=90)


def my_week_tab(state: AppState, now: dt.datetime) -> None:
    """Draw today and the six days after it, then the undated reminders."""
    for heading, lines in week_view(state, now):
        st.subheader(heading, anchor=False)
        for line in lines:
            show(text_html(line))
    with st.expander("Other reminders"):
        entries = other_reminders(state)
        if not entries:
            show(text_html("No other reminders."))
        for entry in entries:
            show(text_html(entry))


def remember(question: str, reply: str) -> None:
    """Add one question and its answer to the chat history."""
    st.session_state["chat"].append({"role": "user", "content": question})
    st.session_state["chat"].append({"role": "assistant", "content": reply})


def ask(question: str, state: AppState, now: dt.datetime) -> None:
    """Answer one question and keep both turns. Changes nothing else."""
    try:
        llm = model()
        reply = chat_mod.answer(question, st.session_state["chat"], state, now, llm)
    except LLMConfigError as exc:
        st.error(str(exc))
        return
    except LLMError as exc:
        remember(question, f"Sorry, I couldn't answer just now. {exc}")
        st.rerun()
        return
    remember(question, reply)
    st.rerun()


def ask_tab(state: AppState, now: dt.datetime) -> None:
    """Draw the chat history, two example questions and the question box."""
    for turn in st.session_state["chat"]:
        with st.chat_message(turn["role"]):
            show(text_html(turn["content"]))
    if st.button("What do I have tomorrow?", key="ask-example-0"):
        ask("What do I have tomorrow?", state, now)
    if st.button("When do I get Noah?", key="ask-example-1"):
        ask("When do I get Noah?", state, now)
    typed = st.chat_input("Ask about your week", key="ask")
    if typed:
        ask(typed, state, now)


def checked_summary(outcome: TriageOutcome) -> dict[str, object]:
    """Return the four things the Check a text tab remembers about a check."""
    signals = [
        signal
        for action in outcome.actions
        if isinstance(action, ScamWarning)
        for signal in action.signals
    ]
    return {
        "summary": outcome.summary,
        "signals": signals,
        "new": len([a for a in outcome.actions if not isinstance(a, ScamWarning)]),
        "scam": any(isinstance(a, ScamWarning) for a in outcome.actions),
    }


def check_pasted(text: str, who: str, state: AppState, now: dt.datetime) -> None:
    """Read a text she pasted and keep whatever triage makes of it."""
    try:
        llm = model()
    except LLMConfigError as exc:
        st.error(str(exc))
        return
    contact = next((item for item in state.contacts if item.name == who), None)
    message = Message(
        id=store.new_id("pasted"),
        sender=contact.name if contact is not None else UNKNOWN_SENDER,
        contact_id=contact.id if contact is not None else None,
        channel="sms",
        received_at=now,
        text=text,
    )
    try:
        outcome = triage.triage_message(message, state, now, llm)
    except LLMError as exc:
        st.error(str(exc))
        return
    state.messages.append(message)
    store.add_outcome(state, outcome)
    store.save_state(state)
    st.session_state["checked"] = checked_summary(outcome)
    st.rerun()


def show_checked() -> None:
    """Draw what the last pasted text turned out to be."""
    checked = st.session_state["checked"]
    if not checked:
        return
    show(text_html(str(checked["summary"])))
    if checked["scam"]:
        show(text_html(SCAM_BANNER, "hu-alert"))
        for signal in checked["signals"]:
            show(text_html(str(signal), "hu-signal"))
    new = int(checked["new"])
    if new > 0:
        show(text_html(f"Added {new} to Needs your OK."))
    else:
        show(text_html("Nothing to add to your calendar."))


def check_text_tab(state: AppState, now: dt.datetime) -> None:
    """Draw the paste-a-text form and the answer to the last one."""
    show(text_html("Got a text you're not sure about? Paste it here."))
    text = st.text_area("The text", key="check-text")
    names = [contact.name for contact in state.contacts] + [SOMEONE_NEW]
    who = st.selectbox("Who is it from?", names, key="check-from")
    if st.button("Check it", key="check-go"):
        if text.strip():
            check_pasted(text, who, state, now)
        else:
            st.warning("Paste a text first.")
    show_checked()


def main() -> None:
    """Draw the whole page from the saved state."""
    setup_page()
    start_session()
    now = st.session_state["now"]
    state = store.load_state()
    sidebar(state, now)
    st.title("Hi Gloria", anchor=False)
    st.subheader(header_text(now), anchor=False)
    show_notice()
    alerts(state, now)
    tabs = st.tabs(
        [
            f"Needs your OK ({len(store.pending_actions(state))})",
            "Tomorrow",
            "My week",
            "Ask me",
            "Check a text",
        ]
    )
    with tabs[0]:
        needs_ok_tab(state, now)
    with tabs[1]:
        tomorrow_tab(state, now)
    with tabs[2]:
        my_week_tab(state, now)
    with tabs[3]:
        ask_tab(state, now)
    with tabs[4]:
        check_text_tab(state, now)


main()
