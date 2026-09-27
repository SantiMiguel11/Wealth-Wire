"""§5 press-release wires and §6 Google News RSS for outlets that block bots."""
import sqlite3
from datetime import timedelta

import pytest

from fiduciarywire import db, paths
from fiduciarywire.categorize import Categorizer
from fiduciarywire.firms import SecMatcher
from fiduciarywire.gnews import dedupe_key, feed_url, parse_google_news, strip_outlet_suffix
from fiduciarywire.ingest import run_ingest
from fiduciarywire.wires import keep_wire_item

from .conftest import DEMO, NOW

GN = """<?xml version="1.0"?><rss version="2.0"><channel><title>site:thinkadvisor.com - Google News</title>
<item><title>Mariner Buys $2B RIA - ThinkAdvisor</title><link>https://news.google.com/rss/articles/CBMiAAA?oc=5</link>
<pubDate>Thu, 24 Sep 2026 12:00:00 GMT</pubDate><description>&lt;a href="x"&gt;Mariner&lt;/a&gt;</description>
<source url="https://www.thinkadvisor.com">ThinkAdvisor</source></item>
<item><title>Mariner Buys $2B RIA - ThinkAdvisor</title><link>https://news.google.com/rss/articles/CBMiBBB?oc=5</link>
<pubDate>Thu, 24 Sep 2026 13:00:00 GMT</pubDate><source url="https://www.thinkadvisor.com">ThinkAdvisor</source></item>
<item><title>Other Outlet Story - Somewhere</title><link>https://news.google.com/rss/articles/CBMiCCC?oc=5</link>
<pubDate>Thu, 24 Sep 2026 13:00:00 GMT</pubDate><source url="https://example.org">Somewhere</source></item>
</channel></rss>"""


def test_google_news_parsing():
    items, skipped = parse_google_news(GN, "ThinkAdvisor", "https://www.thinkadvisor.com", NOW)
    assert skipped == 1                                   # another outlet's article is not attributed to ThinkAdvisor
    assert len(items) == 1                                 # same headline/outlet/day → one item
    it = items[0]
    assert it.title == "Mariner Buys $2B RIA" and it.source == "ThinkAdvisor"
    assert it.url == "https://news.google.com/rss/articles/CBMiAAA?oc=5"   # redirect kept, never resolved
    assert it.canonical_url == dedupe_key("ThinkAdvisor", "2026-09-24T12:00:00Z", "Mariner Buys $2B RIA") == \
        "gnews:thinkadvisor:2026-09-24:mariner buys 2b ria"
    assert it.description == ""                           # Google's description is link HTML, not a teaser


def test_suffix_and_url_helpers():
    assert strip_outlet_suffix("A - B - ThinkAdvisor", ["ThinkAdvisor"]) == "A - B"
    assert strip_outlet_suffix("No suffix here", ["ThinkAdvisor"]) == "No suffix here"
    assert feed_url("site:thinkadvisor.com") == "https://news.google.com/rss/search?q=site:thinkadvisor.com&hl=en-US&gl=US&ceid=US:en"


def test_blocked_outlets_are_never_contacted(home, monkeypatch):
    from fiduciarywire import fetch

    seen = []
    orig = fetch.FixtureTransport.handle_request

    def spy(self, request):
        seen.append(request.url.host)
        return orig(self, request)

    monkeypatch.setattr(fetch.FixtureTransport, "handle_request", spy)
    run_ingest(fixtures=DEMO, now=NOW, quiet=True)
    assert "news.google.com" in seen
    assert not {"www.thinkadvisor.com", "www.fa-mag.com", "citywire.com"} & set(seen)
    # Google redirect links are stored, never followed
    urls = [r[0] for r in sqlite3.connect(paths.db_path()).execute("SELECT url FROM items WHERE source='ThinkAdvisor'")]
    assert urls and all(u.startswith("https://news.google.com/rss/articles/") for u in urls)


def test_google_news_dedupe_survives_new_redirect_links(ingested):
    """Google rotates redirect URLs; the headline+outlet+date key keeps re-runs duplicate-free."""
    conn = sqlite3.connect(paths.db_path())
    before = conn.execute("SELECT COUNT(*) FROM items WHERE source='ThinkAdvisor'").fetchone()[0]
    title, pub = conn.execute("SELECT title, published_at FROM items WHERE source='ThinkAdvisor' LIMIT 1").fetchone()
    feed = GN.replace("Mariner Buys $2B RIA - ThinkAdvisor", f"{title} - ThinkAdvisor", 1).replace(
        "Thu, 24 Sep 2026 12:00:00 GMT", pub.replace("T", " ").replace("Z", " GMT"), 1)
    items, _ = parse_google_news(feed.replace("12:00:00", "12:00:00"), "ThinkAdvisor", "https://www.thinkadvisor.com", NOW)
    assert any(i.canonical_url == dedupe_key("ThinkAdvisor", pub, title) for i in items)
    run_ingest(fixtures=DEMO, now=NOW + timedelta(hours=3), quiet=True)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE source='ThinkAdvisor'").fetchone()[0] == before


@pytest.fixture(scope="module")
def sec():
    return SecMatcher([{"crd": "1", "legal_name": "HARBORVIEW WEALTH PARTNERS, LLC", "business_name": "HARBORVIEW WEALTH PARTNERS", "aum_usd": 1e9}])


@pytest.mark.parametrize("title, desc, keep", [
    ("Harborview Wealth Partners Announces Acquisition of Summit Ridge Advisors", "a wealth management firm", True),   # SEC firm
    ("Acme Advisors Acquires Beta Planning, a Registered Investment Adviser", "", True),                              # M&A
    ("Beta Wealth Hires Former UBS Financial Advisor as Managing Director", "", True),                                   # people move
    ("National Survey: Financial Advisors Expect Client Growth", "survey of advisors", False),                           # no firm, not M&A
    ("Acme Biotech Announces Positive Phase 2 Results", "trial met its endpoint", False),                               # no wealth terms
    ("Industrial Holdings Corp. Merges With Steel Supplier", "4,000 employees", False),                                 # M&A but not wealth
])
def test_wire_filter(sec, title, desc, keep):
    assert keep_wire_item(title, desc, sec, Categorizer())[0] is keep


def test_wire_drop_counts_and_press_release_effects(ingested):
    conn = db.connect()
    st = {r["name"]: (r["items_last_run"], r["new_last_run"], r["dropped_last_run"]) for r in conn.execute("SELECT * FROM source_status")}
    # 4 keyword feeds: 11 items fetched, 5 kept (4 unique: Harborview is in two feeds), 5 dropped, 1 too old
    assert st["GlobeNewswire"] == (11, 4, 5)
    assert "Business Wire" not in st and "PR Newswire" not in st
    from fiduciarywire.sitebuild import collect

    files = collect(conn, NOW)
    deals = {d["headline"]: d for d in files["mna.json"]["deals"]}
    # Crestline: trade headlines alone are ambiguous (two targets) → the press release names the deal → high
    c = deals["PE-Backed Crestline Wealth to Buy Riverbend Financial and Aspen Grove Advisors"]
    assert c["press_release"] and c["confidence"] == "high"
    assert (c["acquirer"]["name"], c["target"]["name"], c["target_aum_usd"]) == ("Crestline Wealth", "Riverbend Financial", 9e8)
    # the press release joined the trade coverage (one card, not two)
    heads = [cl["headline"] for cl in files["clusters.json"]["clusters"]]
    assert not any(h.startswith("Crestline Wealth Completes Acquisition") for h in heads)
    assert files["sources.json"]["sources"][-1]["dropped_last_run"] >= 1
