"""Shared pytest fixtures. Every test runs against a throwaway data folder."""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform != "win32":
    # Headless elsewhere; on Windows the native platform is used so fonts and metrics match real use.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "finpilot-home"
    home.mkdir()
    monkeypatch.setenv("FINPILOT_HOME", str(home))
    return home


@pytest.fixture
def db(tmp_path):
    from finpilot.data.db import Database
    d = Database(tmp_path / "test.db")
    yield d
    d.close()


@pytest.fixture(scope="session")
def cur():
    from finpilot.curriculum import load
    return load()
