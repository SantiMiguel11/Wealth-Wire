from datetime import datetime, timezone

from fiduciarywire.dates import parse_date, sane_published
from fiduciarywire.parse import parse_feed
from fiduciarywire.discover import parse_listing

FETCHED = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Eastern offset</title><link>https://a.example/1</link><pubDate>Thu, 24 Sep 2026 08:00:00 -0400</pubDate></item>
<item><title>GMT</title><link>https://a.example/2</link><pubDate>Thu, 24 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>Named zone</title><link>https://a.example/3</link><pubDate>Thu, 24 Sep 2026 05:00:00 PDT</pubDate></item>
<item><title>No date</title><link>https://a.example/4</link></item>
<item><title>Future date</title><link>https://a.example/5</link><pubDate>Thu, 24 Dec 2026 05:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><id>x</id><updated>2026-09-24T12:00:00Z</updated>
<entry><title>Z</title><link href="https://b.example/1"/><id>1</id><updated>2026-09-24T12:00:00Z</updated></entry>
<entry><title>Offset</title><link href="https://b.example/2"/><id>2</id><published>2026-09-24T14:00:00+02:00</published><updated>2026-09-25T00:00:00Z</updated></entry>
</feed>"""


def test_rss_dates_normalized_to_utc():
    items, _ = parse_feed(RSS, "S", FETCHED)
    by = {i.title: i for i in items}
    assert by["Eastern offset"].published_at == "2026-09-24T12:00:00Z"
    assert by["GMT"].published_at == "2026-09-24T12:00:00Z"
    assert by["Named zone"].published_at == "2026-09-24T12:00:00Z"
    assert by["No date"].published_at == "2026-09-25T18:00:00Z" and by["No date"].published_estimated
    assert by["Future date"].published_estimated


def test_atom_dates_prefer_published():
    items, _ = parse_feed(ATOM, "S", FETCHED)
    by = {i.title: i for i in items}
    assert by["Z"].published_at == "2026-09-24T12:00:00Z"
    assert by["Offset"].published_at == "2026-09-24T12:00:00Z"


def test_parse_date_formats():
    utc = timezone.utc
    assert parse_date("2026-09-24T08:00:00-04:00") == datetime(2026, 9, 24, 12, tzinfo=utc)
    assert parse_date("2026-09-24T12:00:00Z") == datetime(2026, 9, 24, 12, tzinfo=utc)
    # naive values are read in the configured timezone (PDT = UTC-7 in September)
    assert parse_date("2026-09-24T05:00:00") == datetime(2026, 9, 24, 12, tzinfo=utc)
    assert parse_date("September 24, 2026") == datetime(2026, 9, 24, 7, tzinfo=utc)
    assert parse_date("Sep. 24, 2026") == datetime(2026, 9, 24, 7, tzinfo=utc)
    assert parse_date("9/24/2026") == datetime(2026, 9, 24, 7, tzinfo=utc)
    assert parse_date("Thu, 24 Sep 2026 12:00:00 +0000") == datetime(2026, 9, 24, 12, tzinfo=utc)
    assert parse_date("January 5, 2026", "America/New_York") == datetime(2026, 1, 5, 5, tzinfo=utc)
    assert parse_date("not a date") is None and parse_date("") is None


def test_sane_published():
    assert sane_published(None, FETCHED) == (FETCHED, True)


def test_listing_parser_headline_link_date_only():
    html = """<html><body><nav><a href="/news/menu-item-link-here-now">Menu item link here now ok</a></nav>
    <article><h2><a href="/news/firm-a-acquires-firm-b-today">Firm A acquires Firm B in big RIA deal</a></h2>
    <time datetime="2026-09-24T09:00:00-07:00">Sep 24</time><p>Body text should never be collected.</p></article>
    <article><h3><a href="/tag/m-a">Mergers and acquisitions tag archive</a></h3></article>
    <article><h2><a href="https://other.example/news/x-y-z">Offsite link that should be skipped here</a></h2></article>
    </body></html>"""
    items = parse_listing(html, "https://l.example/", "L", FETCHED)
    assert [i.title for i in items] == ["Firm A acquires Firm B in big RIA deal"]
    assert items[0].published_at == "2026-09-24T16:00:00Z" and items[0].description == ""
