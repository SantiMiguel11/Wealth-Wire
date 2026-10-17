import json
import sqlite3

import pytest

from fiduciarywire import paths
from fiduciarywire.mna import deal_for_cluster, extract_deal

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
    # deals only: one row per story, and every story is a deal
    assert conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0] == len(rows) == 21
    assert not any("Breaks Away" in h for h in rows)
    summit = rows["Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"]
    assert (summit["acquirer"], summit["target"], summit["target_aum_usd"], summit["confidence"], summit["press_release"]) == (
        "Harborview Wealth Partners", "Summit Ridge Advisors", 1.2e9, "high", 1)
    assert summit["value_usd"] is None                       # $1.2bn is AUM, not a price
    northwind = rows["Northwind Software to Acquire Brightpath Analytics for $420 Million"]
    assert (northwind["value_usd"], northwind["target_aum_usd"], northwind["stage"]) == (420e6, None, "announced")
    assert json.loads(northwind["industries"]) == ["Technology"]
    # stage: the most advanced any headline reports
    assert rows["Atlas Industrial to acquire Meridian Steel for $2.1bn"]["stage"] == "completed"
    assert rows["Halcyon Energy in talks to acquire Redstone Midstream"]["stage"] == "announced"
    assert rows["Copperline Bancorp and First Prairie Bank Announce Merger Agreement"]["deal_type"] == "merger"
    for h, r in rows.items():
        assert r["confidence"] == "high" or r["note"], h


def test_public_mna_rows(ingested):
    from fiduciarywire import db
    from fiduciarywire.sitebuild import collect

    from .conftest import NOW

    files = collect(db.connect(), NOW)
    deals = files["mna.json"]["deals"]
    assert all(r["sources"] and r["sources"][0]["url"].startswith("https://") for r in deals)
    summit = next(r for r in deals if "Summit Ridge" in r["headline"])
    assert summit["acquirer"]["name"] == "Harborview Wealth Partners" and summit["target_aum_source"] == "headline"
    assert summit["industries"][0] == "Wealth Management & RIAs" and summit["stage"] == "announced"
    by_ind = {}
    for r in deals:
        for i in r["industries"]:
            by_ind.setdefault(i, []).append(r["headline"])
    assert {"Investment Banking", "Wealth Management & RIAs", "Technology", "Banking", "Healthcare & Life Sciences",
            "Energy & Utilities", "Industrials", "Insurance", "Fintech & Payments", "Consumer & Retail",
            "Private Equity & Asset Management"} <= set(by_ind)
    assert any("Calloway Partners" in h for h in by_ind["Investment Banking"])
    meta = files["meta.json"]
    assert meta["industries"][0] == "Investment Banking" and meta["industries"][-1] == "Other"
    assert meta["categories"] == meta["industries"]
