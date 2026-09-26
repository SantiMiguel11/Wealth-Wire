"""Precision/recall of SEC firm matching on the labeled headline set (tests/fixtures/firm_headlines.yaml)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .firms import SecMatcher, normalize

LABELS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "firm_headlines.yaml"


def evaluate(matcher: SecMatcher, labels_path: Path = LABELS) -> dict:
    data = yaml.safe_load(labels_path.read_text(encoding="utf-8"))
    tp = fp = fn = 0
    rows = []
    for h in data["headlines"]:
        expected = [normalize(k) for k in h["firms"]]
        predicted = []
        for crd in matcher.firms_in(h["text"]):
            f = matcher.firms[crd]
            names = normalize(f"{f.get('business_name') or ''} {f.get('legal_name') or ''}").replace("| ", "")
            predicted.append((crd, matcher.display(crd), names))
        hit_keys = set()
        row_fp = []
        for crd, display, names in predicted:
            keys = [k for k in expected if k in names]
            if keys:
                hit_keys.update(keys)
            else:
                row_fp.append(display)
        tp += len(hit_keys)
        fp += len(row_fp)
        missed = [k for k in expected if k not in hit_keys]
        fn += len(missed)
        rows.append({"headline": h["text"], "expected": h["firms"], "found": [d for _, d, _ in predicted],
                     "false_positives": row_fp, "missed": missed})
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"headlines": len(rows), "expected_mentions": tp + fn, "true_positives": tp, "false_positives": fp,
            "false_negatives": fn, "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
            "sec_firms_in_dictionary": len(matcher.firms), "rows": rows}


def write_report(matcher: SecMatcher, out: Path, data_date: str | None) -> dict:
    report = evaluate(matcher)
    report["sec_data_date"] = data_date
    report["curated_unresolved"] = matcher.curated_unresolved
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report
