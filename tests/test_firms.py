"""§4 firm matching: aliases, precision guards, and precision/recall on 75 real labeled headlines."""
import csv
from pathlib import Path

import pytest

from wealthwire.firmeval import evaluate
from wealthwire.firms import SecMatcher, aliases_for, load_curated, normalize, pretty_name

FIX = Path(__file__).parent / "fixtures"


def eval_rows():
    lines = [l for l in (FIX / "sec_firms_eval.csv").read_text().splitlines() if not l.startswith("#")]
    return [dict(crd=r["Organization CRD#"], legal_name=r["Legal Name"], business_name=r["Primary Business Name"],
                 aum_usd=float(r["5F(2)(c)"]), state=r["Main Office State"]) for r in csv.DictReader(lines)]


@pytest.fixture(scope="module")
def matcher():
    return SecMatcher(eval_rows(), load_curated())


def found(m, text):
    return [m.display(c) for c in m.firms_in(text)]


def test_alias_generation():
    assert aliases_for("Raymond James & Associates, Inc.") == ["raymond james and associates", "raymond james"]
    assert aliases_for("SUMMIT WEALTH PARTNERS LLC") == ["summit wealth partners", "summit wealth", "summit"]
    assert aliases_for("J.P. Morgan Securities LLC") == ["j p morgan securities", "j p morgan"]
    assert aliases_for("First Capital Advisors") == []          # only generic words
    assert aliases_for("The Bahnsen Group, LLC") == ["bahnsen group", "bahnsen"]


def test_normalize_and_display():
    assert normalize("Goldman Sachs’ unit & J.P. Morgan: Crypto Assets. Advisors") == \
        "goldman sachs unit and j p morgan | crypto assets | advisors"
    assert pretty_name("MERCER GLOBAL ADVISORS INC.") == "Mercer Global Advisors"
    assert pretty_name("LPL FINANCIAL LLC") == "LPL Financial"
    assert pretty_name("SHUFRO, ROSE & CO., LLC") == "Shufro, Rose"


@pytest.mark.parametrize("text, expected", [
    ("Mercer Advisors hires Goldman alum", ["Mercer Advisors", "Goldman Sachs"]),
    ("Captrust Adds $1.2B in Double Deal", ["Captrust"]),
    ("LPL adds $1 billion teams", ["LPL Financial"]),
    ("Obama headlines Creative Planning event", ["Creative Planning"]),
    ("Judge Upholds Award in J.P. Morgan 'Deli Platter' Dispute", ["J.P. Morgan Securities"]),
    ("Q&A: Charlesbank's David Katz on RIAs", ["Charlesbank"]),
    ("Raymond James Attracts Two Teams", ["Raymond James & Associates"]),
    # precision guards
    ("Mercer raises fees", []),                             # single common word ("Mercer-style ambiguity")
    ("Reaching the summit of wealth planning", []),         # lowercase common words
    ("Summit Wealth joins the Summit Financial conference", ["Summit Financial"]),  # "summit wealth" is ambiguous (2 firms)
    ("Focus on the Pinnacle of Service", []),
    ("creative planning ideas for clients", []),            # all-dictionary alias must be Title Cased
    ("Northwestern Mutual picks Jump for enterprise AI", ["Northwestern Mutual"]),  # "Jump" alone never matches
    ("SEIA Partners With Invent to Unify Data", ["SEIA"]),  # "Invent" alone never matches
    ("Mission accomplished. Wealth firms grow", []),        # never spans a sentence boundary ("mission wealth")
])
def test_matching_cases(matcher, text, expected):
    assert found(matcher, text) == expected


def test_longest_match_wins(matcher):
    ms = matcher.match("Goldman Sachs Asset Management launches ETFs")
    assert [(m.alias, matcher.display(m.crd)) for m in ms] == [("goldman sachs asset management", "Goldman Sachs Asset Management")]


def test_precision_recall_on_real_headlines(matcher):
    rep = evaluate(matcher)
    assert rep["headlines"] >= 60
    assert rep["precision"] >= 0.9, rep
    assert rep["recall"] >= 0.8, rep
    generated_only = evaluate(SecMatcher(eval_rows(), {}))
    assert generated_only["precision"] >= 0.9 and generated_only["recall"] >= 0.65


def test_curated_aliases_resolve_against_sec_names():
    m = SecMatcher(eval_rows(), {"Vanguard": "The Vanguard Group, Inc.", "Nope": "No Such Firm LLC"})
    assert found(m, "Altruist is acquired by Vanguard") == ["Vanguard"]
    assert found(m, "at the vanguard of change") == []      # curated aliases must be capitalized
    assert m.curated_unresolved == ["Nope"]


GUARD_ROWS = [
    {"crd": "1", "legal_name": "PEIRCE CAPITAL MANAGEMENT LLC", "business_name": "PEIRCE CAPITAL MANAGEMENT", "aum_usd": 1e8},
    {"crd": "2", "legal_name": "WISCONSIN CAPITAL MANAGEMENT, LLC", "business_name": "", "aum_usd": 1e8},
    {"crd": "3", "legal_name": "LONG ISLAND WEALTH MANAGEMENT INC", "business_name": "", "aum_usd": 1e8},
    {"crd": "4", "legal_name": "M & A CONSULTING GROUP, LLC", "business_name": "CAM INVESTOR SOLUTIONS", "aum_usd": 1e8},
    {"crd": "5", "legal_name": "MCP MANAGEMENT, LP", "business_name": "", "aum_usd": 1e8},
    {"crd": "6", "legal_name": "TRUSTAGE INVESTMENT MANAGEMENT", "business_name": "MEMBERS CAPITAL ADVISORS", "aum_usd": 1e8},
    {"crd": "7", "legal_name": "WELLS FINANCIAL ADVISORS, INC.", "business_name": "TSW WEALTH MANAGEMENT", "aum_usd": 1e8},
    {"crd": "8", "legal_name": "CARSON GROUP INVESTING, LLC", "business_name": "", "aum_usd": 2e9},
    {"crd": "9", "legal_name": "CARSON ADVISORY, INC.", "business_name": "CARSON ADVISORY GROUP", "aum_usd": 8e8},
    {"crd": "10", "legal_name": "&PARTNERS", "business_name": "&PARTNERS", "aum_usd": 3e10},
]


@pytest.mark.parametrize("headline", [
    "SEC Commissioner Peirce to leave agency",                       # surname
    "Succession drives Wisconsin advisory team to Carson Group",     # state (Carson is expected, Wisconsin not)
    "Captrust Adds $1.2B in Double Deal for Long Island Firms",      # place
    "RIA M&A Activity Plummets 19% in Q3",                           # 1-2 letter tokens
    "Milemarker Launches Advisory Firm MCP AI Server",               # short acronym
    "SEC Alleges Man Defrauded Law Enforcement Members In Scheme",   # inflected dictionary word
    "Dumbfounded Arbitrator Slams Elder Abuse Claim Against Wells Vet",  # surname-like single token
])
def test_real_world_false_positives_are_guarded(headline):
    m = SecMatcher(GUARD_ROWS, {})
    names = {m.display(c) for c in m.firms_in(headline)}
    assert names <= {"Carson Group Investing"}, names


def test_brand_resolution_and_curated_ampersand():
    m = SecMatcher(GUARD_ROWS, {"&Partners": "&PARTNERS"})
    assert [m.display(c) for c in m.firms_in("Succession drives advisory team to Carson Group")] == ["Carson Group Investing"]
    assert m.firms_in("$744 Million Wells Fargo Team Joins &Partners in Missouri") == ["10"]
