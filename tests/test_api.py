import pytest
from fastapi.testclient import TestClient

from wealthwire.queries import fts_query


@pytest.fixture
def client(ingested, monkeypatch):
    monkeypatch.setenv("WEALTHWIRE_NO_BACKGROUND", "1")
    from wealthwire.server import app

    with TestClient(app) as c:
        yield c


def headlines(resp):
    data = resp.json()
    return [c["headline"] for c in data["pinned"] + data["clusters"]]


def test_fts_query_sanitizes():
    assert fts_query('custody "rule') == '"custody" "rule"*'
    assert fts_query("   ") == ""
    assert fts_query("S&P 500") == '"S&P" "500"*'


def test_index_and_static(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_feed_reverse_chronological(client):
    data = client.get("/api/feed?limit=200").json()
    lasts = [c["last_published"] for c in data["clusters"]]
    assert lasts == sorted(lasts, reverse=True)
    assert data["total"] == len(data["clusters"]) + len(data["pinned"]) or data["total"] >= len(data["clusters"])


def test_search(client):
    hs = headlines(client.get("/api/feed", params={"q": "custody rule"}))
    assert hs and all("custody" in h.lower() for h in hs)
    # prefix match on the last term, description is searched too
    assert headlines(client.get("/api/feed", params={"q": "cherry-pick"}))
    assert headlines(client.get("/api/feed", params={"q": "qualified custodian"}))  # only in a description
    assert client.get("/api/feed", params={"q": "zzzznotaword"}).json()["total"] == 0
    assert client.get("/api/feed", params={"q": '"unbalanced (quote'}).status_code == 200


def test_source_filter(client):
    data = client.get("/api/feed", params={"source": "SEC Press Releases", "limit": 200}).json()
    assert data["total"] >= 3
    for c in data["pinned"] + data["clusters"]:
        assert "SEC Press Releases" in [s["name"] for s in c["sources"]]


def test_date_filter(client):
    data = client.get("/api/feed", params={"from": "2026-09-25", "to": "2026-09-26", "limit": 200}).json()
    assert data["total"] > 0
    for c in data["pinned"] + data["clusters"]:
        assert any("2026-09-25" <= it["published_at"] < "2026-09-26" for it in c["items"])
    assert client.get("/api/feed", params={"from": "garbage"}).status_code == 400


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["demo"] is True and m["items"] > 40
    assert {s["name"] for s in m["sources"]} >= {"Kitces", "FINRA News"}
