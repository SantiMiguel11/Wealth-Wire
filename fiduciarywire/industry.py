"""Industry tags for deals, from industries.yaml (multi-label; the first match in file order is primary)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import yaml


def _compile(patterns: list[str]) -> re.Pattern | None:
    """Case-insensitive phrases on word boundaries; `re:` prefix = raw regex."""
    parts = []
    for p in patterns or []:
        p = str(p)
        if p.startswith("re:"):
            parts.append(f"(?:{p[3:]})")
        else:
            parts.append(r"(?<![\w&])" + re.escape(p).replace(r"\ ", r"\s+") + r"(?![\w&])")
    return re.compile("|".join(parts), re.I) if parts else None


@dataclass(frozen=True)
class IndustryRule:
    name: str
    any: object
    unless: object


def load_rules() -> tuple[list[IndustryRule], str]:
    from . import paths

    return _load(str(paths.config_dir() / "industries.yaml"))


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[list[IndustryRule], str]:
    from pathlib import Path

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rules = [IndustryRule(r["name"], _compile(r.get("any", [])), _compile(r.get("unless", []))) for r in data.get("industries", [])]
    return rules, data.get("default", "Other")


def industry_names() -> list[str]:
    rules, default = load_rules()
    return [r.name for r in rules] + [default]


def classify(title: str, description: str = "", hint: str | None = None) -> list[str]:
    """Industries a deal belongs to, primary first. `hint` is the outlet's industry (single-industry outlets)."""
    rules, default = load_rules()
    found: set[str] = set()
    for text in (title or "", description or ""):
        for r in rules:
            if text and r.any and r.any.search(text) and not (r.unless and r.unless.search(text)):
                found.add(r.name)
    if hint:
        found.add(hint)
    ordered = [r.name for r in rules if r.name in found]
    return ordered or [default]


def merge(lists: list[list[str]]) -> list[str]:
    """Union over a cluster's articles, in file order; 'Other' only when nothing else matched."""
    rules, default = load_rules()
    found = {n for lst in lists for n in lst if n != default}
    return [r.name for r in rules if r.name in found] or [default]
