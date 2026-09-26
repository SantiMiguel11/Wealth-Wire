import sqlite3

import pytest

from wealthwire import paths
from wealthwire.mna import deal_for_cluster, extract_deal

B = 1e9
M = 1e6


@pytest.mark.parametrize(
    "title, acquirer, target, aum, dtype",
    [
        ("Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors", "Harborview Wealth Partners", "Summit Ridge Advisors", 1.2 * B, "acquisition"),
        ("Harborview Wealth Partners Acquires $1.2B Summit Ridge Advisors | ThinkAdvisor", "Harborview Wealth Partners", "Summit Ridge Advisors", 1.2 * B, "acquisition"),
        ("Harborview Wealth Partners to Acquire Summit Ridge Advisors, a $1.2 Billion RIA", "Harborview Wealth Partners", "Summit Ridge Advisors", 1.2 * B, "acquisition"),
        ("Meridian Capital Partners adds $850M Cedar Lane Private Wealth", "Meridian Capital Partners", "Cedar Lane Private Wealth", 850 * M, "acquisition"),
        # B sells to A → roles inverted
        ("Cedar Lane Private Wealth sells to Meridian Capital Partners", "Meridian Capital Partners", "Cedar Lane Private Wealth", None, "acquisition"),
        ("Summit Wealth, a $900M firm, agrees to be acquired by Mariner", "Mariner", "Summit Wealth", 900 * M, "acquisition"),
        ("Lakeshore Financial Group agrees to be acquired by Atlas Wealth Management", "Atlas Wealth Management", "Lakeshore Financial Group", None, "acquisition"),
        # stakes
        ("Blue Heron Capital Takes Minority Stake In Oakmont Family Office", "Blue Heron Capital", "Oakmont Family Office", None, "stake"),
        ("Bear Mountain Capital makes minority investment in Willowbrook Wealth", "Bear Mountain Capital", "Willowbrook Wealth", None, "stake"),
        ("Willowbrook Wealth lands minority investment from Bear Mountain Capital", "Bear Mountain Capital", "Willowbrook Wealth", None, "stake"),
        ("Cetera sells minority stake to Genstar Capital", "Genstar Capital", "Cetera", None, "stake"),
        # mergers — combined figure is not a target AUM
        ("Northgate Advisors and Pinecrest Wealth Merge to Form $4.5B Firm", "Northgate Advisors", "Pinecrest Wealth", None, "merger"),
        ("Northgate Advisors merges with Pinecrest Wealth", "Northgate Advisors", "Pinecrest Wealth", None, "merger"),
        ("Sequoia Point Wealth completes recapitalization with Granite Peak Partners", "Granite Peak Partners", "Sequoia Point Wealth", None, "recapitalization"),
        # descriptors / prefixes / prices
        ("Exclusive: Mariner buys $300M Summit Wealth in Ohio", "Mariner", "Summit Wealth", 300 * M, "acquisition"),
        ("PE-backed Wealth Enhancement Group acquires Bellwether Advisors", "Wealth Enhancement Group", "Bellwether Advisors", None, "acquisition"),
        ("Hightower acquires $1.2B Cleveland firm Lorem Advisors", "Hightower", "Lorem Advisors", 1.2 * B, "acquisition"),
        ("Mariner acquires Summit Wealth for $50M", "Mariner", "Summit Wealth", None, "acquisition"),  # a price, not AUM
    ],
)
def test_high_confidence(title, acquirer, target, aum, dtype):
    d = extract_deal(title)
    assert (d.acquirer, d.target, d.deal_type, d.confidence) == (acquirer, target, dtype, "high"), d.notes
    assert d.target_aum_usd == (pytest.approx(aum) if aum else None)


@pytest.mark.parametrize(
    "title, acquirer, target, aum",
    [
        ("PE-Backed Crestline Wealth to Buy Riverbend Financial and Aspen Grove Advisors", "Crestline Wealth", "", None),  # two targets
        ("Crestline Wealth To Buy Riverbend Financial, Aspen Grove Advisors", "Crestline Wealth", "", None),
        ("Mariner acquires Texas RIA in $2.4B deal", "Mariner", "", None),  # unnamed target; $2.4B AUM or price?
        ("Focus Financial Partners to buy $1B RIA", "Focus Financial Partners", "", 1 * B),  # figure attached, target unnamed
        ("Kestra buys two RIAs with combined $3B", "Kestra", "", None),
        ("Report says sources say firm buys rival", "", "", None),
    ],
)
def test_low_confidence_leaves_blanks(title, acquirer, target, aum):
    d = extract_deal(title)
    assert d.confidence == "low" and d.notes
    assert (d.acquirer, d.target) == (acquirer, target)
    assert d.target_aum_usd == (pytest.approx(aum) if aum else None)


def test_no_pattern():
    assert extract_deal("Two Texas RIAs combine in deal creating $3bn firm") is None
    d = deal_for_cluster(["Serial acquirer strikes again with $600M buy in Arizona"])
    assert d.confidence == "low" and d.acquirer == d.target == "" and d.target_aum_usd is None


def test_cluster_fills_aum_from_agreeing_headline():
    d = deal_for_cluster(["Cedar Lane Private Wealth sells to Meridian Capital Partners",
                          "Meridian Capital Partners adds $850M Cedar Lane Private Wealth"])
    assert (d.acquirer, d.target, d.target_aum_usd, d.confidence) == ("Meridian Capital Partners", "Cedar Lane Private Wealth", 850 * M, "high")


def test_cluster_disagreement_goes_low():
    d = deal_for_cluster(["Alpha Wealth acquires Beta Advisors", "Gamma Capital acquires Beta Advisors"])
    assert d.confidence == "low" and d.acquirer == ""


def test_demo_mna_table(ingested):
    conn = sqlite3.connect(paths.db_path())
    conn.row_factory = sqlite3.Row
    rows = {r["headline"]: dict(r) for r in conn.execute("SELECT d.*, c.headline FROM mna_deals d JOIN clusters c ON c.id = d.cluster_id")}
    # one row per M&A cluster; People Moves (breakaway team to Harborview) is not in the table
    assert conn.execute("SELECT COUNT(*) FROM clusters WHERE category='M&A'").fetchone()[0] == len(rows)
    assert not any("Breaks Away" in h for h in rows)
    summit = rows["Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"]
    assert (summit["acquirer"], summit["target"], summit["target_aum_usd"], summit["confidence"]) == (
        "Harborview Wealth Partners", "Summit Ridge Advisors", 1.2e9, "high")
    lows = [h for h, r in rows.items() if r["confidence"] == "low"]
    assert "Two Texas RIAs combine in deal creating $3bn firm" in lows
    assert "Serial acquirer strikes again with $600M buy in Arizona" in lows
    for h in lows:
        assert rows[h]["note"]


def test_mna_api_filter(ingested, monkeypatch):
    monkeypatch.setenv("WEALTHWIRE_NO_BACKGROUND", "1")
    from fastapi.testclient import TestClient

    from wealthwire.server import app

    with TestClient(app) as c:
        all_rows = c.get("/api/mna").json()
        low = c.get("/api/mna?confidence=low").json()
        high = c.get("/api/mna?confidence=high").json()
        assert c.get("/api/mna?confidence=bogus").status_code == 422
    assert len(all_rows) == len(low) + len(high) and low and high
    assert all(r["confidence"] == "low" for r in low)
    assert all(r["sources"] and r["sources"][0]["url"].startswith("https://") for r in all_rows)
