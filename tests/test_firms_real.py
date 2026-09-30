"""Firm matching against a slice of the REAL SEC adviser file (tests/fixtures/sec_firms_real_subset.csv), on all
three labeled headline sets (original, held-out A, blind B). Regression guard for follow-up 1; the slice reproduces
full-file results exactly (scripts/build_eval_dictionary.py verifies that when it builds it)."""
import csv
from pathlib import Path

import pytest

from fiduciarywire.config import load_stoplist
from fiduciarywire.firmeval import evaluate
from fiduciarywire.firms import SecMatcher, load_curated

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def real():
    lines = [l for l in (FIX / "sec_firms_real_subset.csv").read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    rows = [dict(r, aum_usd=float(r["aum_usd"]) if r["aum_usd"] else None) for r in csv.DictReader(lines)]
    return SecMatcher(rows, load_curated(), load_stoplist())


def test_no_curated_alias_is_unresolved(real):
    assert real.curated_unresolved == []


@pytest.mark.parametrize("labels,min_p,min_r", [
    ("firm_headlines_blind.yaml", 0.98, 0.95),     # 133 headlines, 66 mentions (blind pre-fix: 0.902 / 0.833)
    ("firm_headlines_heldout.yaml", 0.98, 0.96),   # 162 headlines, 50 mentions (pre-fix: 0.957 / 0.900)
    ("firm_headlines.yaml", 0.98, 0.93),           # original 75 headlines, 67 mentions
])
def test_precision_recall_on_real_sec_data(real, labels, min_p, min_r):
    r = evaluate(real, FIX / labels)
    errors = [(x["headline"][:70], x["false_positives"], x["missed"]) for x in r["rows"] if x["false_positives"] or x["missed"]]
    assert r["precision"] >= min_p and r["recall"] >= min_r, errors


@pytest.mark.parametrize("headline,expected", [
    ("Concurrent adds $425 million Houston team as breakaway wave continues", ["Concurrent Investment Advisors"]),
    ("EQT raises Perpetual takeover bid for the fourth time", ["EQT Partners"]),
    ("Advisor moves: RBC lands $2B BofA Private Bank duo in La Jolla", ["RBC Capital Markets", "Merrill Lynch, Pierce, Fenner & Smith"]),
    ("FINRA Fines Pictet Overseas and Blue Ocean ATS for AML and Supervisory Violations", ["Pictet Asset Management"]),
    ("Breaking Bad News To A Client About Prior Problematic Financial Decisions: Kitces & Carl 199", []),
    ("SEC Charges Founder and His Two New Jersey-Based Companies in Alleged $16 Million Ponzi Scheme", []),
    ("FINRA Fines UBS Financial $20 Million for Anti-Money Laundering Violations", ["UBS Financial Services"]),
    # blind set B fixes
    ("Insurer and Wealth Manager HUB Rebrands Ahead of Planned IPO", []),                      # "planned" is a word
    ("DTCC Invests in iCapital, Announces Partnership", ["Icapital"]),                           # interior capital
    ("RIA moves: Carson, Mesirow and DayMark add planning teams across three states",
     ["Carson Group Investing", "Mesirow Financial Investment Management", "Daymark Wealth Partners"]),  # CamelCase brand
    ("Goldman Sachs succession plan: John Waldron set to take the top job", ["Goldman Sachs Asset Management"]),  # person
    ("Wedbush Welcomes Wealth Management Leader Jim McDermott as Managing Director", ["Wedbush Securities"]),
    ("RIA moves: Hightower Signature Wealth adds New England reach with $752M Sandy Cove Advisors",
     ["Hightower Advisors", "Sandy Cove Advisors"]),                                         # sub-brand, not a 2nd firm
    ("Northern Trust bulks up family office team with New York hires", ["Northern Trust Investments"]),
    ("XYPN Partners with Jump to Help Advisors Harness the Next Generation of Compliant AI", ["Xypn Sapphire"]),
    ("Trump ETF Brand, Dan Ives Mark Yorkville's Push on Wall Street", ["Yorkville Advisors Global"]),  # "Mark" a verb
])
def test_follow_up_cases(real, headline, expected):
    assert [real.display(c) for c in real.firms_in(headline)] == expected


def test_subject_rule_needs_start_verb_and_capital(real):
    assert real.firms_in("Why Concurrent adds matter for RIAs") == []          # not the headline subject
    assert real.firms_in("Concurrent team moves are rising") == []             # no deal/news verb after it
    assert real.firms_in("concurrent adds pressure to advisors") == []         # not capitalized
    assert real.firms_in("Eqt raises bid") == []                               # short alias must be all caps


def test_camel_case_is_not_acronym_plural_or_mc_name():
    from fiduciarywire.firms import _camel, is_word
    assert _camel("DayMark") and _camel("iCapital") and _camel("FiNet")
    assert not _camel("APIs") and not _camel("SaaS") and not _camel("McDermott") and not _camel("LPL")
    assert is_word("planned") and is_word("planning") and not is_word("coller")
