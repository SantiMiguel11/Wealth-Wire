import sqlite3
from pathlib import Path

import pytest
import yaml

from wealthwire import paths
from wealthwire.categorize import Categorizer
from wealthwire.cluster import ClusterItem, cluster, normalize_title, score
from wealthwire.config import load_config, load_stoplist
from wealthwire.extract import extract_firms

PAIRS = yaml.safe_load((Path(__file__).parent / "fixtures" / "cluster_pairs.yaml").read_text())
THRESHOLD = float(load_config()["cluster"]["threshold"])
_cat = Categorizer()
_stop = load_stoplist()


def item(i, title, source=None, when="2026-09-25T00:00:00Z"):
    return ClusterItem(i, source or f"src{i}", when, title, firms=set(extract_firms(title, _stop)), category=_cat.categorize(title))


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
    assert conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0] == 35
    row = conn.execute("SELECT * FROM clusters WHERE headline LIKE '%Summit Ridge%'").fetchone()
    assert row["outlet_count"] == 4
    # headline comes from the earliest item
    assert row["headline"] == "Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"
    sources = {r[0] for r in conn.execute("SELECT source FROM items WHERE cluster_id=?", (row["id"],))}
    assert sources == {"Citywire RIA", "ThinkAdvisor", "WealthManagement.com", "RIABiz"}
    # the breakaway team joining Harborview is a separate story
    team = conn.execute("SELECT * FROM clusters WHERE headline LIKE '%Breaks Away%'").fetchone()
    assert team["id"] != row["id"] and team["category"] == "People Moves" and team["outlet_count"] == 3


def test_public_card_lists_all_sources(ingested):
    from wealthwire import db
    from wealthwire.sitebuild import collect

    from .conftest import NOW

    files = collect(db.connect(), NOW)
    cards = [c for c in files["clusters.json"]["clusters"] if "Summit Ridge" in c["headline"]]
    assert len(cards) == 1
    # AdvisorHub is excluded from the public site; the other outlets are all listed with links
    assert {s["name"] for s in cards[0]["sources"]} == {"Citywire RIA", "ThinkAdvisor", "WealthManagement.com", "RIABiz"}
    assert all(s["url"].startswith("https://") for s in cards[0]["sources"])
