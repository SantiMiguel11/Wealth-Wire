"""M&A tracker: acquirer / target / target AUM from headlines. Blank + low confidence rather than a guess."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import DESCRIPTOR_PREFIX, MONEY, money_spans

V = r"\s+"
PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # (deal_type, roles, regex) — roles tells which named group is the acquirer ("a") and target ("b")
    ("acquisition", "b_by_a", re.compile(r"^(?P<b>.+?)\s+(?:agrees to be acquired by|to be acquired by|is acquired by|acquired by|to be bought by|bought by)\s+(?P<a>.+)$", re.I)),
    ("stake", "b_to_a", re.compile(r"^(?P<b>.+?)\s+(?:sells?|to sell|agrees to sell)\s+(?:an?\s+)?(?:minority|majority|significant|strategic|non-controlling)?\s*stake\s+to\s+(?P<a>.+)$", re.I)),
    ("acquisition", "b_to_a", re.compile(r"^(?P<b>.+?)\s+(?:sells|sold|to sell|agrees to sell)\s+(?:itself\s+|firm\s+|business\s+)?to\s+(?P<a>.+)$", re.I)),
    ("stake", "a_in_b", re.compile(r"^(?P<a>.+?)\s+(?:takes?|to take|acquires?|buys?|to buy|makes?|to make|announces|completes)\s+(?:an?\s+)?(?:minority|majority|strategic|significant|non-controlling|controlling|growth)?\s*(?:equity\s+)?(?:stake|investment)\s+in\s+(?P<b>.+)$", re.I)),
    ("stake", "b_from_a", re.compile(r"^(?P<b>.+?)\s+(?:lands|gets|receives|secures|takes|accepts|announces|nabs)\s+(?:an?\s+)?(?:minority|majority|strategic|significant|growth)?\s*(?:equity\s+)?(?:stake|investment)\s+from\s+(?P<a>.+)$", re.I)),
    ("recapitalization", "b_with_a", re.compile(r"^(?P<b>.+?)\s+(?:completes|announces|closes|finalizes)?\s*(?:an?\s+)?(?:recapitalization|recap)\s+(?:with|led by|backed by)\s+(?P<a>.+)$", re.I)),
    ("recapitalization", "b_with_a", re.compile(r"^(?P<b>.+?)\s+recapitalizes\s+(?:with|via)\s+(?P<a>.+)$", re.I)),
    ("recapitalization", "a_of_b", re.compile(r"^(?P<a>.+?)\s+(?:leads|backs|completes)\s+(?:an?\s+)?recapitalization of\s+(?P<b>.+)$", re.I)),
    ("merger", "a_and_b", re.compile(r"^(?P<a>.+?)\s+(?:and|&)\s+(?P<b>.+?)\s+(?:to merge|agree to merge|merge|announce merger|complete merger|combine|to combine)\b.*$", re.I)),
    ("merger", "a_with_b", re.compile(r"^(?P<a>.+?)\s+(?:merges|to merge|will merge|agrees to merge|combines)\s+with\s+(?P<b>.+)$", re.I)),
    ("acquisition", "a_b", re.compile(
        r"^(?P<a>.+?)\s+(?:agrees to acquire|agrees to buy|to acquire|to buy|acquires|buys|completes acquisition of|closes acquisition of|"
        r"announces acquisition of|completes purchase of|closes on|scoops up|snaps up|picks up|adds)\s+(?P<b>.+)$", re.I)),
]

# Where a party name ends: punctuation, or a clause introduced by one of these words.
_CUT = re.compile(
    r"\s*(?:[,;:(]|\s[-–—]\s|—|–)|\s+(?:in|to|for|as|after|amid|with|worth|valued|from|at|on|while|marking|its|and\s+(?=[a-z]))\b",
)
_APPOSITIVE_AUM = re.compile(
    r"^\s*(?:,\s*(?:an?\s+|which\s+(?:manages|oversees)\s+|managing\s+|overseeing\s+|with\s+)?|\(\s*|\s+with\s+|\s+managing\s+|\s+overseeing\s+)"
    r"(?P<money>" + MONEY.pattern + r")",
    re.I,
)
_GENERIC = {
    "ria", "rias", "firm", "firms", "team", "teams", "advisor", "advisors", "adviser", "advisers", "practice", "wealth",
    "manager", "managers", "business", "shop", "office", "family", "multifamily", "independent", "hybrid", "texas", "rival",
    "two", "three", "another", "stake", "minority", "majority", "undisclosed", "breakaway", "consolidator", "acquirer",
}
_NAME_WORD = re.compile(r"^(?:[A-Z0-9][\w.&'’-]*|&|of|de|la|the)$")


@dataclass
class Deal:
    acquirer: str = ""
    target: str = ""
    target_aum_usd: float | None = None
    deal_type: str = ""
    confidence: str = "low"
    notes: list[str] = field(default_factory=list)

    @property
    def note(self) -> str:
        return "; ".join(self.notes)


def _prep(title: str) -> str:
    title = re.sub(r"\s+[|]\s+.*$", "", title.strip())
    if ":" in title:  # "Exclusive: X acquires Y" / "RIA roundup: …"
        head, tail = title.rsplit(":", 1)
        if len(head.split()) <= 4 and tail.strip():
            title = tail.strip()
    return title


def _strip_prefix(text: str) -> tuple[str, list[float]]:
    """Remove leading descriptors and dollar figures ('$1.2bn RIA Summit' → 'Summit'). Returns stripped figures."""
    figures: list[float] = []
    prev = None
    while prev != text:
        prev = text
        m = MONEY.match(text)
        if m:
            figures.append(money_spans(m.group(0))[0][2])
            text = text[m.end():].lstrip(" -")
        text = DESCRIPTOR_PREFIX.sub("", text)
        text = re.sub(r"^(?:[\w-]+\s+)?(?i:ria|rias|wealth manager|advisory firm|firm|multifamily office|family office|practice|shop|breakaway)\s+(?=[A-Z])", "", text)
    return text.strip(), figures


def _clean_party(raw: str) -> tuple[str, str, str, list[float]]:
    """→ (name, tail, problem, prefix_figures). Name is '' when it isn't a clean proper noun."""
    raw = raw.strip()
    stripped, figures = _strip_prefix(raw)
    m = _CUT.search(stripped)
    name, tail = (stripped[: m.start()], stripped[m.start():]) if m else (stripped, "")
    name = name.strip(" .'’\"")
    if re.match(r"^\s*,\s*(?!(?:Inc|LLC|LP|Ltd)\b)[A-Z]", tail):
        return "", tail, "multiple parties or unclear apposition", figures
    if re.search(r"\s(?:and|&)\s", name) and len(name.split()) > 3:
        return "", tail, "multiple parties", figures
    words = name.split()
    if not words:
        return "", tail, "no name", figures
    if len(words) > 7:
        return "", tail, "name too long", figures
    if not all(_NAME_WORD.match(w) for w in words) or not _NAME_WORD.match(words[0]) or words[0][0].islower():
        return "", tail, f"not a proper name: {name!r}", figures
    if all(w.lower().strip("'’s") in _GENERIC or MONEY.match(w) for w in words):
        return "", tail, f"generic description: {name!r}", figures
    if words[-1].lower() in {"ria", "rias", "firm", "team", "practice"}:
        return "", tail, f"descriptive, not a name: {name!r}", figures
    return re.sub(r"'s$|’s$", "", name), tail, "", figures


