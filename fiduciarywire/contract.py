"""The public data contract: which JSON Schema (schemas/) governs which file under site/data/."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import paths

# (regex on the path relative to site/data, schema file)
RULES = [
    (r"meta\.json", "meta.schema.json"),
    (r"clusters\.json", "clusters.schema.json"),
    (r"stories\.json", "stories.schema.json"),
    (r"digest\.json", "digest.schema.json"),
    (r"digests/index\.json", "digests-index.schema.json"),
    (r"digests/\d{4}-\d{2}-\d{2}\.json", "digest.schema.json"),
    (r"weekly/index\.json", "weekly-index.schema.json"),
    (r"weekly/\d{4}-W\d{2}\.json", "weekly.schema.json"),
    (r"mna\.json", "mna.schema.json"),
    (r"firms/index\.json", "firms-index.schema.json"),
    (r"firms/[a-z0-9-]+\.json", "firm.schema.json"),
    (r"trending\.json", "trending.schema.json"),
    (r"sources\.json", "sources.schema.json"),
]


def schema_for(rel: str) -> str | None:
    for pattern, name in RULES:
        if re.fullmatch(pattern, rel):
            return name
    return None


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    return json.loads((paths.SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def validate_data_dir(data_dir: Path) -> list[str]:
    """Validate every JSON file under site/data. Returns a list of problems (empty = valid)."""
    import jsonschema

    problems = []
    for p in sorted(data_dir.rglob("*.json")):
        rel = p.relative_to(data_dir).as_posix()
        name = schema_for(rel)
        if not name:
            problems.append(f"{rel}: no schema covers this file")
            continue
        validator = jsonschema.Draft202012Validator(load_schema(name))
        for err in sorted(validator.iter_errors(json.loads(p.read_text(encoding="utf-8"))), key=lambda e: list(e.path))[:5]:
            loc = "/".join(str(x) for x in err.path)
            problems.append(f"{rel} [{loc}]: {err.message[:200]}")
    return problems
