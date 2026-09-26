import pytest

from wealthwire.urls import canonicalize


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("HTTPS://WWW.ThinkAdvisor.COM/2026/09/24/story/", "https://www.thinkadvisor.com/2026/09/24/story"),
        ("https://www.thinkadvisor.com/a/?utm_source=rss&utm_medium=feed&utm_campaign=x", "https://www.thinkadvisor.com/a"),
        ("https://www.investmentnews.com/x/1?fbclid=abc", "https://www.investmentnews.com/x/1"),
        ("https://example.com/x?gclid=1&id=7&a=2", "https://example.com/x?a=2&id=7"),
        ("https://citywire.com/ria/news/story/a2400000#comments", "https://citywire.com/ria/news/story/a2400000"),
        ("https://example.com:443/x", "https://example.com/x"),
        ("http://example.com:8080/x/", "http://example.com:8080/x"),
        ("https://example.com/", "https://example.com"),
        ("https://example.com/path///", "https://example.com/path"),
    ],
)
def test_canonicalize(raw, expected):
    assert canonicalize(raw) == expected


def test_path_case_preserved():
    # only the host is lowercased — paths can be case-sensitive
    assert canonicalize("https://EXAMPLE.com/News/A") == "https://example.com/News/A"


def test_variants_collapse_to_one():
    variants = [
        "https://www.thinkadvisor.com/2026/09/24/x/?utm_source=rss",
        "https://WWW.THINKADVISOR.COM/2026/09/24/x",
        "https://www.thinkadvisor.com/2026/09/24/x/#top",
        "https://www.thinkadvisor.com/2026/09/24/x?fbclid=1&utm_medium=email",
    ]
    assert len({canonicalize(v) for v in variants}) == 1
