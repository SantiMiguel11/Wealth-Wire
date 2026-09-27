"""Print cluster scores for the fixture pairs (tests/fixtures/cluster_pairs.yaml) to pick a threshold."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fiduciarywire.cluster import ClusterItem, score  # noqa: E402
from fiduciarywire.config import load_stoplist  # noqa: E402
from fiduciarywire.categorize import Categorizer  # noqa: E402
from fiduciarywire.extract import extract_firms  # noqa: E402

pairs = yaml.safe_load((Path(__file__).resolve().parent.parent / "tests/fixtures/cluster_pairs.yaml").read_text())
stop = load_stoplist()
cat = Categorizer()


def item(i, t):
    return ClusterItem(i, f"s{i}", "2026-09-25T00:00:00Z", t, firms=set(extract_firms(t, stop)), category=cat.categorize(t))


for kind in ("match", "no_match", "known_limitations"):
    print(f"--- {kind}")
    for a, b in pairs[kind]:
        print(f"{score(item(1, a), item(2, b)):6.1f}  {a[:55]:57} | {b[:55]}")
