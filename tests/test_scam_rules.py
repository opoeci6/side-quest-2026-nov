"""The offline scam checks, including the link pattern's edge cases."""

from __future__ import annotations

from datetime import datetime

import pytest

from headsup import scam_rules
from headsup.models import AppState, Message
from headsup.scam_rules import (
    ASKS_FOR_MONEY,
    HAS_LINK,
    RUSHES_YOU,
    UNKNOWN_SENDER,
    is_suspicious,
    scam_signals,
)


def known_message(text: str) -> Message:
    """A text from Michelle, who is in Gloria's contacts."""
    return Message(
        id="m-test",
        sender="Michelle",
        contact_id="c-michelle",
        channel="sms",
        received_at=datetime(2026, 10, 22, 10, 0),
        text=text,
    )


def test_only_the_scam_message_is_suspicious(seeded_state: AppState) -> None:
    flagged = [
        message.id
        for message in seeded_state.messages
        if is_suspicious(scam_signals(message, seeded_state))
    ]
    assert flagged == ["m-scam-0914"]


def test_scam_message_has_every_signal_in_order(seeded_state: AppState) -> None:
    message = next(m for m in seeded_state.messages if m.id == "m-scam-0914")
    assert scam_signals(message, seeded_state) == [
        UNKNOWN_SENDER,
        HAS_LINK,
        ASKS_FOR_MONEY,
        RUSHES_YOU,
    ]


def test_known_messages_have_no_signals(seeded_state: AppState) -> None:
    for message in seeded_state.messages:
        if message.contact_id is not None:
            assert scam_signals(message, seeded_state) == [], message.id


def test_app_notices_are_never_people(seeded_state: AppState) -> None:
    notice = Message(
        id="m-app",
        sender="Solitaire",
        contact_id=None,
        channel="app",
        app="Solitaire",
        received_at=datetime(2026, 10, 22, 8, 0),
        text="URGENT final notice: pay the $9.99 fee at www.example.com now!",
    )
    assert scam_signals(notice, seeded_state) == []
    assert is_suspicious(scam_signals(notice, seeded_state)) is False


@pytest.mark.parametrize(
    "text",
    [
        "canadapost-redelivery.example/pay",
        "secure-visa-check.example",
        "https://x.org",
        "www.abc.com",
        "Go to HTTPS://Example.COM/path now",
    ],
)
def test_link_pattern_matches(seeded_state: AppState, text: str) -> None:
    assert HAS_LINK in scam_signals(known_message(text), seeded_state)


@pytest.mark.parametrize(
    "text",
    [
        "$1.99",
        "4:30",
        "e.g.",
        "Mr. Smith",
        "St. Brendan's",
        "Oct 23",
    ],
)
def test_link_pattern_ignores(seeded_state: AppState, text: str) -> None:
    assert HAS_LINK not in scam_signals(known_message(text), seeded_state)


@pytest.mark.parametrize(
    "text",
    [
        "Please pay the fee.",
        "I already paid.",
        "Payment is due.",
        "There is a small fee.",
        "Fees apply.",
        "Send an e-transfer.",
        "etransfer me the money",
        "Buy a gift card.",
        "Give me your card number.",
        "Ask your bank.",
        "We owe you a refund.",
        "It costs $20.",
        "It costs $ 20.",
    ],
)
def test_money_words_are_detected(seeded_state: AppState, text: str) -> None:
    assert ASKS_FOR_MONEY in scam_signals(known_message(text), seeded_state)


@pytest.mark.parametrize("text", ["She repaid me.", "A banking day.", "Thanks a lot."])
def test_money_words_need_whole_words(seeded_state: AppState, text: str) -> None:
    assert ASKS_FOR_MONEY not in scam_signals(known_message(text), seeded_state)


@pytest.mark.parametrize(
    "text",
    [
        "FINAL NOTICE",
        "This is urgent",
        "Call immediately",
        "Your account is suspended",
        "Suspension notice",
        "You are locked out",
        "Last chance",
        "Act now",
        "Reply within 24 hours",
    ],
)
def test_urgency_words_are_detected(seeded_state: AppState, text: str) -> None:
    assert RUSHES_YOU in scam_signals(known_message(text), seeded_state)


@pytest.mark.parametrize("text", ["See you soon.", "Nice weather.", "The cat is asleep."])
def test_calm_words_are_not_urgency(seeded_state: AppState, text: str) -> None:
    assert RUSHES_YOU not in scam_signals(known_message(text), seeded_state)


def test_known_contact_with_a_link_and_payment_words_is_not_suspicious(
    seeded_state: AppState,
) -> None:
    message = known_message("Here is the link www.example.com - please pay the fee.")
    signals = scam_signals(message, seeded_state)
    assert HAS_LINK in signals
    assert ASKS_FOR_MONEY in signals
    assert UNKNOWN_SENDER not in signals
    assert is_suspicious(signals) is False


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        ([], False),
        ([UNKNOWN_SENDER], False),
        ([UNKNOWN_SENDER, HAS_LINK], False),
        ([UNKNOWN_SENDER, ASKS_FOR_MONEY, RUSHES_YOU], True),
        ([UNKNOWN_SENDER, HAS_LINK, RUSHES_YOU], True),
        ([HAS_LINK, ASKS_FOR_MONEY, RUSHES_YOU], False),
    ],
)
def test_is_suspicious(signals: list[str], expected: bool) -> None:
    assert is_suspicious(signals) is expected


def test_unknown_sender_with_two_other_signals_is_suspicious(seeded_state: AppState) -> None:
    message = Message(
        id="m-test",
        sender="+1 (902) 555-0199",
        contact_id=None,
        channel="sms",
        received_at=datetime(2026, 10, 22, 10, 0),
        text="Urgent: pay the fee at www.example.com",
    )
    signals = scam_signals(message, seeded_state)
    assert signals == [UNKNOWN_SENDER, HAS_LINK, ASKS_FOR_MONEY, RUSHES_YOU]
    assert is_suspicious(signals) is True


def test_signal_wording() -> None:
    assert UNKNOWN_SENDER == "The sender isn't in your contacts."
    assert HAS_LINK == "It has a link."
    assert ASKS_FOR_MONEY == "It asks for money or payment details."
    assert RUSHES_YOU == "It tries to rush you."
    assert scam_rules.UNKNOWN_SENDER == UNKNOWN_SENDER
