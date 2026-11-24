#!/usr/bin/env bash
# Run one command with the project-local toolchain: .venv first on PATH,
# caches under .cache/. Nothing is installed or configured system-wide.
# Usage: scripts/with-env.sh <command> [args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Native Windows programs need Windows paths in env vars.
if command -v cygpath >/dev/null 2>&1; then ROOT_NATIVE="$(cygpath -w "$ROOT")"; else ROOT_NATIVE="$ROOT"; fi

if [ -d "$ROOT/.venv/Scripts" ]; then VENV_BIN="$ROOT/.venv/Scripts"; else VENV_BIN="$ROOT/.venv/bin"; fi
if [ ! -d "$VENV_BIN" ]; then
  echo "with-env: no .venv found. Create it first: python -m venv .venv (see docs/dev-setup.md)" >&2
  exit 1
fi

export VIRTUAL_ENV="$ROOT_NATIVE/.venv"
export PATH="$VENV_BIN:$ROOT/.tools/bin:$ROOT/.tools:$PATH"
export PIP_CACHE_DIR="$ROOT_NATIVE/.cache/pip"
export XDG_CACHE_HOME="$ROOT_NATIVE/.cache"
export PYTHONUTF8=1
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

if [ "$#" -eq 0 ]; then
  echo "usage: scripts/with-env.sh <command> [args...]" >&2
  exit 2
fi
exec "$@"
