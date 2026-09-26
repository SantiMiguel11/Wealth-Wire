import json
from datetime import timedelta
from pathlib import Path

from wealthwire import db, paths
from wealthwire.dates import to_iso
from wealthwire.digest import digest_payload, render_markdown
from wealthwire.ingest import run_ingest

from .conftest import DEMO, NOW

ROOT = Path(__file__).resolve().parent.parent
FIELDS = {"cluster_id", "headline", "category", "sources", "outlet_count", "watchlist_hits", "firms", "aum_usd",
          "descriptions", "first_seen"}


def load():
    return json.loads(paths.new_stories_path().read_text())


def test_new_stories_written_after_ingest_with_fallback_window(ingested):
    data = load()
    assert data["window_basis"].startswith("fallback")
    assert data["window_start"] == to_iso(NOW - timedelta(hours=24))
    assert data["local_date"] == "2026-09-25" and data["generated_at"] == to_iso(NOW)
    assert data["count"] == len(data["stories"]) > 20
    for s in data["stories"]:
        assert FIELDS <= set(s)
        assert all(set(x) == {"name", "url"} for x in s["sources"])


def test_ranking(ingested):
    stories = load()["stories"]
    keys = [(-len(s["watchlist_hits"]), -s["outlet_count"]) for s in stories]
    assert keys == sorted(keys)
    first_non_watch = next(i for i, s in enumerate(stories) if not s["watchlist_hits"])
    assert all(s["watchlist_hits"] for s in stories[:first_non_watch])
    # among non-watchlist stories the 4-outlet Summit Ridge deal comes first
    assert stories[first_non_watch]["headline"].startswith("Harborview Wealth Partners buys")
    # recency breaks ties
    same = [s for s in stories if not s["watchlist_hits"] and s["outlet_count"] == 1]
    assert [s["published_at"] for s in same] == sorted((s["published_at"] for s in same), reverse=True)


def test_window_uses_last_digest(ingested):
    digests = paths.digests_dir()
    digests.mkdir(parents=True, exist_ok=True)
    (digests / ".last_digest").write_text(to_iso(NOW) + "\n")
    # nothing new since the last digest
    run_ingest(fixtures=DEMO, now=NOW + timedelta(hours=2), quiet=True)
    data = load()
    assert data["window_basis"] == "digests/.last_digest" and data["count"] == 0
    # a new item arriving later shows up
    conn = db.connect()
    conn.execute(
        "INSERT INTO items(title,url,canonical_url,source,published_at,fetched_at,description) VALUES (?,?,?,?,?,?,?)",
        ("Acme Wealth Partners acquires Beta Advisors", "https://x.example/1", "https://x.example/1", "Kitces",
         to_iso(NOW + timedelta(hours=3)), to_iso(NOW + timedelta(hours=3)), ""),
    )
    conn.commit()
    from wealthwire.pipeline import recompute

    recompute(conn, now=NOW + timedelta(hours=4))
    data = load()
    assert [s["headline"] for s in data["stories"]] == ["Acme Wealth Partners acquires Beta Advisors"]


def test_backfill_guard_excludes_old_published(home):
    conn = db.connect()
    conn.execute(
        "INSERT INTO items(title,url,canonical_url,source,published_at,fetched_at,description) VALUES (?,?,?,?,?,?,?)",
        ("Old story from the feed archive", "https://x.example/old", "https://x.example/old", "Kitces",
         to_iso(NOW - timedelta(days=30)), to_iso(NOW), ""),
    )
    conn.commit()
    from wealthwire.pipeline import recompute

    recompute(conn, now=NOW)
    assert load()["count"] == 0


def test_digest_payload_fallback_then_file(ingested):
    p = digest_payload()
    assert p["date"] is None and len(p["top"]) == 10
    d = paths.digests_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-24.md").write_text("# Old")
    (d / "2026-09-25.md").write_text("# Wealth Wire\n\n## Watchlist Hits\n\n[Link](https://example.com)\n")
    p = digest_payload()
    assert p["date"] == "2026-09-25" and "<h2>Watchlist Hits</h2>" in p["html"]


def test_markdown_is_sanitized():
    html = render_markdown("Hi <script>alert(1)</script> [x](javascript:alert(1)) <img src=x onerror=alert(1)> [ok](https://a.example)")
    assert "<script" not in html and "javascript:" not in html and "onerror" not in html and "<img" not in html
    assert 'href="https://a.example"' in html


def test_settings_allow_only_what_digest_needs():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    allow = settings["permissions"]["allow"]
    assert set(allow) == {"Bash(python -m wealthwire ingest)", "Bash(python3 -m wealthwire ingest)",
                          "Read(./new_stories.json)", "Write(./digests/**)", "Edit(./digests/**)"}
    assert not any("*" in a and "digests" not in a for a in allow)
    cmd = (ROOT / ".claude" / "commands" / "digest.md").read_text()
    assert "python -m wealthwire ingest" in cmd and ".last_digest" in cmd and "Watchlist Hits" in cmd
