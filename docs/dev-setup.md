# Dev setup

Everything stays inside the repo: the Python environment in `.venv/`, caches in `.cache/`, any extra tools in `.tools/`. Nothing is installed system-wide.

## First time

Needs Python 3.11 on PATH.

```bash
python -m venv .venv
scripts/with-env.sh python -m pip install -r requirements.txt
cp .env.example .env    # then fill in your API key
```

PowerShell:

```powershell
python -m venv .venv
scripts/with-env.ps1 python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## Every command

Run commands through the wrapper so the venv and local caches are used. Shells don't keep state between calls, so use it every time.

```bash
scripts/with-env.sh python -m pytest                 # offline tests, no API calls
scripts/with-env.sh python -m streamlit run streamlit_app.py
scripts/with-env.sh python eval/run_eval.py          # live LLM eval, costs a few cents
scripts/with-env.sh python scripts/render_pdf.py docs/pitch.md
```

## LLM settings (`.env`)

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `anthropic` (Anthropic SDK) or `openai` (any OpenAI-compatible endpoint) |
| `LLM_MODEL` | Model id, e.g. `claude-haiku-5-5`, or the id your OpenAI-compatible provider uses |
| `LLM_BASE_URL` | Only for `openai`, e.g. `https://api.deepseek.com` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Your key. Stays in `.env`, which git ignores. |
| `HEADSUP_NOW` | Optional fixed demo clock, e.g. `2026-10-21T19:00` |

Use test data only. The persona data in `headsup/data/gloria/` is fictional; don't put your own messages, calendar or email into the app or its tests.
