import sqlite3
from pathlib import Path

import pytest
import yaml

from fiduciarywire import paths
from fiduciarywire.cluster import ClusterItem, cluster, normalize_title, score
from fiduciarywire.config import load_config, load_stoplist
from fiduciarywire.deals import is_deal
from fiduciarywire.extract import extract_firms

PAIRS = yaml.safe_load((Path(__file__).parent / "fixtures" / "cluster_pairs.yaml").read_text())
THRESHOLD = float(load_config()["cluster"]["threshold"])
_stop = load_stoplist()


def item(i, title, source=None, when="2026-09-25T00:00:00Z"):
    return ClusterItem(i, source or f"src{i}", when, title, firms=set(extract_firms(title, _stop)), category="M&A" if is_deal(title) else "Other")  # the pipeline clusters deals only (all "M&A")


@pytest.mark.parametrize("a, b", PAIRS["match"])
def test_should_match(a, b):
    assert score(item(1, a), item(2, b)) >= THRESHOLD


@pytest.mark.parametrize("a, b", PAIRS["no_match"])
def test_should_not_match(a, b):
    assert score(item(1, a), item(2, b)) < THRESHOLD


def test_normalize_title():
    assert normalize_title("Harborview Buys $1.2B RIA | ThinkAdvisor") == normalize_title("Harborview acquires $1.2 billion RIA")
    assert "usd850m" in normalize_title("Firm adds $850mm team")


def test_same_source_never_clusters():
    a = item(1, "Fed Holds Rates Steady", source="X")
    b = item(2, "Fed Holds Rates Steady", source="X")
    assert len(cluster([a, b], THRESHOLD)) == 2


def test_window():
    a = item(1, "Fed Holds Rates Steady, Signals One More Cut", when="2026-09-20T00:00:00Z")
    b = item(2, "Fed Holds Rates Steady, Signals One More Cut", when="2026-09-24T00:00:00Z")
    assert len(cluster([a, b], THRESHOLD, window_hours=72)) == 2
    c = item(3, "Fed Holds Rates Steady, Signals One More Cut", when="2026-09-22T00:00:00Z")
    assert len(cluster([a, c], THRESHOLD, window_hours=72)) == 1


def test_demo_clusters(ingested):
    conn = sqlite3.connect(paths.db_path())
    conn.row_factory = sqlite3.Row
    assert conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0] == 21
    row = conn.execute("SELECT * FROM clusters WHERE headline LIKE '%Summit Ridge%'").fetchone()
    assert row["outlet_count"] == 5  # 4 trade outlets + the PR Newswire release
    # headline comes from the earliest item
    assert row["headline"] == "Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"
    sources = {r[0] for r in conn.execute("SELECT source FROM items WHERE cluster_id=?", (row["id"],))}
    assert sources == {"WealthManagement.com", "Financial Planning", "InvestmentNews", "RIABiz", "PR Newswire M&A"}
    assert row["category"] == "Wealth Management & RIAs"
    # the breakaway team joining Harborview is a people move, not a deal: never stored
    assert not conn.execute("SELECT 1 FROM items WHERE title LIKE '%Breaks Away%'").fetchone()
    # the same deal in different words across outlets is one story ("to Acquire … for $420 Million" / "buys … for $420M")
    nw = conn.execute("SELECT * FROM clusters WHERE headline LIKE 'Northwind Software%'").fetchall()
    assert len(nw) == 1 and nw[0]["outlet_count"] == 3
    lumen = conn.execute("SELECT * FROM clusters WHERE headline LIKE '%Lumen Dental%'").fetchall()
    assert len(lumen) == 1 and lumen[0]["outlet_count"] == 3   # "Completes Acquisition of" / "buys" / "sold to"


def test_public_card_lists_all_sources(ingested):
    from fiduciarywire import db
    from fiduciarywire.sitebuild import collect

    from .conftest import NOW

    files = collect(db.connect(), NOW)
    cards = [c for c in files["clusters.json"]["clusters"] if "Summit Ridge" in c["headline"]]
    assert len(cards) == 1
    # AdvisorHub is excluded from the public site; the other outlets are all listed with links
    assert {s["name"] for s in cards[0]["sources"]} == {"WealthManagement.com", "Financial Planning", "InvestmentNews", "RIABiz", "PR Newswire M&A"}
    assert cards[0]["press_release"] is True
    assert {s["name"]: s["kind"] for s in cards[0]["sources"]}["PR Newswire M&A"] == "wire"
    assert cards[0]["deal"] == {"acquirer": "Harborview Wealth Partners", "target": "Summit Ridge Advisors", "type": "acquisition",
                                "stage": "announced", "value_usd": None}
    assert all(s["url"].startswith("https://") for s in cards[0]["sources"])
