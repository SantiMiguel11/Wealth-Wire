import pytest

from fiduciarywire.watchlist import Firm, Matcher


SEED = [
    Firm("Pugh Capital"),
    Firm("Coldstream", ["Coldstream Wealth Management"]),
    Firm("Bear Mountain Capital"),
    Firm("Goldman Sachs", ["Goldman Sachs Wealth Management", "Goldman"]),
]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Goldman Sachs Asset Management Launches Two Active ETFs", ["Goldman Sachs"]),
        ("GOLDMAN SACHS cuts fees", ["Goldman Sachs"]),
        ("Former Goldman advisors launch RIA", ["Goldman Sachs"]),
        ("Goldman's private wealth unit expands", ["Goldman Sachs"]),
        ("Coldstream Wealth Management Opens Portland Office", ["Coldstream"]),
        ("coldstream hires a CIO", ["Coldstream"]),
        ("Pugh Capital Management Expands Fixed Income Team", ["Pugh Capital"]),
        ("Bear Mountain Capital makes minority investment", ["Bear Mountain Capital"]),
        ("Bear   Mountain\nCapital backs RIA", ["Bear Mountain Capital"]),  # whitespace-insensitive
        # false positives that must NOT match
        ("Goldmann Advisors opens office", []),        # word boundary
        ("GoldmanSachs-style hiring", []),
        ("Coldstreamer app launches", []),
        ("Bear Mountain hiking trip for advisors", []),  # partial name
        ("Mountain Capital Partners acquires RIA", []),
        ("Pugh named partner at Rivera Capital", []),
        ("Bear market hits Capital Group funds", []),
        ("Pugh-Capital style", []),
    ],
)
def test_matching(text, expected):
    assert Matcher(SEED).hits(text) == expected


def test_short_aliases_never_match():
    m = Matcher([Firm("Goldman Sachs", ["GS", "G"])])
    assert m.hits("GS rallies as G7 meets") == []
    assert Firm("GS", ["Goldman Sachs"]).terms() == ["Goldman Sachs"]


def test_parse_watchlist_json_formats():
    from fiduciarywire.watchlist import parse_watchlist

    exported = '{"version":1,"firms":[{"name":"Goldman Sachs","aliases":["Goldman"]},{"name":" Pugh  Capital "}]}'
    firms = parse_watchlist(exported)
    assert [(f.name, f.aliases) for f in firms] == [("Goldman Sachs", ["Goldman"]), ("Pugh Capital", [])]
    assert [f.name for f in parse_watchlist('["Coldstream", {"name": ""}]')] == ["Coldstream"]
