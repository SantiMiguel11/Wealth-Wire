"""Print the layout of the latest SEC registered-adviser file and check the Census ZIP gazetteer (run on GitHub by
probe-feeds.yml with inspect_sec=true; the build sandbox can't reach either host). Public data only."""
from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fiduciarywire.config import load_config  # noqa: E402
from fiduciarywire.fetch import Fetcher  # noqa: E402
from fiduciarywire.sec import DEFAULT_PAGE, discover_files  # noqa: E402

GAZ = [
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip",
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip",
]


CRDS = {c.strip() for c in os.environ.get("SEC_CRDS", "").split(",") if c.strip()}


def main() -> int:
    cfg = load_config()
    f = Fetcher(cfg["user_agent"], per_host_delay=2.0, timeout=60, retries=1)
    page = f.get(DEFAULT_PAGE)
    files = discover_files(page.text, page.url)
    print("SEC files:", [(x.url.rsplit("/", 1)[-1], str(x.data_date)) for x in files[:3]])
    z = f.get(files[0].url)
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        for name in zf.namelist():
            print("MEMBER", name, zf.getinfo(name).file_size)
            low = name.lower()
            if low.endswith((".csv", ".txt")):
                raw = zf.read(name).decode("utf-8-sig", errors="replace")
                first = raw.split("\n", 1)[0]
                delim = max([",", "|", "\t"], key=first.count)
                rows = list(csv.reader(io.StringIO(raw), delimiter=delim))
            elif low.endswith(".xlsx"):
                import openpyxl

                wb = openpyxl.load_workbook(io.BytesIO(zf.read(name)), read_only=True, data_only=True)
                ws = wb.worksheets[0]
                rows = []
                for i, r in enumerate(ws.iter_rows(values_only=True)):
                    rows.append(["" if c is None else str(c) for c in r])
                    if i > 40 and not CRDS:
                        break
            else:
                continue
            for i, r in enumerate(rows[:6]):
                if len([c for c in r if c]) > 5:
                    hdr = r
                    print(f"HEADER row {i}: {len(hdr)} columns")
                    sample = rows[i + 1] if i + 1 < len(rows) else []
                    for j, h in enumerate(hdr):
                        print(f"  [{j}] {h!r} = {sample[j] if j < len(sample) else ''!r}")
                    break
            if CRDS:   # every address-like column for the given CRDs (to see why some rows lack a main office)
                ci = next(j for j, h in enumerate(hdr) if "crd" in h.lower())
                cols = [j for j, h in enumerate(hdr) if any(w in h.lower() for w in ("office", "address", "city", "state",
                                                                                         "postal", "country", "zip"))]
                for r in rows:
                    if ci < len(r) and r[ci].strip().split(".")[0] in CRDS:
                        print("CRD", r[ci], {hdr[j]: r[j] for j in cols if j < len(r) and r[j]})
    for url in GAZ:
        ok, why = f.robots.check(url)
        r = f.get(url) if ok else None
        print("GAZ", url, "robots:", ok, why, "HTTP", r.status if r else None, len(r.content) if r and r.ok else 0)
        if r and r.ok:
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                n = zf.namelist()[0]
                print("  ", n, zf.read(n).decode("utf-8", "replace").splitlines()[:3])
            break
    f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
