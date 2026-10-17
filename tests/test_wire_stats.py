"""Per-feed stats for press-release wires (state/wire_stats.csv) and robots.txt for wires."""
import csv
from datetime import timedelta

import pytest

from fiduciarywire import paths
from fiduciarywire.ingest import append_wire_stats, run_ingest

from .conftest import DEMO, NOW

PRN = "https://www.prnewswire.com/rss/financial-services-latest-news/acquisitions-mergers-and-takeovers-list.rss"


def rows():
    with paths.wire_stats_path().open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_one_row_per_wire_feed(ingested):
    [r] = rows()
    assert (r["source"], r["feed"], r["status"], r["run_at"]) == ("PR Newswire M&A", PRN, "ok", "2026-09-25T18:00:00Z")
    # 9 releases: 1 older than 14 days, 2 not deals (a class-action reminder, a French translation), 6 deals
    assert (int(r["fetched"]), int(r["too_old"]), int(r["dropped_by_filter"]), int(r["kept"])) == (9, 1, 2, 6)
    assert r["source_new_items"] == "6"


def test_stats_append_across_runs_and_prune(ingested):
    run_ingest(fixtures=DEMO, now=NOW + timedelta(hours=6), quiet=True)
    assert [x["run_at"] for x in rows()] == ["2026-09-25T18:00:00Z", "2026-09-26T00:00:00Z"]
    append_wire_stats([], NOW + timedelta(days=125))        # 120-day retention
    assert rows() == []


def test_stats_file_travels_with_state(ingested, tmp_path):
    from fiduciarywire import state

    state.save(tmp_path / "out")
    assert (tmp_path / "out" / "state" / "wire_stats.csv").exists()
    paths.wire_stats_path().unlink()
    assert state.restore(tmp_path / "out")["wire_stats"] is True
    assert len(rows()) == 1


def test_wire_feed_disallowed_by_robots_is_skipped(home, monkeypatch):
    """Wire feeds are robots-checked like pages (Business Wire's and GlobeNewswire's robots.txt rule them out)."""
    from fiduciarywire import db
    from fiduciarywire.config import Source
    from fiduciarywire.fetch import Fetcher
    from fiduciarywire.ingest import SourceIngester

    fetcher = Fetcher("test", per_host_delay=0)
    monkeypatch.setattr(fetcher.robots, "check", lambda url: (False, "robots.txt disallows /rss/home/"))
    monkeypatch.setattr(fetcher, "get", lambda *a, **k: pytest.fail("a disallowed feed must never be requested"))
    ing = SourceIngester(fetcher, db.connect(), "America/Los_Angeles", NOW)
    run = ing.run(Source("Wire", kind="wire", feed_urls=["https://feed.example.com/rss/home/?rss=x"]))
    assert not run.ok and "robots.txt disallows" in run.reason
    assert run.feed_stats[0]["status"].startswith("skipped")
    run = ing.run(Source("Wire2", kind="wire", feed_url="https://feed.example.com/rss/home/?rss=y"))
    assert not run.ok and "robots.txt disallows" in run.reason


def test_multi_feed_wire_merges_and_counts_each_feed(home):
    """A wire configured with several feeds (feed_urls) is filtered per feed and merged by URL."""
    from fiduciarywire import db
    from fiduciarywire.config import Source
    from fiduciarywire.fetch import Fetcher, FixtureTransport
    from fiduciarywire.ingest import SourceIngester

    fetcher = Fetcher("test", per_host_delay=0, backoff=0, transport=FixtureTransport(DEMO))
    ing = SourceIngester(fetcher, db.connect(), "America/Los_Angeles", NOW)
    src = Source("Two feeds", kind="wire", max_age_days=14, feed_urls=[PRN, PRN + "?dup=1"])
    run = ing.run(src)
    assert [(r["fetched"], r["kept"], r["dropped"]) for r in run.feed_stats][0] == (9, 6, 2)
    assert run.ok and len(run.items) == 6        # the same releases in both feeds count once
