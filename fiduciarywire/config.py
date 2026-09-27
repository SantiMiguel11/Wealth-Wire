"""Load the editable YAML configuration files."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import paths

DEFAULTS: dict[str, Any] = {
    "contact_email": "me@example.com",
    "user_agent": "FiduciaryWire/0.1 (personal news reader; {contact_email})",
    "timezone": "America/Los_Angeles",
    "http": {"per_host_delay_seconds": 2.0, "timeout_seconds": 15, "retries": 1, "backoff_seconds": 2.0},
    "cluster": {"window_hours": 72, "threshold": 70},
    "server": {"host": "127.0.0.1", "port": 8000, "reingest_interval_hours": 2},
    "digest": {"fallback_hours": 24, "top_n": 10},
}

PLACEHOLDER_EMAIL = "me@example.com"


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict[str, Any]:
    cfg = _merge(DEFAULTS, _read_yaml(paths.config_dir() / "config.yaml") or {})
    cfg["user_agent"] = str(cfg["user_agent"]).format(contact_email=cfg["contact_email"])
    return cfg


@dataclass
class Source:
    name: str
    homepage: str = ""
    feed_url: str = ""
    listing_url: str = ""
    gated: bool = False
    enabled: bool = True
    kind: str = "feed"          # feed | wire (press-release wire, filtered) | google_news
    query: str = ""             # google_news: the search query, e.g. "site:thinkadvisor.com"
    max_age_days: int = 0       # 0 = no limit; wires/google_news skip items older than this
    feed_urls: list = field(default_factory=list)  # wire: several keyword-scoped feeds, merged and deduped


def load_sources() -> list[Source]:
    data = _read_yaml(paths.config_dir() / "sources.yaml") or {}
    out = []
    for raw in data.get("sources", []):
        out.append(
            Source(
                name=str(raw["name"]).strip(),
                homepage=(raw.get("homepage") or "").strip(),
                feed_url=(raw.get("feed_url") or "").strip(),
                listing_url=(raw.get("listing_url") or "").strip(),
                gated=bool(raw.get("gated", False)),
                enabled=bool(raw.get("enabled", True)),
                kind=str(raw.get("kind") or "feed").strip(),
                query=(raw.get("query") or "").strip(),
                max_age_days=int(raw.get("max_age_days") or 0),
                feed_urls=[str(u).strip() for u in raw.get("feed_urls") or [] if str(u).strip()],
            )
        )
    return out


@dataclass
class CategoryRules:
    categories: list[str]
    rules: list[dict] = field(default_factory=list)


def load_categories() -> CategoryRules:
    data = _read_yaml(paths.config_dir() / "categories.yaml") or {}
    return CategoryRules(categories=list(data.get("categories", [])), rules=list(data.get("rules", [])))


def load_stoplist() -> set[str]:
    data = _read_yaml(paths.config_dir() / "firm_stoplist.yaml") or {}
    return {str(s).strip().lower() for s in data.get("stoplist", []) if str(s).strip()}
