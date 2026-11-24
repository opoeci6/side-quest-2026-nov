"""The persona data loads, validates and says exactly what it should."""

from __future__ import annotations

from datetime import date, datetime, time

from headsup import store
from headsup.models import AppState, SenderKind


def test_counts(seeded_state: AppState) -> None:
    assert len(seeded_state.contacts) == 5
    assert len(seeded_state.messages) == 9
    assert len(seeded_state.events) == 8
    assert len(seeded_state.reminders) == 8


def test_note_rows_are_skipped(seeded_state: AppState) -> None:
    ids = [
        *[contact.id for contact in seeded_state.contacts],
        *[message.id for message in seeded_state.messages],
        *[event.id for event in seeded_state.events],
        *[reminder.id for reminder in seeded_state.reminders],
    ]
    assert not [item_id for item_id in ids if item_id.startswith("_")]


def test_contacts(seeded_state: AppState) -> None:
    contacts = {contact.id: contact for contact in seeded_state.contacts}
    assert list(contacts) == ["c-michelle", "c-ray", "c-linda", "c-pharmacy", "c-school"]
    michelle = contacts["c-michelle"]
    assert michelle.name == "Michelle"
    assert michelle.kind is SenderKind.family
    assert michelle.relation == "daughter"
    assert michelle.phone == "+1 (902) 555-0111"
    assert contacts["c-ray"].relation == "husband"
    assert contacts["c-linda"].name == "Linda Arsenault"
    assert contacts["c-pharmacy"].kind is SenderKind.business
    assert contacts["c-pharmacy"].relation == "pharmacy"
    assert contacts["c-school"].relation == "Ava's school"


def test_message_ids_and_order(seeded_state: AppState) -> None:
    assert [message.id for message in seeded_state.messages] == [
        "m-michelle-1048",
        "m-solitaire-0800",
        "m-facebook-0830",
        "m-scam-0914",
        "m-pharmacy-1000",
        "m-michelle-call-1447",
        "m-michelle-1452",
        "m-michelle-1558",
        "m-weather-1605",
    ]


