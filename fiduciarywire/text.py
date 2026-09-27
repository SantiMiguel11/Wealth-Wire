"""Text helpers: HTML stripping and truncation."""
from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

MAX_DESCRIPTION = 300
_WS = re.compile(r"\s+")
_WP_BOILERPLATE = re.compile(r"\s*The post .{1,300}? appeared first on .{1,120}?\.?\s*$", re.S)
_READ_MORE = re.compile(r"\s*(?:\[(?:…|\.\.\.|&#8230;)\]|Read more\W*|Continue reading\W*|\(more…\))\s*$", re.I)


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    if "<" in value:
        value = BeautifulSoup(value, "html.parser").get_text(" ")
    value = html.unescape(value)
    value = _WS.sub(" ", value).strip()
    value = _WP_BOILERPLATE.sub("", value)
    value = _READ_MORE.sub("", value)
    return value.strip()


def truncate(value: str, limit: int = MAX_DESCRIPTION) -> str:
    """Truncate at a word boundary so the result (including the ellipsis) is ≤ limit chars."""
    value = value.strip()
    if len(value) <= limit:
        return value
    cut = value[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-–—") + "…"


def clean_description(value: str | None) -> str:
    return truncate(strip_html(value))


def clean_title(value: str | None) -> str:
    return _WS.sub(" ", html.unescape(strip_html(value))).strip()


def strip_source_suffix(title: str, source: str) -> str:
    """'Headline | ThinkAdvisor' → 'Headline' (only when the suffix names the source)."""
    names = {source, source.replace(" ", ""), source.split()[0]} if source else set()
    for name in sorted(names, key=len, reverse=True):
        title = re.sub(rf"\s+[|\-–—:]\s+{re.escape(name)}(?:\.com)?\s*$", "", title, flags=re.I)
    return title.strip()
