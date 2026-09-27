import sqlite3
from datetime import timedelta

import httpx

from fiduciarywire import db, paths
from fiduciarywire.fetch import Fetcher, FixtureTransport
from fiduciarywire.ingest import run_ingest

from .conftest import DEMO, NOW


def _conn():
    conn = sqlite3.connect(paths.db_path())
    conn.row_factory = sqlite3.Row
    return conn


def test_ingest_twice_inserts_zero_duplicates(ingested):
    _, first = ingested
    assert first["new"] > 40
    count = _conn().execute("SELECT COUNT(*) FROM items").fetchone()[0]
    second = run_ingest(fixtures=DEMO, now=NOW + timedelta(hours=2), quiet=True)
    assert second["new"] == 0
    assert _conn().execute("SELECT COUNT(*) FROM items").fetchone()[0] == count


def test_unique_constraint_on_canonical_url(ingested):
    conn = _conn()
    row = conn.execute("SELECT * FROM items LIMIT 1").fetchone()
    cur = conn.execute(
        "INSERT OR IGNORE INTO items(title,url,canonical_url,source,published_at,fetched_at,description) VALUES (?,?,?,?,?,?,?)",
        (row["title"], row["url"] + "?utm_source=x", row["canonical_url"], "Other", row["published_at"], row["fetched_at"], ""),
    )
    assert cur.rowcount == 0


def test_no_full_text_stored(ingested):
    conn = _conn()
    assert conn.execute("SELECT MAX(length(description)) FROM items").fetchone()[0] <= 300
    for (desc,) in conn.execute("SELECT description FROM items"):
        assert "FULL ARTICLE TEXT" not in desc
        assert "<" not in desc and "&amp;" not in desc
    # Kitces item that only has content:encoded → empty description
    row = conn.execute("SELECT description FROM items WHERE title LIKE 'The Latest In Financial #AdvisorTech%'").fetchone()
    assert row["description"] == ""
    # long HTML description → stripped and truncated with an ellipsis
    row = conn.execute("SELECT description FROM items WHERE title LIKE 'Weekend Reading%'").fetchone()
    assert 200 < len(row["description"]) <= 300 and row["description"].endswith("…")
    # stored columns are only the allowed article fields + derived metadata
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert cols == {"id", "title", "url", "canonical_url", "source", "published_at", "published_estimated",
                    "fetched_at", "description", "category", "cluster_id", "aum_usd"}


def test_description_length_enforced_by_db(home):
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO items(title,url,canonical_url,source,published_at,fetched_at,description) VALUES ('t','u','c','s','p','f',?)",
            ("x" * 301,),
        )
        assert False, "CHECK constraint should reject >300 chars"
    except sqlite3.IntegrityError:
        pass


def test_gated_source_has_empty_descriptions(ingested):
    rows = _conn().execute("SELECT description FROM items WHERE source='AdvisorHub'").fetchall()
    assert rows and all(r["description"] == "" for r in rows)


def test_source_methods_and_reasons(ingested):
    conn = _conn()
    status = {r["name"]: r for r in conn.execute("SELECT * FROM source_status")}
    assert status["WealthManagement.com"]["method"] == "RSS"
    assert status["InvestmentNews"]["method"] == "discovered RSS"   # homepage 403 → /feed
    assert status["RIABiz"]["method"] == "listing fallback"
    for name in ("ThinkAdvisor", "Financial Advisor Magazine", "Citywire RIA"):
        assert status[name]["method"] == "Google News RSS" and status[name]["kind"] == "google_news"
    assert status["FINRA News"]["method"] == "failed"
    assert "robots.txt disallows" in status["FINRA News"]["reason"]
    assert "gated" in status["AdvisorHub"]["reason"]
    assert status["GlobeNewswire"]["kind"] == "wire" and status["GlobeNewswire"]["dropped_last_run"] == 5
    assert "PR Newswire" not in status  # disabled: listed in SOURCES.md, never fetched
    assert sum(r["ok"] for r in status.values()) >= 7


def test_sources_md_written(ingested):
    text = paths.sources_md_path().read_text()
    assert "| FINRA News | feed | ❌ failed | failed |" in text
    assert "robots.txt disallows /media-center/newsreleases" in text
    assert "listing fallback" in text and "discovered RSS" in text and "Google News RSS" in text
    assert "| GlobeNewswire | wire | ✅ ok | RSS (4 of 4 feeds) |" in text and "kept 5 of 11 across 4 keyword feeds (4 unique)" in text
    assert "| PR Newswire | wire | ⏸ disabled | disabled |" in text
    assert "Offline fixture run" in text and "SEC adviser data" in text


