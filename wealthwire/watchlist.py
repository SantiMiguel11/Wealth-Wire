"""Watchlist: load/save watchlist.yaml and match firms in text."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

import yaml

from . import paths

MIN_ALIAS_LEN = 3
_LOCK = threading.Lock()


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


def _path():
    return paths.config_dir() / "watchlist.yaml"


def load_watchlist() -> list[Firm]:
    p = _path()
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    firms = []
    for raw in data.get("firms", []) or []:
        if isinstance(raw, str):
            firms.append(Firm(raw.strip()))
        elif raw and raw.get("name"):
            firms.append(Firm(str(raw["name"]).strip(), [str(a).strip() for a in raw.get("aliases") or [] if str(a).strip()]))
    return firms


HEADER = """# Firms to highlight and pin. Matching is case-insensitive on word boundaries.
# Aliases shorter than 3 characters are ignored (avoids matching acronyms like "GS").
# Also edited by the web UI (Watchlist panel), which rewrites this file.
"""


def save_watchlist(firms: list[Firm]) -> None:
    with _LOCK:
        body = yaml.safe_dump({"firms": [{"name": f.name, "aliases": f.aliases} for f in firms]}, sort_keys=False, allow_unicode=True)
        tmp = _path().with_suffix(".yaml.tmp")
        tmp.write_text(HEADER + body, encoding="utf-8")
        tmp.replace(_path())


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
