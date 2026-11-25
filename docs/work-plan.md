# Work plan

**Goal for Fri Nov 27:** a working large-print app that replays Gloria's Oct 21–22. It turns Michelle's late-night text into a one-tap calendar change with a safety-net alert, gives the pharmacy deadline a date, flags the Canada Post scam, and shows a 7 PM "Tomorrow" summary. Code goes on GitHub with tests and a measured eval score.

## Milestones

| Day | Work | Done when |
|---|---|---|
| Mon Nov 23 | Pitch, design spec, data contract, dev setup | Pitch submitted; design spec and `headsup/models.py` ready |
| Tue Nov 24 | **A** Gloria's data, calendar store, "Tomorrow" summary, scam rules · **B** LLM connectors (Anthropic and OpenAI-compatible) | Offline tests pass for both |
| Tue–Wed | **C** Message triage with guardrails, "Ask me" chat, 20-case eval | Tests pass; live eval ≥ 90% |
| Wed Nov 25 | **D** Streamlit app: Needs your OK, Tomorrow (read aloud), My week, Ask me, Check a text | Demo script runs end to end |
| Thu Nov 26 | Fixes from the full demo; stretch: pickup alerts, Google Calendar test-account sync | Demo is reliable |
| Fri Nov 27 | Showcase: README, screenshots, screen recording, eval results, submit | Submitted |

## Hours

About 15 hours for the week, planned as follows:

| Module | Planned hours |
|---|---|
| Pitch (research the persona, write and submit) | 3 |
| Work plan and design spec | 2 |
| Build (steps A–D, reviews, fixes, eval) | 6 |
| Showcase (README, screenshots, recording, submission) | 4 |

## Tools

- **Language and app:** Python 3.11, Streamlit for the large-print screen, Pydantic to check every model answer.
- **Model:** Claude Haiku 5.5 through the Anthropic SDK by default. The OpenAI SDK covers any OpenAI-compatible provider. Keys stay in a local `.env`.
- **Testing:** pytest with a scripted fake model, so tests need no network. A 20-case eval runs against the real model.
- **Code and CI:** Git and GitHub, one pull request per step, with GitHub Actions running the tests on each one.
- **AI help:** Claude Code writes the design and step-by-step handoffs and reviews each step. A coding agent writes the code from those handoffs. I run the agent, review the results, and do the commits and merges myself.

## How I'll check it

- Offline tests (pytest) for the store, summary, scam rules, guardrails and both LLM connectors, with no API calls.
- A 20-text eval run against the real model: plan changes, deadlines, scams, chit-chat and two prompt-injection attempts.
- A scripted 7-step demo in the browser, each step with an expected result. It replays Wednesday 7 PM through Thursday 7 PM.

## Guardrails I'm committing to

- Nothing changes in her calendar or reminders until she taps Yes. The only automatic action is an alert.
- Texts from unknown senders never create calendar or reminder changes. A rule-based scam check can't be overruled by the model.
- Links in suspicious texts are never clickable. The app never sends messages, pays, or asks for card details.
- API keys stay in a local `.env`. Only fictional persona data is used.

## What I'll cut if time runs short

1. Google Calendar sync
2. The "alert before every pickup" proposal
3. The "Check a text" tab

