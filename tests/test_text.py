from wealthwire.parse import parse_feed
from wealthwire.text import clean_description, strip_html, truncate

from .test_dates import FETCHED


def test_truncate_word_boundary():
    s = "word " * 100
    out = truncate(s)
    assert len(out) <= 300 and out.endswith("…") and not out[:-1].endswith(" ")


def test_strip_html_and_wordpress_boilerplate():
    raw = '<p>Hello &amp; <b>world</b></p><p>The post <a href="x">Hello</a> appeared first on Kitces.</p>'
    assert strip_html(raw) == "Hello & world"


def test_content_encoded_ignored_even_when_feedparser_copies_it():
    rss = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>t</title>
    <item><title>Only content</title><link>https://a.example/1</link><content:encoded><![CDATA[<p>FULL TEXT</p>]]></content:encoded></item>
    <item><title>Both</title><link>https://a.example/2</link><description>Teaser</description><content:encoded><![CDATA[<p>FULL TEXT</p>]]></content:encoded></item>
    </channel></rss>"""
    items, _ = parse_feed(rss, "S", FETCHED)
    by = {i.title: i.description for i in items}
    assert by == {"Only content": "", "Both": "Teaser"}


def test_gated_parse_drops_description():
    rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Gated</title><link>https://a.example/1</link><description>Teaser</description></item></channel></rss>"""
    items, _ = parse_feed(rss, "S", FETCHED, gated=True)
    assert items[0].description == ""


def test_clean_description_limit():
    assert len(clean_description("<p>" + "x" * 1000 + "</p>")) <= 300
