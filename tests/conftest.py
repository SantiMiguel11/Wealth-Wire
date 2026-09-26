from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
DEMO = FIXTURES / "demo"
# Fixture stories are generated relative to this instant (see scripts/make_fixtures.py).
NOW = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated data dir + copy of the config files (so watchlist edits don't touch the repo)."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    for name in ("config.yaml", "sources.yaml", "categories.yaml", "firm_stoplist.yaml"):
        shutil.copy(ROOT / name, cfg / name)
    data = tmp_path / "home"
    data.mkdir()
    monkeypatch.setenv("WEALTHWIRE_CONFIG", str(cfg))
    monkeypatch.setenv("WEALTHWIRE_HOME", str(data))
    return data


@pytest.fixture
def ingested(home):
    from wealthwire.ingest import run_ingest

    summary = run_ingest(fixtures=DEMO, now=NOW, quiet=True)
    return home, summary
