"""Fixtures shared by the Heads-Up test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from headsup import store
from headsup.models import AppState


@pytest.fixture
def seeded_state() -> AppState:
    """A fresh state built from the persona files, changed by nothing."""
    return store.seed_state()


@pytest.fixture
def state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary state file, also pointed at by ``HEADSUP_STATE``."""
    path = tmp_path / "state.json"
    monkeypatch.setenv("HEADSUP_STATE", str(path))
    return path
