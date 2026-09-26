"""Press-release wires (§5): keep only wealth-management news.

A wire item is kept when it mentions wealth-management terms AND (it names an SEC-registered adviser OR it's
an M&A / people-move story). Everything else (biotech trials, earnings, product recalls…) is dropped and
counted per source.
"""
from __future__ import annotations

import re

from .categorize import Categorizer
from .firms import SecMatcher

WEALTH_TERMS = re.compile(
    r"\b(?:RIAs?|registered investment advis[eo]rs?|investment advis[eo]rs?|investment advisory|wealth management|"
    r"wealth managers?|wealth advis[eo]rs?|financial advis[eo]rs?|advisory firms?|family offices?|private wealth|"
    r"financial planning firm|independent advis[eo]rs?|fiduciary advis[eo]rs?)\b",
    re.I,
)
KEEP_CATEGORIES = {"M&A", "People Moves"}


def keep_wire_item(title: str, description: str, sec: SecMatcher, categorizer: Categorizer) -> tuple[bool, str]:
    text = f"{title}\n{description}"
    if not WEALTH_TERMS.search(text):
        return False, "no wealth-management terms"
    if sec.firms_in(title) or sec.firms_in(description):
        return True, "names an SEC-registered adviser"
    cat = categorizer.categorize(title, description)
    if cat in KEEP_CATEGORIES:
        return True, cat
    return False, "wealth terms but no SEC firm and not M&A / people move"
