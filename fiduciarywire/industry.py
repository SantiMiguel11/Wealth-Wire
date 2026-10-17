"""Industry tags for deals, from industries.yaml (multi-label; the first match in file order is primary)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from .categorize import _compile


@dataclass(frozen=True)
class IndustryRule:
    name: str
    any: object
    unless: object


@lru_cache(maxsize=1)
def load_rules() -> tuple[list[IndustryRule], str]:
    from . import paths

    data = yaml.safe_load((paths.config_dir() / "industries.yaml").read_text(encoding="utf-8")) or {}
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
