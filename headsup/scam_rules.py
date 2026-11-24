"""Cheap, offline checks for texts that look like a scam.

The result is only a hint for the cards Gloria sees; the LLM may also flag a
message that these rules miss.
"""

from __future__ import annotations

import re

from headsup.models import AppState, Message
from headsup.store import contact_for

UNKNOWN_SENDER = "The sender isn't in your contacts."
HAS_LINK = "It has a link."
ASKS_FOR_MONEY = "It asks for money or payment details."
RUSHES_YOU = "It tries to rush you."

_LINK_RE = re.compile(
    r"\b(?:https?://\S+|www\.\S+|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?)",
    re.IGNORECASE,
)

_MONEY_WORDS = (
    "pay",
    "paid",
    "payment",
    "fee",
    "fees",
    "e-transfer",
    "etransfer",
    "gift card",
    "card number",
    "bank",
    "refund",
)
_MONEY_RE = re.compile(
    r"\$\s?\d|\b(?:" + "|".join(re.escape(word) for word in _MONEY_WORDS) + r")\b",
    re.IGNORECASE,
)

_URGENCY_RE = re.compile(
    r"final notice|urgent|immediately|suspended|suspension|locked|last chance"
    r"|act now|within 24",
    re.IGNORECASE,
)


def scam_signals(message: Message, state: AppState) -> list[str]:
    """Return the plain-words warning signs in one message, in a fixed order."""
    if message.channel == "app":
        return []
    signals: list[str] = []
    if contact_for(state, message) is None:
        signals.append(UNKNOWN_SENDER)
    if _LINK_RE.search(message.text):
        signals.append(HAS_LINK)
    if _MONEY_RE.search(message.text):
        signals.append(ASKS_FOR_MONEY)
    if _URGENCY_RE.search(message.text):
        signals.append(RUSHES_YOU)
    return signals


def is_suspicious(signals: list[str]) -> bool:
    """Say whether the signals add up to a likely scam."""
    if UNKNOWN_SENDER not in signals:
        return False
    others = [signal for signal in (HAS_LINK, ASKS_FOR_MONEY, RUSHES_YOU) if signal in signals]
    return len(others) >= 2
