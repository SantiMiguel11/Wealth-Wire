"""Build tests/fixtures/sec_firms_real_subset.csv: the slice of the real SEC adviser file needed to reproduce
firm matching on the labeled headline sets offline (regression tests).

A registrant is included if any alias it generates occurs in any labeled headline, or if it is the target of a
curated alias. Alias resolution only depends on the registrants that generate an alias, so matching those
headlines against this slice gives exactly the same result as against the full file; the script verifies that
and fails otherwise.

    python scripts/build_eval_dictionary.py path/to/wealthwire.db     # e.g. state/wealthwire.db from `live`
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wealthwire.config import load_stoplist  # noqa: E402
from wealthwire.firms import SecMatcher, aliases_for, load_curated, normalize  # noqa: E402

SETS = [ROOT / "tests/fixtures/firm_headlines.yaml", ROOT / "tests/fixtures/firm_headlines_heldout.yaml"]
OUT = ROOT / "tests/fixtures/sec_firms_real_subset.csv"
COLS = ["crd", "sec_number", "legal_name", "business_name", "city", "state", "aum_usd", "data_date"]


def main(db: str) -> int:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM sec_firms")]
    texts = [h["text"] for p in SETS for h in yaml.safe_load(p.read_text(encoding="utf-8"))["headlines"]]
    padded = [" " + " ".join(t for t in normalize(x).split()) + " " for x in texts]
    curated = load_curated()
    targets = {" ".join(t for t in normalize(v).split() if t != "|") for v in curated.values()}
    keep = []
    for r in rows:
        names = {r.get("business_name") or "", r.get("legal_name") or ""} - {""}
        als = {a for n in names for a in aliases_for(n)}
        norm = {" ".join(t for t in normalize(n).split() if t != "|") for n in names}
        if norm & targets or any(f" {a} " in p for a in als for p in padded):
            keep.append(r)
    full = SecMatcher(rows, curated, load_stoplist())
    sub = SecMatcher(keep, curated, load_stoplist())
    diffs = [t for t in texts if full.firms_in(t) != sub.firms_in(t)]
    if diffs:
        print("subset does not reproduce the full file on:", *diffs[:5], sep="\n  ")
        return 1
    keep.sort(key=lambda r: int(r["crd"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Slice of the SEC adviser file dated {rows[0]['data_date']} ({len(keep)} of {len(rows)} advisers). "
                 "Built by scripts/build_eval_dictionary.py; public SEC data.\n")
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(keep)
    print(f"{len(keep)} advisers → {OUT.relative_to(ROOT)}; identical matches on {len(texts)} headlines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
