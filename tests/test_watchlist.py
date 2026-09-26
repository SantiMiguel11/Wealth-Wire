import pytest
import yaml

from wealthwire import paths
from wealthwire.watchlist import Firm, Matcher, load_watchlist, save_watchlist


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


def test_yaml_round_trip(home):
    save_watchlist(SEED + [Firm("Acme Wealth", ["Acme"])])
    loaded = load_watchlist()
    assert [f.name for f in loaded][-1] == "Acme Wealth" and loaded[-1].aliases == ["Acme"]
    data = yaml.safe_load((paths.config_dir() / "watchlist.yaml").read_text())
    assert data["firms"][1] == {"name": "Coldstream", "aliases": ["Coldstream Wealth Management"]}
