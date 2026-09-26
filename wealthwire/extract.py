"""Regex/heuristic extraction of AUM figures and firm names. No NLP services."""
from __future__ import annotations

import re

UNITS = {
    "trillion": 1e12, "tn": 1e12, "t": 1e12,
    "billion": 1e9, "bln": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mln": 1e6, "mm": 1e6, "mn": 1e6, "m": 1e6,
    "thousand": 1e3, "k": 1e3,
}
MONEY = re.compile(
    r"\$\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?-?\s?(?P<unit>trillion|billion|million|thousand|tn|bln|bn|mln|mm|mn|b|m|k|t)(?![a-z]))?",
    re.I,
)


def _value(m: re.Match) -> float:
    num = float(m.group("num").replace(",", ""))
    unit = (m.group("unit") or "").lower()
    return num * UNITS.get(unit, 1.0)


def parse_aum(text: str) -> float | None:
    """Normalize the first dollar figure: '$1.2bn' → 1.2e9, '$850mm' → 8.5e8, '$1.1 trillion' → 1.1e12."""
    m = MONEY.search(text or "")
    return _value(m) if m else None


def money_spans(text: str) -> list[tuple[int, int, float]]:
    return [(m.start(), m.end(), _value(m)) for m in MONEY.finditer(text or "")]


# Words near a figure that make it NOT an AUM (fines, prices, funding, frauds…)
_NEG = re.compile(
    r"\b(fine[sd]?|fining|penalt\w*|pays?|paid|paying|settle\w*|restitution|disgorge\w*|raise[sd]?|raising|funding|round|"
    r"price[sd]?|pricing|valued|valuation|revenue|revenues|salary|salaries|bonus\w*|loans?|scheme|stole|stolen|diverted|"
    r"divert\w*|misappropriat\w*|costs?|fees?|fraud\w*|theft|embezzl\w*|ponzi|budget|deficit|sales|profit\w*|income|"
    r"per advisor|per month|per year|a year|annually|inflows?|outflows?|topped|award\w*)\b",
    re.I,
)
_POS_BEFORE = re.compile(
    r"\b(with|managing|manages|managed|overseeing|oversees|oversaw|aum|ria|rias|team|firm|practice|adds?|added|buys?|"
    r"acquires?|acquired|acquiring|to buy|to acquire|of|creating|create|form|forming|advisor|adviser|advisors|advisers|"
    r"assets of)\W*$",
    re.I,
)
_POS_AFTER = re.compile(
    r"^\W*(?:in\s+)?(?:client\s+|total\s+)?(assets|aum|-aum|ria|rias|firm|firms|team|teams|practice|wealth|advisory|"
    r"multifamily|multi-family|family office|book|shop|hybrid|breakaway|advisor|adviser|independent|office|asset manager|"
    r"wealth manager|in aum)\b",
    re.I,
)


def extract_aum(text: str) -> float | None:
    """First dollar figure that reads like assets under management (≥ $1M, asset context, not a fine/price)."""
    for start, end, value in money_spans(text):
        if value < 1e6:
            continue
        before = text[max(0, start - 32) : start]
        after = text[end : end + 32]
        near_before = " ".join(before.split()[-3:])
        near_after = " ".join(after.split()[:3])
        if _NEG.search(near_before) or _NEG.search(near_after):
            continue
        if _POS_BEFORE.search(before) or _POS_AFTER.search(after):
            return value
    return None