def _discover(src, now=NOW):
    from fiduciarywire.config import Source
    from fiduciarywire.ingest import SourceIngester

    conn = db.connect()
    f = Fetcher("UA test@example.com", per_host_delay=0, conn=conn, transport=FixtureTransport(DEMO))
    return SourceIngester(f, conn, "America/Los_Angeles", now).run(Source(**src)), conn


def test_discovery_via_link_rel_alternate_skips_comment_feeds(home):
    run, conn = _discover({"name": "CW direct", "homepage": "https://citywire.com/ria", "listing_url": "https://citywire.com/ria/news"})
    assert run.method == "discovered RSS" and run.url_used == "https://citywire.com/ria/news.rss" and run.fetched == 7
    # cached and reused on the next run (no homepage crawl)
    row = conn.execute("SELECT discovered_feed_url FROM source_status WHERE name='CW direct'").fetchone()
    assert row["discovered_feed_url"] == "https://citywire.com/ria/news.rss"
    again, _ = _discover({"name": "CW direct", "homepage": "https://citywire.com/ria"})
    assert again.method == "discovered RSS" and again.new == 0


def test_discovery_via_common_path(home):
    run, _ = _discover({"name": "FA direct", "homepage": "https://www.fa-mag.com", "listing_url": "https://www.fa-mag.com/news"})
    assert run.method == "discovered RSS" and run.url_used == "https://www.fa-mag.com/rss"


def test_conditional_get_uses_etag_and_handles_304(ingested):
    transport = FixtureTransport(DEMO)
    fetcher = Fetcher("UA test@example.com", per_host_delay=0, conn=db.connect(), transport=transport)
    res = fetcher.get("https://www.sec.gov/news/pressreleases.rss", conditional=True)
    assert res.not_modified and res.status == 304
    assert transport.requests[-1].headers["if-none-match"] == '"sec-v1"'
    assert "if-modified-since" in transport.requests[-1].headers


def test_listing_titles_stripped_of_source_suffix(ingested):
    titles = [r[0] for r in _conn().execute("SELECT title FROM items WHERE source='ThinkAdvisor'")]
    assert not any("| ThinkAdvisor" in t for t in titles)


def test_user_agent_sent(home):
    transport = FixtureTransport(DEMO)
    f = Fetcher("FiduciaryWire/0.1 (personal news reader; me@example.com)", per_host_delay=0, transport=transport)
    f.get("https://www.kitces.com/feed/")
    assert "me@example.com" in transport.requests[0].headers["user-agent"]


class FakeClock:
    def __init__(self):
        self.t = 100.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_per_host_delay():
    fc = FakeClock()
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="ok"))
    f = Fetcher("UA", per_host_delay=2.0, transport=transport, sleep=fc.sleep, clock=fc.clock)
    f.get("https://a.example/1")
    f.get("https://b.example/1")  # different host: no wait
    assert fc.sleeps == []
    fc.t += 0.5
    f.get("https://a.example/2")  # same host 0.5s later: waits the remaining 1.5s
    assert fc.sleeps == [1.5]


def test_retry_once_with_backoff():
    fc = FakeClock()
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, text="ok")

    f = Fetcher("UA", per_host_delay=0, retries=1, backoff=2.0, transport=httpx.MockTransport(handler), sleep=fc.sleep, clock=fc.clock)
    assert f.get("https://a.example/x").ok
    assert len(calls) == 2 and 2.0 in fc.sleeps


def test_no_retry_on_404_and_only_one_retry():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(404 if "404" in str(req.url) else 500)

    f = Fetcher("UA", per_host_delay=0, retries=1, backoff=0, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert f.get("https://a.example/404").status == 404 and len(calls) == 1
    assert f.get("https://a.example/500").status == 500 and len(calls) == 3


def test_robots_disallow_blocks_listing():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /news\n")
        return httpx.Response(200, text="<html></html>")

    f = Fetcher("UA", per_host_delay=0, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert f.robots.check("https://x.example/news/list") == (False, "robots.txt disallows /news/list")
    assert f.robots.check("https://x.example/other")[0] is True
