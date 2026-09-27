"""Follow-up 2: keyword-scoped wire feeds, per-feed stats file, robots for wires, award filter."""
import csv
from datetime import timedelta

import pytest

from fiduciarywire import paths
from fiduciarywire.categorize import Categorizer
from fiduciarywire.ingest import append_wire_stats, run_ingest

from .conftest import DEMO, NOW


def rows():
    with paths.wire_stats_path().open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_one_row_per_keyword_feed(ingested):
    r = {x["feed"].split("/keyword/")[1].split("/")[0]: x for x in rows()}
    assert set(r) == {"registered%20investment%20advisor", "wealth%20management", "RIA", "family%20office"}
    counts = {k: (int(v["fetched"]), int(v["too_old"]), int(v["dropped_by_filter"]), int(v["kept"])) for k, v in r.items()}
    assert counts == {
        "registered%20investment%20advisor": (4, 0, 2, 2),
        "wealth%20management": (4, 1, 1, 2),
        "RIA": (2, 0, 1, 1),
        "family%20office": (1, 0, 1, 0),   # award release
    }
    assert {x["source"] for x in rows()} == {"GlobeNewswire"} and {x["source_new_items"] for x in rows()} == {"4"}
    assert all(x["run_at"] == "2026-09-25T18:00:00Z" and x["status"] == "ok" for x in rows())


def test_stats_append_across_runs_and_prune(ingested):
    run_ingest(fixtures=DEMO, now=NOW + timedelta(hours=6), quiet=True)
    assert [x["run_at"] for x in rows()].count("2026-09-26T00:00:00Z") == 4 and len(rows()) == 8
    append_wire_stats([], NOW + timedelta(days=125))        # 120-day retention
    assert rows() == []


def test_stats_file_travels_with_state(ingested, tmp_path):
    from fiduciarywire import state

    state.save(tmp_path / "out")
    assert (tmp_path / "out" / "state" / "wire_stats.csv").exists()
    paths.wire_stats_path().unlink()
    assert state.restore(tmp_path / "out")["wire_stats"] is True
    assert len(rows()) == 4


def test_wire_feed_disallowed_by_robots_is_skipped(home, monkeypatch):
    """Business Wire's robots.txt disallows its feed path; wire feeds are robots-checked like pages."""
    from fiduciarywire.config import Source
    from fiduciarywire.fetch import Fetcher
    from fiduciarywire.ingest import SourceIngester
    from fiduciarywire import db

    fetcher = Fetcher("test", per_host_delay=0)
    monkeypatch.setattr(fetcher.robots, "check", lambda url: (False, "robots.txt disallows /rss/home/"))
    monkeypatch.setattr(fetcher, "get", lambda *a, **k: pytest.fail("a disallowed feed must never be requested"))
    ing = SourceIngester(fetcher, db.connect(), "America/Los_Angeles", NOW)
    run = ing.run(Source("Wire", kind="wire", feed_urls=["https://feed.example.com/rss/home/?rss=x"]))
    assert not run.ok and "robots.txt disallows" in run.reason
    assert run.feed_stats[0]["status"].startswith("skipped")
    run = ing.run(Source("Wire2", kind="wire", feed_url="https://feed.example.com/rss/home/?rss=y"))
    assert not run.ok and "robots.txt disallows" in run.reason


@pytest.mark.parametrize("title,keep", [
    ("Crestwood Advisors Earns Continued Recognition on Barron's 2026 Top 100 RIA Firms List", False),
    ("Stansberry Asset Management Earns 2025 Great Place To Work Certification", False),
    ("ROBERTSON STEPHENS NAMED TO USA TODAY'S BEST FINANCIAL ADVISORY FIRMS", False),
    ("Award-Winning RIA Harborview Wealth Partners Acquires Summit Ridge Advisors", True),   # a deal still counts
    ("Family Office Partners Names Jason Mok as Director of Family Office Services", True),  # "Names X" ≠ "Named to"
])
def test_award_releases_are_dropped(ingested, title, keep):
    from fiduciarywire import db
    from fiduciarywire.firms import SecMatcher
    from fiduciarywire.wires import keep_wire_item

    assert keep_wire_item(title, "a registered investment adviser", SecMatcher.from_db(db.connect()), Categorizer())[0] is keep
