# Heads-Up: catching the texts Gloria misses

**AI Agent Dev pitch · Persona: Gloria Benoit**

## Who it's for

Gloria Benoit, 68, a retired Grade 3 teacher in Halifax. She picks up her granddaughter Ava from school on Tuesdays and Thursdays and her grandson Noah from daycare on Fridays, and she drives her husband Ray to his appointments. She would rather call than text.

## The problem

When plans change by text, Gloria doesn't find out in time, and nothing on her phone turns the change into a reminder.

## What her phone shows

- **The missed pickup.** At 10:48 PM on Wednesday, her daughter Michelle asked by text if she could get Ava at 2:30 the next day instead of 3:15 (early dismissal). Gloria never saw it. On Thursday at 2:52 PM: *"School called, Ava's waiting at the office."* Later: *"Did you not see my text last night?"*
- **She rarely looks, and texts get buried.** She picks up her phone about twice a day (on Wednesday, first at 7:01&nbsp;PM) and gets about 29 notifications a day, 63 of them from Facebook last week. 23 texts sit unread.
- **Nothing reminds her.** Her "Pick up Ava" event still says 3:15 and has no alert. None of her 8 reminders has a date, including "Pick up prescription Harbourview", even though the pharmacy's third notice says it goes back to stock after Friday.
- **A scam slips in.** A fake *"CanadaPost FINAL NOTICE … pay the $1.99 redelivery fee"* text arrived the same morning, and her reminder "Ask Michelle about the parcel" shows she isn't sure it's fake.

## What Heads-Up will do

- Read her new texts and pick out the ones that change her plans or set a deadline.
- Ask in plain words, for example *"Pick up Ava at 2:30 this Thursday instead of 3:15?"*, and update her calendar or reminder only when she taps **Yes**.
- If a change arrives after her evening check, set an alert one hour before the new time.
- At 7 PM, when she actually looks at her phone, show one large-print "Tomorrow" summary it can read aloud.
- Flag texts that look like scams, and answer simple questions about her week ("When do I get Noah?") from her own data.

## What it won't do

- Send messages or call anyone for her, or change anything in her calendar or reminders without her OK.
- Open links, pay for anything, ask for card details, or give medical advice.
- Read her real iPhone (Apple doesn't allow it). The demo uses a copy of the persona's data.

## Tools

Python and Streamlit (a large-print web app). An LLM through the Anthropic API or any OpenAI-compatible API, using a low-cost model such as Claude Haiku 5.5, with API keys kept on my machine. Pydantic checks every model answer before the app acts on it. A local calendar store, with an optional sync to a Google Calendar test account if time allows. pytest.

## How I'll show it works

A replay of Gloria's Wednesday and Thursday: Michelle's 10:48 PM text comes in, Heads-Up proposes the 2:30 pickup and sets a 1:30 PM alert, and once Gloria taps Yes her calendar shows 2:30. Thursday's 7 PM summary warns that Friday is the last day for the prescription. A test set of about 20 labelled texts (plan changes, deadlines, scams, Facebook noise and a text with hidden instructions) measures how often the agent gets it right.