def extract_deal(title: str) -> Deal | None:
    """Parse one headline. None when no M&A pattern matches."""
    text = _prep(title)
    for deal_type, roles, pat in PATTERNS:
        m = pat.match(text)
        if not m:
            continue
        deal = Deal(deal_type=deal_type)
        a_raw, b_raw = m.group("a"), m.group("b")
        # acquirer: for patterns where it comes first, it's everything before the verb
        acq, acq_tail, acq_problem, acq_prefix = _clean_party(a_raw)
        tgt, tgt_tail, tgt_problem, tgt_prefix = _clean_party(b_raw)
        if acq_problem:
            deal.notes.append(f"acquirer unclear ({acq_problem})")
        if tgt_problem:
            deal.notes.append(f"target unclear ({tgt_problem})")
        deal.acquirer, deal.target = acq, tgt

        # --- target AUM: only a figure attached to the target (its prefix or its own appositive) ---
        def attached(prefix: list[float], tail: str) -> list[float]:
            figs = list(prefix)
            app = _APPOSITIVE_AUM.match(tail or "")
            if app:
                figs.append(money_spans(app.group("money"))[0][2])
            return [round(f, -5) for f in figs if f >= 1e6]

        candidates = sorted(set(attached(tgt_prefix, tgt_tail)))
        acq_figs = set(attached(acq_prefix, acq_tail))
        if deal_type == "merger":
            acq_figs |= set(candidates)
            candidates = []  # neither side is a "target"; a combined figure is not a target's AUM
        other = [v for _, _, v in money_spans(text) if v >= 1e6 and round(v, -5) not in set(candidates) | acq_figs]
        unexplained = [v for v in other if not _is_price_or_combined(text, v)]
        if len(candidates) == 1:
            deal.target_aum_usd = candidates[0]
        elif len(candidates) > 1:
            deal.notes.append("several figures attached to the target")
        if unexplained and not deal.target_aum_usd and deal_type != "merger":
            deal.notes.append("dollar figure in headline could be AUM or price")

        ok = bool(deal.acquirer and deal.target) and not deal.notes
        deal.confidence = "high" if ok else "low"
        return deal
    return None


