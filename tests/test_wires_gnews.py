"""Google News RSS parsing (kept for outlets that block automated readers) and its robots.txt check.

news.google.com/robots.txt disallows /rss/search (found 2026-10-17), so the Google News sources are disabled
and, if re-enabled, the robots check stops them before any request (DECISIONS D4)."""
import sqlite3

from fiduciarywire import paths
from fiduciarywire.gnews import dedupe_key, feed_url, parse_google_news, strip_outlet_suffix
from fiduciarywire.ingest import run_ingest

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


def _spy_hosts(monkeypatch):
    from fiduciarywire import fetch

    seen = []
    orig = fetch.FixtureTransport.handle_request

    def spy(self, request):
        seen.append(str(request.url))
        return orig(self, request)

    monkeypatch.setattr(fetch.FixtureTransport, "handle_request", spy)
    return seen


def test_disabled_sources_are_never_contacted(home, monkeypatch):
    seen = _spy_hosts(monkeypatch)
    run_ingest(fixtures=DEMO, now=NOW, quiet=True)
    hosts = {u.split("/")[2] for u in seen}
    assert not {"news.google.com", "www.thinkadvisor.com", "www.fa-mag.com", "citywire.com", "www.globenewswire.com",
                "www.kitces.com", "www.finra.org"} & hosts
    assert "seekingalpha.com" in hosts and "www.prnewswire.com" in hosts


def test_google_news_search_respects_robots(home, monkeypatch):
    """Re-enabling a Google News source: robots.txt disallows /rss/search, so the feed is never requested."""
    import yaml

    cfg = paths.config_dir() / "sources.yaml"
    data = yaml.safe_load(cfg.read_text())
    for s in data["sources"]:
        if s["name"] == "ThinkAdvisor":
            s["enabled"] = True
    cfg.write_text(yaml.safe_dump(data))
    seen = _spy_hosts(monkeypatch)
    run_ingest(fixtures=DEMO, now=NOW, quiet=True)
    assert "https://news.google.com/robots.txt" in seen
    assert not any("/rss/search" in u for u in seen)
    reason = sqlite3.connect(paths.db_path()).execute("SELECT reason, ok FROM source_status WHERE name='ThinkAdvisor'").fetchone()
    assert reason[1] == 0 and "robots.txt" in reason[0]
