"""Deals-only filter and industry tags, on real headlines (tests/fixtures/deal_headlines.yaml)."""
from pathlib import Path

import pytest
import yaml

from fiduciarywire import industry
from fiduciarywire.deals import classify

FIX = Path(__file__).parent / "fixtures"
ROWS = yaml.safe_load((FIX / "deal_headlines.yaml").read_text(encoding="utf-8"))["headlines"]


def test_real_headlines_deal_or_not():
    wrong = []
    for r in ROWS:
        d = classify(r["text"])
        if r.get("missed"):
            continue
        if bool(d) != r["deal"]:
            wrong.append(("FP" if d else "FN", r["text"][:90]))
        elif d and (d.acquirer, d.target, d.stage) != (r["acquirer"], r["target"], r["stage"]):
            wrong.append(("parties", r["text"][:70], (d.acquirer, d.target, d.stage), (r["acquirer"], r["target"], r["stage"])))
    assert not wrong, wrong


def test_corpus_is_mostly_not_deals():
    # the point of the change: general news is dropped. 1,300 real headlines, under 10% are deals.
    deals = sum(r["deal"] for r in ROWS)
    assert 80 <= deals <= 130 and len(ROWS) > 1200


@pytest.mark.parametrize("title", [
    "RIA M&A drops 17% in Q3 as mega sellers set new record, DeVoe says",
    "Why RIA M&A Deals Keep Getting Bigger, and What It Means for Your Firm",
    "Vanguard Group Inc. Raises Stake in Apple Inc.",
    "Acadian Asset Management LLC Acquires New Stake in Microsoft",
    "Market Brief: Nvidia Adds $150 Billion to Massive Share Buyback Program",
    "Mercer Advisors Completes $1.9B Debt Refinancing, Adds $340M Credit Facility",
    "Biogen-backed Estuary nabs $93M for kidney disease gene therapy",
    "HB Wealth Adds Family Trio",
    "Merit Financial Snags 10th Commonwealth Advisor",
    "XYPN Adds Income Lab as Member Benefit",
    "Cognition CEO denies report that SpaceX tried to acquire the startup",
    "Le groupe CSL acquiert SIMPL Wireless pour proposer son offre « Critical Connectivity® » en Amérique du Nord",
    "AstraZeneca inks $1.5B insitro deal for AI-enabled target discovery of liver, heart disease drugs",
    "Is now the time to buy bank stocks?",
])
def test_not_deals(title):
    assert classify(title) is None


@pytest.mark.parametrize("title,acq,tgt,stage,value", [
    ("Proofpoint to acquire Varonis Systems in $6.3B all-cash deal", "Proofpoint", "Varonis Systems", "announced", 6.3e9),
    ("Hugging Face reportedly in talks to be acquired for $13B", "", "Hugging Face", "rumored", 13e9),
    ("Paramount closes historic Warner Bros. merger to form Skydance", "Paramount", "Warner Bros", "completed", None),
    ("SMArtX rejected acquisition offer from CAIS to pursue cap raise: Sources", "CAIS", "SMArtX", "terminated", None),
    ("EQT raises Perpetual takeover bid for the fourth time", "EQT", "Perpetual", "bid", None),
    ("AT&T to sell Mexico wireless business to Televisa-Fintech consortium for $2B", "Televisa-Fintech",
     "AT&T’s Mexico wireless business", "announced", 2e9),
    ("Aspen Standard Wealth buys $1B Louisiana RIA Cullen Investment Group", "Aspen Standard Wealth",
     "Cullen Investment Group", "announced", None),  # $1B is the target's AUM, not a price
])
def test_parties_stage_value(title, acq, tgt, stage, value):
    d = classify(title)
    assert (d.acquirer, d.target, d.stage, d.value_usd) == (acq, tgt, stage, value)


def test_industries_multi_label_primary_first():
    assert industry.classify("Thoma Bravo’s Proofpoint inks $6.3bn take-private of data security firm Varonis") == [
        "Private Equity & Asset Management", "Technology"]
    assert industry.classify("UniCredit wins ECB approval to acquire Commerzbank")[0] == "Banking"
    assert industry.classify("Stifel acquires boutique investment bank Acme Partners")[0] == "Investment Banking"
    assert "Banking" not in industry.classify("Stifel acquires boutique investment bank Acme Partners")
    assert industry.classify("Waverly Advisors buys $1.7B Richmond RIA") == ["Wealth Management & RIAs"]
    assert industry.classify("SoftBank in talks to buy US security group Allied Universal") == ["Business Services"]
    assert industry.classify("Acme buys Beta") == ["Other"]
    assert industry.classify("Acme buys Beta", hint="Healthcare & Life Sciences") == ["Healthcare & Life Sciences"]
    assert industry.merge([["Other"], ["Technology"], ["Banking", "Technology"]]) == ["Banking", "Technology"]