def _is_price_or_combined(text: str, value: float) -> bool:
    for start, _, v in money_spans(text):
        if round(v, -5) != round(value, -5):
            continue
        before = text[max(0, start - 40): start].lower()
        if re.search(r"\b(for|paying|pays|priced at|valued at|valuing|worth)\s*$", before):
            return True
        if re.search(r"\b(to form|to create|creating|forming|combined|bringing|to reach|with a combined)\b[^$]*$", before):
            return True
    return False


def deal_for_cluster(titles: list[str]) -> Deal:
    """Best parse across a cluster's headlines (earliest first). Items that agree on both parties can fill
    in a missing AUM; disagreement leaves it blank."""
    parsed = [d for d in (extract_deal(t) for t in titles) if d]
    if not parsed:
        return Deal(confidence="low", notes=["no deal pattern matched the headlines"])
    highs = [d for d in parsed if d.confidence == "high"]
    best = highs[0] if highs else parsed[0]
    if best.confidence == "high" and best.target_aum_usd is None:
        same = {
            d.target_aum_usd for d in highs[1:]
            if d.target_aum_usd and d.acquirer.lower() == best.acquirer.lower() and d.target.lower() == best.target.lower()
        }
        if len(same) == 1:
            best.target_aum_usd = same.pop()
    if highs:
        conflicting = {(d.acquirer.lower(), d.target.lower()) for d in highs}
        if len(conflicting) > 1 and not _same_parties(conflicting):
            best.notes.append("outlets disagree on the parties")
            best.acquirer, best.target, best.target_aum_usd, best.confidence = "", "", None, "low"
    return best


def _same_parties(pairs: set[tuple[str, str]]) -> bool:
    """Tolerate 'Mariner' vs 'Mariner Wealth Advisors' — one name a prefix of the other."""
    pairs = list(pairs)
    a0, t0 = pairs[0]
    for a, t in pairs[1:]:
        if not (a.startswith(a0) or a0.startswith(a)) or not (t.startswith(t0) or t0.startswith(t)):
            return False
    return True
