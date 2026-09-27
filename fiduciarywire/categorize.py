"""One primary category per item via ordered keyword rules from categories.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import CategoryRules, load_categories


def _compile(patterns: list[str]) -> re.Pattern | None:
    parts = []
    for p in patterns or []:
        p = str(p)
        if p.startswith("re:"):
            parts.append(f"(?:{p[3:]})")
        else:
            parts.append(r"(?<![\w&])" + re.escape(p).replace(r"\ ", r"\s+") + r"(?![\w&])")
    return re.compile("|".join(parts), re.I) if parts else None


@dataclass
class Rule:
    category: str
    any: re.Pattern
    unless: re.Pattern | None
    title_only: bool


class Categorizer:
    def __init__(self, rules: CategoryRules | None = None):
        rules = rules or load_categories()
        self.default = "Other"
        self.rules = [
            Rule(r["category"], _compile(r.get("any", [])), _compile(r.get("unless", [])), bool(r.get("title_only", False)))
            for r in rules.rules
            if r.get("any")
        ]

    def categorize(self, title: str, description: str = "") -> str:
        # Title decides first; the description is only consulted when no rule matches the title.
        for text, is_title in ((title or "", True), (description or "", False)):
            if not text:
                continue
            for rule in self.rules:
                if rule.title_only and not is_title:
                    continue
                if rule.any.search(text) and not (rule.unless and rule.unless.search(text)):
                    return rule.category
        return self.default
