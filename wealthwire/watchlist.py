"""Watchlist matching for the server-side email alert (§8).

The site's watchlist lives only in each visitor's browser (localStorage). The optional email alert gets its
watchlist from the WATCHLIST_JSON secret via the environment — it is never read from or written to a file.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MIN_ALIAS_LEN = 3


@dataclass
class Firm:
    name: str
    aliases: list[str] = field(default_factory=list)

    def terms(self) -> list[str]:
        seen, out = set(), []
        for t in [self.name, *self.aliases]:
            t = " ".join(str(t).split())
            if len(t.replace(" ", "")) < MIN_ALIAS_LEN or t.lower() in seen:
                continue  # never match short acronyms like "GS"
            seen.add(t.lower())
            out.append(t)
        return out


def parse_watchlist(raw: str) -> list[Firm]:
    """Parse the WATCHLIST_JSON format (same as the site's export): {"firms":[{"name","aliases"}]} or a list."""
    data = json.loads(raw)
    items = data.get("firms", []) if isinstance(data, dict) else data
    firms = []
    for f in items or []:
        if isinstance(f, str):
            f = {"name": f}
        name = " ".join(str(f.get("name", "")).split())
        if name:
            firms.append(Firm(name, [" ".join(str(a).split()) for a in f.get("aliases") or [] if str(a).strip()]))
    return firms


class Matcher:
    """Case-insensitive, word-boundary matching. 'Goldman' matches "Goldman's" but not 'Goldmann'."""

    def __init__(self, firms: list[Firm]):
        self.firms = firms
        self._patterns: list[tuple[str, re.Pattern]] = []
        for f in firms:
            terms = f.terms()
            if not terms:
                continue
            alt = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in sorted(terms, key=len, reverse=True))
            self._patterns.append((f.name, re.compile(rf"(?<![\w&-])(?:{alt})(?![\w&]|-\w)", re.I)))

    def hits(self, *texts: str) -> list[str]:
        blob = "\n".join(t for t in texts if t)
        return [name for name, pat in self._patterns if pat.search(blob)]

    def alias_map(self) -> dict[str, str]:
        return {t.lower(): f.name for f in self.firms for t in f.terms()}
