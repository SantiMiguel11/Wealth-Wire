import pytest

from wealthwire.config import load_stoplist
from wealthwire.extract import extract_aum, extract_firms, firm_spans, parse_aum
from wealthwire.queries import trending_firms


@pytest.mark.parametrize(
    "text, value",
    [
        ("$1.2bn", 1.2e9), ("$1.2 billion", 1.2e9), ("$1.2B", 1.2e9), ("$1.2-billion", 1.2e9), ("$1.2 bln", 1.2e9),
        ("$850M", 850e6), ("$850 million", 850e6), ("$850mm", 850e6), ("$850mn", 850e6), ("$850-million", 850e6),
        ("$1.1 trillion", 1.1e12), ("$1.1tn", 1.1e12), ("$1.1T", 1.1e12), ("$2,500,000", 2.5e6),
        ("$ 3.5 Billion", 3.5e9), ("$400k", 400e3), ("$12", 12.0),
    ],
)
def test_parse_aum_formats(text, value):
    assert parse_aum(f"Firm with {text} in assets") == pytest.approx(value)


def test_parse_aum_does_not_eat_following_words():
    assert parse_aum("$5 more than") == 5.0
    assert parse_aum("no money here") is None


@pytest.mark.parametrize(
    "text, value",
    [
        ("Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors", 1.2e9),
        ("Alder Street team with $400M joins Bluewater", 400e6),
        ("Summit Ridge Advisors, which manages $1.2 billion, keeps its brand", 1.2e9),
        ("Lakeshore, with $640 million in assets, is Atlas's second deal", 640e6),
        ("Northgate and Pinecrest merge to form $4.5B firm", 4.5e9),
        ("Oakmont oversees $2.3 billion for 60 families", 2.3e9),
        ("Wirehouse Team Managing $2.1 Billion Breaks Away", 2.1e9),
        ("a $1.1bn multifamily office", 1.1e9),
        # not AUM
        ("FINRA fines broker-dealer $1.5 million over supervision lapses", None),
        ("SEC charges Ohio adviser in $3M cherry-picking scheme", None),
        ("The launch follows a $40 million funding round.", None),
        ("Pricing starts at $95 per advisor per month.", None),
        ("The adviser allegedly diverted $1.4 million from clients", None),
        ("Interval fund assets topped $100 billion for the first time", None),
        ("Firm agrees to pay $2 million penalty", None),
    ],
)
def test_extract_aum_context(text, value):
    assert extract_aum(text) == (pytest.approx(value) if value else None)


STOP = load_stoplist()


@pytest.mark.parametrize(
    "text, firms",
    [
        ("Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors", ["Harborview Wealth Partners", "Summit Ridge Advisors"]),
        ("Harborview Wealth Partners Acquires $1.2B Summit Ridge Advisors", ["Harborview Wealth Partners", "Summit Ridge Advisors"]),
        ("PE-Backed Crestline Wealth to Buy Riverbend Financial and Aspen Grove Advisors",
         ["Crestline Wealth", "Riverbend Financial", "Aspen Grove Advisors"]),
        ("Blue Heron Capital Takes Minority Stake In Oakmont Family Office", ["Blue Heron Capital", "Oakmont Family Office"]),
        ("Goldman Sachs Asset Management Launches Two Active ETFs", ["Goldman Sachs Asset Management"]),
        ("Lakeshore Financial Group agrees to be acquired by Atlas Wealth Management", ["Lakeshore Financial Group", "Atlas Wealth Management"]),
        ("Acme Wealth Partners LLC files Form ADV", ["Acme Wealth Partners"]),
        ("Bank of Montreal Private Wealth hires", ["Bank of Montreal Private Wealth"]),
        ("Wealth Enhancement Group's CEO speaks", ["Wealth Enhancement Group"]),
        # false positives (generic phrases, people, sentence boundaries)
        ("How Financial Advisors Can Use Private Credit", []),
        ("SEC Charges Ohio Investment Adviser With Cherry-Picking Scheme", []),
        ("What Wealth Management Firms Get Wrong About Family Offices", []),
        ("SEC Proposes Revamp of Custody Rule for Crypto Assets. Advisors would face new rules.", []),
        ("Financial Planning Association honors members", []),
        ("Private Equity Keeps Buying RIAs", []),
        ("Capital Markets Outlook For Q4", []),
    ],
)
def test_extract_firms(text, firms):
    assert extract_firms(text, STOP) == firms


def test_firm_spans_do_not_cross_sentences():
    assert firm_spans("Meridian Capital Partners adds $850M Cedar Lane Private Wealth. Meridian Capital Partners grows.") == [
        "Meridian Capital Partners", "Cedar Lane Private Wealth", "Meridian Capital Partners"]


def test_watchlist_alias_mapped_to_display_name():
    alias_map = {"coldstream wealth management": "Coldstream"}
    assert extract_firms("Coldstream Wealth Management Opens Portland Office", STOP, alias_map) == ["Coldstream"]


def test_trending_firms(ingested):
    import sqlite3

    from wealthwire import paths

    from .conftest import NOW

    conn = sqlite3.connect(paths.db_path())
    conn.row_factory = sqlite3.Row
    rows = trending_firms(conn, days=7, now=NOW)
    ranked = {r["firm"]: r["stories"] for r in rows}
    # Harborview: the Summit Ridge deal + the breakaway team → 2 distinct clusters (not 7 items)
    assert ranked["Harborview Wealth Partners"] == 2
    assert rows[0]["stories"] >= rows[-1]["stories"]
    assert "Goldman Sachs" in ranked and "Coldstream" in ranked
    assert trending_firms(conn, days=7, now=NOW.replace(year=2027)) == []
