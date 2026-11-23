"""The shared data contract builds on its own."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_app_state_builds_without_importing_store() -> None:
    # A fresh interpreter, because conftest already imports headsup.store here.
    code = (
        "from headsup.models import AppState; "
        "print(AppState(contacts=[], messages=[], events=[], reminders=[]).evening_check)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "19:00:00"