def test_michelle_message(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-michelle-1048")
    assert message is not None
    assert message.sender == "Michelle"
    assert message.contact_id == "c-michelle"
    assert message.channel == "sms"
    assert message.app is None
    assert message.received_at == datetime(2026, 10, 21, 22, 48)
    assert message.text == (
        "Mom can you get Ava at 2:30 tomorrow instead of 3:15? "
        "Early dismissal, PD afternoon \U0001f60a thank you!!"
    )


def test_scam_message(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-scam-0914")
    assert message is not None
    assert message.sender == "+1 (902) 555-0148"
    assert message.contact_id is None
    assert message.channel == "sms"
    assert message.app is None
    assert message.received_at == datetime(2026, 10, 22, 9, 14)
    assert message.text == (
        "CanadaPost FINAL NOTICE: Your parcel will be returned to sender. "
        "Pay the $1.99 redelivery fee: canadapost-redelivery.example/pay"
    )


def test_pharmacy_message(seeded_state: AppState) -> None:
    message = store.find_message(seeded_state, "m-pharmacy-1000")
    assert message is not None
    assert message.sender == "Harbourview Pharmacy"
    assert message.contact_id == "c-pharmacy"
    assert message.channel == "sms"
    assert message.received_at == datetime(2026, 10, 22, 10, 0)
    assert message.text == (
        "3rd reminder: Your prescription is ready for pickup. "
        "Please pick up by Fri Oct 23 or it will be returned to stock."
    )


def test_remaining_message_texts(seeded_state: AppState) -> None:
    texts = {message.id: message.text for message in seeded_state.messages}
    assert texts["m-solitaire-0800"] == "Your Daily Challenge is ready! \U0001f0cf"
    assert texts["m-facebook-0830"] == "Linda Arsenault and 4 others commented on your photo."
    assert texts["m-michelle-call-1447"] == "Missed Call (2)"
    assert texts["m-michelle-1452"] == "Mom?? School called, Ava's waiting at the office"
    assert texts["m-michelle-1558"] == (
        "Thanks for grabbing her. Did you not see my text last night? \U0001f615"
    )
    assert texts["m-weather-1605"] == "Rain starting around 5 PM."


def test_app_messages_carry_an_app_name(seeded_state: AppState) -> None:
    apps = {
        message.id: message.app
        for message in seeded_state.messages
        if message.channel == "app"
    }
    assert apps == {
        "m-solitaire-0800": "Solitaire",
        "m-facebook-0830": "Facebook",
        "m-weather-1605": "Weather",
    }


def test_message_contacts_resolve(seeded_state: AppState) -> None:
    for message in seeded_state.messages:
        contact = store.contact_for(seeded_state, message)
        if message.contact_id is None:
            assert contact is None
        else:
            assert contact is not None
            assert contact.id == message.contact_id


def test_events(seeded_state: AppState) -> None:
    assert [event.id for event in seeded_state.events] == [
        "ev-hair",
        "ev-ray-eye",
        "ev-choir",
        "ev-ava",
        "ev-noah",
        "ev-garden",
        "ev-church",
        "ev-family-lunch",
    ]
    hair = store.find_event(seeded_state, "ev-hair")
    assert hair is not None
    assert hair.title == "Hair appointment"
    assert hair.location is None
    assert hair.date == date(2026, 10, 19)
    assert (hair.start, hair.end) == (time(13, 30), time(14, 30))
    assert hair.repeat_weekdays == []

    ava = store.find_event(seeded_state, "ev-ava")
    assert ava is not None
    assert ava.title == "Pick up Ava"
    assert ava.location == "Oakwood Elementary, front doors"
    assert ava.date is None
    assert ava.repeat_weekdays == [1, 3]
    assert (ava.start, ava.end) == (time(15, 15), time(15, 45))
    assert ava.calendar == "Gloria"
    assert ava.alert_minutes_before is None
    assert ava.overrides == {}

    noah = store.find_event(seeded_state, "ev-noah")
    assert noah is not None
    assert noah.title == "Pick up Noah"
    assert noah.location is None
    assert noah.repeat_weekdays == [4]
    assert (noah.start, noah.end) == (time(16, 30), time(17, 0))

    church = store.find_event(seeded_state, "ev-church")
    assert church is not None
    assert church.location == "St. Brendan's"
    assert church.date == date(2026, 10, 25)
    lunch = store.find_event(seeded_state, "ev-family-lunch")
    assert lunch is not None
    assert lunch.location == "Michelle's house"
    assert lunch.date == date(2026, 10, 25)


def test_every_event_has_no_alert(seeded_state: AppState) -> None:
    assert all(event.alert_minutes_before is None for event in seeded_state.events)


def test_reminders_are_open_and_undated(seeded_state: AppState) -> None:
    assert [reminder.id for reminder in seeded_state.reminders] == [
        "r-linda-card",
        "r-ava-costume",
        "r-prescription",
        "r-parcel",
        "r-apples",
        "r-oats",
        "r-brown-sugar",
        "r-milk",
    ]
    for reminder in seeded_state.reminders:
        assert reminder.done is False
        assert reminder.due is None
        assert reminder.due_time is None
        assert reminder.alert_at is None


def test_reminder_details(seeded_state: AppState) -> None:
    card = store.find_reminder(seeded_state, "r-linda-card")
    assert card is not None
    assert card.title == "Thank-you card for Linda"
    assert card.list == "Reminders"
    assert card.notes == "For the casserole"
    costume = store.find_reminder(seeded_state, "r-ava-costume")
    assert costume is not None
    assert costume.title == "Ava's Halloween costume, ask Michelle what size"
    assert costume.notes is None
    apples = store.find_reminder(seeded_state, "r-apples")
    assert apples is not None
    assert apples.title == "Apples (6) for crisp"
    assert apples.list == "Groceries"
    assert [r.list for r in seeded_state.reminders].count("Groceries") == 4


def test_seeded_state_is_independent(seeded_state: AppState) -> None:
    seeded_state.events.clear()
    assert len(store.seed_state().events) == 8
