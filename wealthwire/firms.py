"""Firm detection against SEC adviser data (§4): normalized names + aliases, Aho-Corasick multi-pattern matching.

Aliases per firm (from its primary business name and its legal name):
  - the full normalized name, legal suffixes stripped ("Mercer Global Advisors Inc." → "mercer global advisors");
  - progressively shorter prefixes with trailing generic words dropped
    ("summit wealth partners" → "summit wealth" → "summit").

Precision guards:
  - aliases made only of generic words ("capital management", "wealth partners") are never used;
  - a single-word alias is used on its own only if it is *distinctive*: not an English dictionary word, ≥3
    letters, and capitalized where it appears ("Captrust", "Hightower", "LPL" — but never "Summit", "Focus",
    "Pinnacle", "Mercer", which only match with a following firm word, e.g. "Mercer Advisors");
  - a multi-word alias built only from dictionary/generic words ("Creative Planning", "Summit Wealth") must
    appear Title Cased in the text;
  - an alias shared by several firms goes to the one whose full name it is; otherwise, if the alias contains a
    distinctive word, to the largest firm by AUM (brand-level, e.g. "Goldman Sachs"); otherwise it is dropped
    as ambiguous;
  - sentence punctuation (: ; , . ! ? | quotes) is a hard boundary; a match never spans it;
  - overlapping matches keep the longest.
Firms not in the SEC data still come from the old regex heuristics, marked unverified.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache

import ahocorasick

GENERIC = set("""
wealth capital advisors advisor advisers adviser advisory partners partner financial finance group management managers
private asset assets investment investments investors investor family office offices planning planners planner
consulting consultants services service strategies strategy securities trust trustco company co and of the llc inc
lp llp ltd corp corporation holdings holding global national international america american americas us usa united
states retirement fund funds equity counsel associates solutions bank banking research portfolio portfolios markets
market fiduciary fiduciaries wealthcare pllc pc plc na n a inv mgmt mgt grp svcs llc. inc. advisory. of. for in
first new
""".split())
LEGAL_SUFFIX = re.compile(r"(?:[\s,]+(?:llc|l\.l\.c\.?|inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|"
                          r"l\.?p\.?|llp|l\.l\.p\.?|pllc|p\.c\.|pc|na|n\.a\.|plc))+\.?\s*$", re.I)
BOUNDARY = re.compile(r"[:;,!?|\"“”‘()\[\]—–]|\s-\s")
SENTENCE_PERIOD = re.compile(r"(?<=\w{3})\.(?=\s|$)")  # "Assets. Advisors" ends a sentence; "J.P." and "Co." don't
PIPE = " | "


@lru_cache(maxsize=1)
def english_words() -> frozenset:
    try:
        from english_words import get_english_words_set

        return frozenset(get_english_words_set(["web2"], lower=True))
    except Exception:  # pragma: no cover - dependency missing: be conservative, treat nothing as distinctive
        return frozenset()


def strip_legal(name: str) -> str:
    name = LEGAL_SUFFIX.sub("", name.strip())
    return re.sub(r"^the\s+", "", name, flags=re.I).strip(" ,.")


def tokenize(text: str) -> list[tuple[str, str]]:
    """(original, normalized) tokens. Normalized: lowercase, '&' → 'and', possessive 's dropped,
    sentence punctuation → '|' (a hard boundary no alias can span), other punctuation removed."""
    t = (text or "").replace("’", "'")
    t = re.sub(r"(\w)'s\b", r"\1", t)
    t = SENTENCE_PERIOD.sub(PIPE, t)
    t = BOUNDARY.sub(PIPE, t)
    return [(tok, "and" if tok == "&" else tok.lower()) for tok in re.findall(r"\||&|[^\W_]+", t)]


def normalize(text: str) -> str:
    return " ".join(n for _, n in tokenize(text))


def load_curated() -> dict[str, str]:
    from . import paths

    p = paths.config_dir() / "firm_aliases.yaml"
    if not p.exists():
        return {}
    import yaml

    return {str(k): str(v) for k, v in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("aliases", {}).items()}


def pretty_name(name: str) -> str:
    """Display form: legal suffix removed; ALL-CAPS SEC names title-cased (short acronyms kept)."""
    base = strip_legal(name).rstrip(" ,&")
    if base.isupper():
        words = []
        for w in base.split():
            core = re.sub(r"[^A-Z]", "", w)
            keep = (len(core) <= 3 and not re.search(r"[AEIOU]", core)) or w in {"LPL", "RBC", "UBS", "BNY", "EP", "SEIA"}
            words.append(w if keep else ("and" if w == "AND" else w.capitalize()))
        base = " ".join(words)
    return base


def distinctive(token: str) -> bool:
    return len(token) >= 3 and token not in GENERIC and token not in english_words() and not token.isdigit()


def aliases_for(name: str) -> list[str]:
    """Full normalized name, then prefixes with trailing generic words dropped, most specific first."""
    tokens = [t for t in normalize(strip_legal(name)).split() if t != "|"]
    out = []
    while tokens:
        if not all(t in GENERIC for t in tokens):
            out.append(" ".join(tokens))
        if tokens[-1] not in GENERIC:
            break
        tokens = tokens[:-1]
        while tokens and tokens[-1] in {"and", "of", "the", "for", "in"}:
            tokens = tokens[:-1]
    return list(dict.fromkeys(out))


@dataclass(frozen=True)
class FirmMatch:
    crd: str
    alias: str
    start_token: int
    end_token: int  # exclusive


class SecMatcher:
    def __init__(self, rows: list[dict], curated: dict[str, str] | None = None):
        self.firms = {r["crd"]: r for r in rows}
        self.curated_unresolved: list[str] = []
        candidates: dict[str, list[tuple[str, bool]]] = {}  # alias → [(crd, is_full_name)]
        for r in rows:
            names = {r.get("business_name") or "", r.get("legal_name") or ""} - {""}
            for n in names:
                als = aliases_for(n)
                for i, a in enumerate(als):
                    candidates.setdefault(a, []).append((r["crd"], i == 0))
        self.alias_to_crd: dict[str, str] = {}
        for alias, cands in candidates.items():
            toks = alias.split()
            if len(toks) == 1 and not distinctive(toks[0]):
                continue  # "summit", "focus", "pinnacle", "mercer" never match alone
            crds = {c for c, _ in cands}
            if len(crds) == 1:
                self.alias_to_crd[alias] = crds.pop()
                continue
            full = {c for c, is_full in cands if is_full}
            if len(full) == 1:
                self.alias_to_crd[alias] = full.pop()
            elif any(distinctive(t) for t in toks) or (len(toks) >= 2 and not any(t in GENERIC for t in toks)):
                # a brand shared by several registrations ("goldman sachs", "raymond james"): the largest entity
                self.alias_to_crd[alias] = max(crds, key=lambda c: (self.firms[c].get("aum_usd") or 0, c))
            # else: ambiguous generic alias shared by unrelated firms ("summit wealth") → dropped
        # curated brand aliases (firm_aliases.yaml) → CRD via exact normalized legal/business name
        self.curated: set[str] = set()
        by_name: dict[str, str] = {}
        for r in rows:
            for n in (r.get("legal_name"), r.get("business_name")):
                if n:
                    by_name.setdefault(" ".join(t for t in normalize(n).split() if t != "|"), r["crd"])
        for alias, target in (curated or {}).items():
            crd = by_name.get(" ".join(t for t in normalize(target).split() if t != "|"))
            a = " ".join(t for t in normalize(alias).split() if t != "|")
            if not crd or not a:
                self.curated_unresolved.append(alias)
                continue
            self.alias_to_crd[a] = crd
            self.curated.add(a)
        self.automaton = ahocorasick.Automaton()
        for alias in self.alias_to_crd:
            self.automaton.add_word(f" {alias} ", alias)
        if self.alias_to_crd:
            self.automaton.make_automaton()

    @classmethod
    def from_db(cls, conn: sqlite3.Connection, curated: dict[str, str] | None = None) -> "SecMatcher":
        return cls([dict(r) for r in conn.execute("SELECT * FROM sec_firms")], load_curated() if curated is None else curated)

    def __len__(self) -> int:
        return len(self.alias_to_crd)

    def match(self, text: str) -> list[FirmMatch]:
        if not self.alias_to_crd or not text:
            return []
        toks = tokenize(text)
        padded = " " + " ".join(n for _, n in toks) + " "
        starts, pos = {}, 1
        for i, (_, n) in enumerate(toks):
            starts[pos] = i
            pos += len(n) + 1
        found: list[FirmMatch] = []
        for end, alias in self.automaton.iter(padded):
            s = end - len(alias)  # key is " alias ", `end` is its last char → first letter of the alias
            if s not in starts:
                continue
            ti = starts[s]
            words = alias.split()
            n = len(words)
            needs_caps = n == 1 or alias in self.curated or all(w in GENERIC or w in english_words() for w in words)
            if needs_caps and not _capitalized([o for o, _ in toks], ti, n):
                continue
            found.append(FirmMatch(self.alias_to_crd[alias], alias, ti, ti + n))
        # keep the longest non-overlapping matches
        found.sort(key=lambda m: (-(m.end_token - m.start_token), m.start_token))
        taken: set[int] = set()
        out = []
        for m in found:
            span = set(range(m.start_token, m.end_token))
            if span & taken:
                continue
            taken |= span
            out.append(m)
        return sorted(out, key=lambda m: m.start_token)

    def firms_in(self, text: str) -> list[str]:
        """Distinct CRDs mentioned in text, in order of appearance."""
        return list(dict.fromkeys(m.crd for m in self.match(text)))

    def display(self, crd: str) -> str:
        f = self.firms[crd]
        return pretty_name(f.get("business_name") or f.get("legal_name"))


def _capitalized(tokens: list[str], i: int, n: int) -> bool:
    span = tokens[i:i + n]
    if len(span) < n:
        return False
    for w in span:
        if w.lower() in {"and", "of", "the", "for", "in"}:
            continue
        if not (w[:1].isupper() or w[:1].isdigit()):
            return False
    return True
