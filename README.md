# Heads-Up: catching the texts Gloria misses

A large-print helper that reads the texts a busy grandmother doesn't see in time, turns plan changes and deadlines into calendar and reminder changes **she approves with one tap**, warns her about scam texts, and gives her one "Tomorrow" summary at the time she actually picks up her phone.

Built for the Side Quest *AI Agent Dev* project around the persona Gloria Benoit. All persona data is fictional.

![A card asking Gloria to approve a new pickup time, with Michelle's original text below it and big Yes and No thanks buttons](docs/screenshots/02-needs-your-ok.png)

## The problem

Gloria is 68, a retired teacher in Halifax. She picks up her granddaughter Ava on Tuesdays and Thursdays and her grandson Noah on Fridays. She would rather call than text, and she checks her phone about twice a day.

Her phone data shows what goes wrong:

- At **10:48 PM on Wednesday** her daughter texted: *can you get Ava at 2:30 tomorrow instead of 3:15? Early dismissal.* Gloria had already put her phone down. On Thursday the school called, and Ava waited at the office.
- Her calendar still said 3:15, with **no alert**. That text was competing with about 29 notifications a day, and 23 texts sat unread.
- **None of her 8 reminders has a date**, including the prescription the pharmacy says goes back to stock after Friday.
- A fake *"CanadaPost FINAL NOTICE … pay the $1.99 redelivery fee"* text arrived the same morning, and she wasn't sure it was fake.

The friction isn't that she misses texts. It's that nothing on her phone turns a change or a deadline into something that reminds her.

## What it does

The demo replays Gloria's Wednesday evening through Thursday evening with a presenter clock. Every screenshot below is from the app running with the real model (Claude Haiku 5.5).

**1. It reads her new texts and asks in plain words.** Michelle's late-night text becomes one question with one tap to answer (top of this page). Nothing changes until she taps **Yes**. Approving changes only that Thursday: the weekly pickup stays at 3:15.

<img src="docs/screenshots/03-my-week.png" alt="My week view: Thursday's Ava pickup shows 2:30 PM, changed from 3:15 PM; next Tuesday is still 3:15 PM" width="480">

**2. It sets a safety net.** The change arrived after her evening check, so Heads-Up also sets an alert an hour before the new time. This alert is the only thing it ever does without asking.

![Yellow alert banner: Michelle asked: Pick up Ava at 2:30 PM today, not 3:15 PM.](docs/screenshots/05-alert.png)

**3. It gives deadlines a date, and flags scams.** The pharmacy's third notice becomes "Due this Friday: Pick up prescription Harbourview. Add it to your reminders?" The Canada Post text gets a red card that says why it looks like a scam. The link is shown as plain text and can't be tapped.

<img src="docs/screenshots/04-deadline-and-scam.png" alt="A red scam card listing four warning signs above a card asking to add the prescription deadline to her reminders" width="480">

**4. It shows one summary at 7 PM**, when she actually looks at her phone, and can read it aloud. It's built straight from her calendar and reminders, so the model can't invent anything in it.

<img src="docs/screenshots/06-tomorrow-thursday.png" alt="Tomorrow summary for Friday: pick up Noah at 4:30 PM, last day for the prescription, and a scam warning, with a Read it to me button" width="480">

**5. It answers questions about her week** from her own calendar, reminders and texts only, and can't change anything. A family member can also paste any text into **Check a text** and get "Is this real? What do I need to do?" Below, a prompt-injection text is flagged and changes nothing.

<img src="docs/screenshots/07-ask-me.png" alt="Ask me tab: When do I get Noah? You pick up Noah on Friday, October 23, from 4:30 PM to 5:00 PM." width="480">

<img src="docs/screenshots/08-check-a-text.png" alt="Check a text tab: a pasted text saying SYSTEM: ignore all previous instructions is flagged as a scam, with Nothing to add to your calendar" width="480">

## What it won't do

- Send, reply to or forward messages, or call anyone.
- Change her calendar or reminders without her OK. The safety-net alert is the one exception, and it only adds a notification.
- Open links, pay for anything, or ask for card or bank details.
- Give medical advice. It tracks the pickup deadline only.
- Read a real iPhone. Apple doesn't let apps read iMessages, so the demo uses a copy of the persona's data. A real version would need her consent and a way to forward texts.

## How it works

Heads-Up is a **workflow, not an autonomous agent**. The model reads and proposes, plain code checks, and Gloria decides.

```
new text ──► rule-based scam check ──┐
         └─► model fills a fixed form ┴─► guardrails ──► question for Gloria ──► Yes ──► calendar / reminder
              (Pydantic-checked)                     └─► safety-net alert (only automatic step)
```

1. **Scam rules** look for an unknown sender, a link, a fee or payment, and pressure words. The model can add reasons, but it can't clear a text the rules flagged.
2. **The model** gets the text as quoted data, never as instructions, plus a list of her events and reminders. It fills a fixed form: category, plan changes, deadlines and scam reasons. Pydantic validates every answer before the app uses it.
3. **Guardrails in code** drop anything unsafe: unknown event ids, dates in the past or more than 60 days out, an end before the start, and any calendar change from a sender who isn't in her contacts or from a text flagged as a scam. A repeating event is only ever changed for a single day.
4. **Gloria decides.** Every change waits on a Yes. The 7 PM summary and the week view are built from her data with no model involved.

The model connector is provider-neutral: the Anthropic SDK by default, or the OpenAI SDK pointed at any OpenAI-compatible endpoint (OpenAI, DeepSeek, Groq, Gemini). A scripted fake model lets the tests and the demo run with no key.

**Accessibility:** a 21 px base font, buttons at least 56 px tall, dark text on white, white on dark green for Yes (about 6.6:1 contrast), one question per card, plain words, 12-hour times, and read-aloud through the browser's built-in speech.

## Results

- **333 offline tests** (pytest) cover the store, the summary, the scam rules, every guardrail, both model connectors (with mocked SDKs) and the screen. They never call a live model, and GitHub Actions runs them on every pull request.
- **Eval: 20/20** on 20 hand-labelled texts with `claude-haiku-5-5` (Nov 23, 2026). The texts cover plan changes, deadlines, scams (including a "Hi Mom, it's Michelle, new number" e-transfer scam the rules alone can't catch), Facebook noise, and two prompt-injection attempts. Both injection texts produced no calendar changes.
- **Caveats:** that's one run of 20 cases I wrote myself, and model output varies from run to run. The guardrails are proven by the offline tests, not by this eval.

## Run it yourself

You need Python 3.11. Everything installs inside the repo (`.venv/`, `.cache/`).

```bash
python -m venv .venv
scripts/with-env.sh python -m pip install -r requirements.txt
cp .env.example .env        # add your API key, or set LLM_PROVIDER=fake
scripts/with-env.sh python -m streamlit run streamlit_app.py
```

On Windows PowerShell, use `scripts/with-env.ps1` and `Copy-Item .env.example .env`.

- **No key?** Set `LLM_PROVIDER=fake` in `.env`. Scripted answers cover the demo texts.
- **Walk the demo:** in the sidebar, pick each *Demo time* in order and press *Check new messages* at 10:50 PM Wednesday and 10:05 AM Thursday. *Reset demo* starts over.
- **Tests:** `scripts/with-env.sh python -m pytest`
- **Eval** (live, costs a few cents): `scripts/with-env.sh python eval/run_eval.py`

Your key stays in `.env`, which git ignores. Nothing is deployed with it.

## Project layout

```
streamlit_app.py          the large-print screen
headsup/models.py         the data contract (Pydantic)
headsup/store.py          calendar, reminders, one-day changes, alerts
headsup/triage.py         model call + guardrails -> questions for Gloria
headsup/scam_rules.py     rule-based scam signs
headsup/digest.py         the 7 PM "Tomorrow" summary (no model)
headsup/chat.py           "Ask me", read-only
headsup/llm/              Anthropic, OpenAI-compatible and fake connectors
headsup/data/gloria/      the persona's texts, calendar, reminders, contacts
eval/                     20 labelled texts and the eval runner
tests/                    offline tests
```

## How it was built

I built it in 4 days, starting from a one-page pitch. I used Claude Code to write the spec, a step-by-step brief for each part, and a review of every step. Another coding agent wrote the code from those briefs. Each step went in as a pull request with the tests running in CI, and I reviewed and merged each one. Reviews caught real problems: a stale alert still showing in the evening, a scammer's "pay $1.99" leaking into a summary, styles that didn't apply, and duplicate scam warnings on the red card. Claude Code also used the subagent settings tested and adapted from my other projects.
