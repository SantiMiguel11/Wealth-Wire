"""Group items from different outlets about the same story (rapidfuzz, no embeddings)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta

from rapidfuzz import fuzz

from .dates import from_iso
from .extract import money_spans

STOPWORDS = set(
    """a an the and or but of to in on for with at by from as into over after amid about is are was were be been being
    its it this that these those his her their our your you we they he she new says said will would could should may might
    how why what when where who which than then just more most up out via vs ria rias firm firms s""".split()
)
# Headline verbs that mean the same thing across outlets.
SYNONYMS = {
    "buys": "acquire", "buy": "acquire", "bought": "acquire", "acquires": "acquire", "acquired": "acquire",
    "acquiring": "acquire", "acquisition": "acquire", "scoops": "acquire", "snaps": "acquire",
    "adviser": "advisor", "advisers": "advisor", "advisors": "advisor", "advisory": "advisor",
    "launches": "launch", "launched": "launch", "unveils": "launch", "debuts": "launch", "rolls": "launch", "introduces": "launch",
    "merges": "merge", "merger": "merge", "merged": "merge", "combine": "merge", "combines": "merge",
    "hires": "hire", "hired": "hire", "joins": "join", "joined": "join", "charges": "charge", "charged": "charge",
    "fines": "fine", "fined": "fine", "proposes": "propose", "proposed": "propose", "proposal": "propose",
    "changes": "change", "revamp": "change", "overhaul": "change", "two": "2", "three": "3", "four": "4", "pair": "2",
    "holds": "hold", "steady": "hold", "etfs": "etf", "funds": "fund", "rates": "rate", "failures": "failure",
    "lapses": "failure", "lapse": "failure", "cutting": "cut", "cuts": "cut", "layoffs": "cut", "workforce": "staff",
    "jobs": "staff", "employees": "staff", "workers": "staff",
}
_SUFFIX = re.compile(r"\s+[|–—-]\s+[\w.&' ]{2,40}$")
_PUNCT = re.compile(r"[^\w\s]")


def _money_token(value: float) -> str:
    if value >= 1e9:
        return f"usd{value / 1e9:.3g}b"
    return f"usd{value / 1e6:.3g}m"


def normalize_title(title: str) -> str:
    t = _SUFFIX.sub("", title or "")
    # canonicalize money so "$1.2B", "$1.2 billion" and "$1.2-billion" compare equal
    out, last = [], 0
    for start, end, value in money_spans(t):
        out.append(t[last:start])
        out.append(" " + _money_token(value) + " ")
        last = end
    out.append(t[last:])
    t = "".join(out).lower().replace("’", "'").replace("'s ", " ")
    t = t.replace("-", " ")
    t = _PUNCT.sub(" ", t)
    words = []
    for w in t.split():
        if w in STOPWORDS:
            continue
        w = SYNONYMS.get(w, w)
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss") and not w.startswith("usd"):
            w = w[:-1]
        words.append(w)
    return " ".join(words)


def title_money(title: str) -> set[float]:
    return {round(v, -5) for _, _, v in money_spans(title) if v >= 1e6}


@dataclass
class ClusterItem:
    id: int
    source: str
    published_at: str
    title: str
    norm: str = ""
    firms: set[str] = field(default_factory=set)
    money: set[float] = field(default_factory=set)
    category: str = ""

    def __post_init__(self):
        self.norm = self.norm or normalize_title(self.title)
        self.money = self.money or title_money(self.title)
        self._dt = from_iso(self.published_at)


def score(a: ClusterItem, b: ClusterItem) -> float:
    """0–100 similarity: fuzzy title score plus firm/AUM evidence."""
    if not a.norm or not b.norm:
        return 0.0
    base = 0.6 * fuzz.token_set_ratio(a.norm, b.norm) + 0.4 * fuzz.token_sort_ratio(a.norm, b.norm)
    shared_tokens = set(a.norm.split()) & set(b.norm.split())
    fa, fb = {f.lower() for f in a.firms}, {f.lower() for f in b.firms}
    shared_firms = fa & fb
    if shared_firms:
        only_a, only_b = fa - fb, fb - fa
        if only_a and only_b:
            base -= 20      # "Atlas buys Lakeshore" vs "Atlas buys Brookfield": same acquirer, different deals
        elif only_a or only_b:
            base += 4
        else:
            base += 12
    elif fa and fb:
        base -= 10          # both name firms, none in common
    if a.money and b.money:
        base += 10 if a.money & b.money else -10
    ta, tb = a.norm.split(), b.norm.split()
    nums_a = {t for t in ta if t.isdigit()}
    nums_b = {t for t in tb if t.isdigit()}
    if nums_a and nums_b and not nums_a & nums_b:
        base -= 30          # "Weekend Reading (Sept 20-21)" vs "(Sept 27-28)": recurring column, different issue
    elif len(ta) >= 3 and ta[:3] == tb[:3]:
        base += 8           # same lead ("fed hold rate …") — outlets differ mostly in the tail
    if a.category and b.category and a.category != b.category:
        base -= 8
    if len(shared_tokens) < 2:
        base = min(base, 50.0)
    return max(0.0, min(100.0, base))


def cluster(items: list[ClusterItem], threshold: float = 70, window_hours: float = 72) -> list[list[ClusterItem]]:
    """Union-find over pairs from *different* sources published within the window."""
    parent = {it.id: it.id for it in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    ordered = sorted(items, key=lambda it: it._dt)
    window = timedelta(hours=window_hours)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if b._dt - a._dt > window:
                break
            if a.source == b.source or find(a.id) == find(b.id):
                continue
            if score(a, b) >= threshold:
                parent[find(b.id)] = find(a.id)
    groups: dict[int, list[ClusterItem]] = {}
    for it in items:
        groups.setdefault(find(it.id), []).append(it)
    return list(groups.values())