# ------------------------------------------------------------------------------------------------
# Firm names
# ------------------------------------------------------------------------------------------------
FIRM_WORDS = {
    "wealth", "capital", "advisors", "advisers", "advisor", "adviser", "advisory", "partners", "financial", "group",
    "management", "private", "asset", "assets", "investments", "investment", "llc", "inc", "family", "office",
}
# Words that are firm-words but too generic to be a name by themselves.
GENERIC = FIRM_WORDS | {"the", "global", "national", "first", "new", "american", "us", "u.s.", "united", "states", "and", "&", "of"}
# Headline words that end a name span even when Title-Cased.
BREAK = {
    "a", "an", "the", "and", "or", "but", "to", "with", "in", "for", "from", "of the", "at", "on", "by", "as", "after",
    "amid", "over", "into", "via", "vs", "vs.", "its", "his", "her", "their", "our", "this", "that", "these", "who", "which",
    "acquires", "acquire", "acquired", "acquiring", "acquisition", "buys", "buy", "bought", "sells", "sell", "sold", "sale",
    "merges", "merge", "merger", "merging", "takes", "take", "stake", "joins", "join", "joined", "hires", "hire", "hired",
    "names", "named", "adds", "add", "added", "launches", "launch", "launched", "unveils", "unveil", "debuts", "rolls",
    "expands", "expand", "opens", "open", "completes", "complete", "closes", "lands", "land", "makes", "make", "agrees",
    "agree", "be", "is", "are", "was", "were", "has", "have", "had", "will", "says", "said", "say", "plans", "plan",
    "announces", "announce", "reports", "report", "sees", "see", "gets", "wins", "loses", "leaves", "departs", "exits",
    "moves", "move", "breaks", "break", "away", "jumps", "taps", "appoints", "promotes", "retires", "steps", "down",
    "fined", "fines", "charges", "charged", "sues", "sued", "settles", "bars", "barred", "backs", "backed", "invests",
    "minority", "majority", "strategic", "deal", "deals", "team", "teams", "ceo", "cio", "coo", "cfo", "president",
    "chief", "head", "chair", "founder", "co-founder", "partner", "why", "how", "what", "when", "where", "new", "former",
    "ex", "exclusive", "breaking", "update", "q&a", "podcast", "video", "webinar", "etf", "etfs", "fund", "funds",
    "pair", "two", "three", "four", "five", "record", "top", "best", "announcement", "portland", "strikes",
    "recapitalization", "recap", "investing", "can", "could", "should", "would", "may", "might", "must", "use",
    "uses", "get", "keep", "keeps", "need", "needs", "want", "wants", "do", "does", "get", "gets", "know", "tell", "should",
    "buying", "selling", "hiring", "growing", "building", "tips", "lessons", "ways", "outlook", "q1", "q2", "q3", "q4",
}
# Allowed inside a firm name even though they are also in BREAK (only when followed by a capitalized word).
CONNECT = {"&", "of"}
DESCRIPTOR_PREFIX = re.compile(
    r"^(?:(?:exclusive|breaking|report|ria|rias|pe|wirehouse|breakaway|hybrid|independent|serial|giant|firm|boutique|"
    r"consolidator|aggregator|custodian|broker-dealer|bd|insurer|former|ex|new|the|a|an|[\w-]+-backed|[\w-]+-based)\s+)+",
    re.I,
)
_CHUNK_SPLIT = re.compile(r"[,;:()\[\]|!?\"“”]|\s[-–—]\s|—|–")
_CAP = re.compile(r"^(?:[A-Z][\w.&'’-]*|[A-Z0-9]{2,}[\w&-]*)$")


ABBREV = {"inc", "corp", "ltd", "llc", "co", "jr", "sr", "bros"}


def _norm_word(w: str) -> tuple[str, bool]:
    """Strip trailing punctuation / possessive. Returns (word, ended) where ended means the name stops here."""
    ended = False
    core = w.rstrip(".'’")
    # a word ending a sentence ("Assets.") ends the span; abbreviations ("Inc.", "U.S.") don't
    if w.endswith(".") and len(core) > 3 and core.lower() not in ABBREV and "." not in core:
        ended = True
    w = w.strip(".'’")
    if w.endswith(("'s", "’s")):
        w, ended = w[:-2], True
    return w, ended


def normalize_firm(name: str) -> str:
    name = re.sub(r"[\s,]+(?:llc|inc|co|corp|l\.l\.c|lp|ltd)\.?$", "", name.strip(), flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" .,'’")


def firm_spans(text: str) -> list[str]:
    """Capitalized spans containing a firm word plus at least one distinctive word."""
    found: list[str] = []
    for chunk in _CHUNK_SPLIT.split(text or ""):
        words = chunk.split()
        spans: list[list[str]] = []
        cur: list[str] = []
        for i, raw in enumerate(words):
            w, ended = _norm_word(raw)
            low = w.lower()
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if cur and low in CONNECT and _CAP.match(nxt or ""):
                cur.append(w)
                continue
            if w and _CAP.match(w) and low not in BREAK and not MONEY.match(raw):
                cur.append(w)
                if ended:
                    spans.append(cur)
                    cur = []
                continue
            if cur:
                spans.append(cur)
            cur = []
        if cur:
            spans.append(cur)
        for span in spans:
            name = DESCRIPTOR_PREFIX.sub("", " ".join(span)).split()
            # trim trailing words after the last firm word ("Summit Ridge Advisors Deal" → "Summit Ridge Advisors")
            idx = [i for i, w in enumerate(name) if w.lower() in FIRM_WORDS]
            if not idx:
                continue
            name = name[: idx[-1] + 1]
            while name and name[-1].lower() in CONNECT:
                name.pop()
            if not name or len(name) > 6:
                continue
            if not any(w.lower() not in GENERIC for w in name):
                continue  # e.g. "Private Wealth", "Capital Group"
            if name[-1].lower() == "family":  # "X Family" without "Office"
                continue
            if name[-1].lower() in ("advisor", "adviser"):  # "Ohio Advisor" describes a person, not a firm
                continue
            found.append(normalize_firm(" ".join(name)))
    return found


def extract_firms(text: str, stoplist: set[str], alias_map: dict[str, str] | None = None) -> list[str]:
    """Firm names from `text`: heuristic spans (minus stoplist) + watchlist aliases mapped to display names.

    alias_map: lowercase alias → display name (from the watchlist).
    """
    alias_map = alias_map or {}
    out: list[str] = []
    for name in firm_spans(text):
        low = name.lower()
        if low in stoplist:
            continue
        name = alias_map.get(low, name)
        if name not in out:
            out.append(name)
    return out
