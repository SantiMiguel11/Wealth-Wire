import pytest
import yaml
from fastapi.testclient import TestClient

from wealthwire import paths
from wealthwire.watchlist import Firm, Matcher, load_watchlist, save_watchlist

from .conftest import NOW

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


@pytest.fixture
def client(ingested, monkeypatch):
    monkeypatch.setenv("WEALTHWIRE_NO_BACKGROUND", "1")
    monkeypatch.setattr("wealthwire.queries.utcnow", lambda: NOW)
    from wealthwire.server import app

    with TestClient(app) as c:
        yield c


def test_pinned_and_highlighted(client):
    data = client.get("/api/feed").json()
    pinned = data["pinned"]
    assert pinned and all(c["watchlist_hits"] for c in pinned)
    names = {n for c in pinned for n in c["watchlist_hits"]}
    assert names == {"Goldman Sachs", "Coldstream", "Pugh Capital", "Bear Mountain Capital"}
    # pinned stories are not repeated in the main list, and the main list has no watchlist hits
    pinned_ids = {c["id"] for c in pinned}
    assert not pinned_ids & {c["id"] for c in data["clusters"]}
    assert all(not c["watchlist_hits"] for c in data["clusters"])


def test_pins_respect_filters(client):
    data = client.get("/api/feed", params={"category": "Products & Funds"}).json()
    assert [c["watchlist_hits"] for c in data["pinned"]] == [["Goldman Sachs"]]


def test_watch_filter(client):
    data = client.get("/api/feed", params={"watch": "1"}).json()
    assert data["pinned"] == [] and data["total"] == len(data["clusters"]) >= 5
    assert all(c["watchlist_hits"] for c in data["clusters"])


def test_add_and_remove_firm_via_api(client):
    r = client.post("/api/watchlist", json={"name": "Harborview Wealth Partners", "aliases": ["Harborview"]})
    assert r.status_code == 201
    assert "Harborview Wealth Partners" in (paths.config_dir() / "watchlist.yaml").read_text()
    data = client.get("/api/feed", params={"watch": "1", "q": "Summit Ridge"}).json()
    assert data["clusters"][0]["watchlist_hits"] == ["Harborview Wealth Partners"]
    assert client.post("/api/watchlist", json={"name": "harborview wealth partners"}).status_code == 409
    assert client.post("/api/watchlist", json={"name": "GS"}).status_code == 422
    firms = {f["name"]: f for f in client.get("/api/watchlist").json()["firms"]}
    assert firms["Harborview Wealth Partners"]["recent"] == 2
    assert client.delete("/api/watchlist/Harborview Wealth Partners").status_code == 200
    assert "Harborview" not in (paths.config_dir() / "watchlist.yaml").read_text()
    assert client.delete("/api/watchlist/Nope").status_code == 404
