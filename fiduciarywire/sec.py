"""SEC Investment Adviser Information Reports (monthly Form ADV extracts) → the `sec_firms` table (§4).

Source page: https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers
Each month the SEC posts a zip containing one spreadsheet of SEC-registered advisers (files named like
`ia090126.zip`, MMDDYY) plus separate exempt-reporting-adviser files. We:

- check the page at most once every `sec.check_days` days (default 25), and only download when the newest
  registered-adviser file is newer than the one already loaded;
- respect SEC fair access: descriptive User-Agent with a contact email, ≥2s between requests, robots.txt;
- keep: CRD, SEC number, legal name, primary business name, main office city/state, regulatory AUM
  (Item 5F(2)(c)), and the file's date.

Header names are matched loosely (case/spacing/punctuation-insensitive), so small format changes don't break
parsing. CSV/TXT and XLSX members are supported.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from . import db
from .dates import from_iso, to_iso

DEFAULT_PAGE = "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers"
_ZIP_HREF = re.compile(r"""href\s*=\s*["']([^"']+\.zip)["']""", re.I)


@dataclass
class SecFile:
    url: str
    data_date: date


def _file_date(name: str) -> date | None:
    digits = re.findall(r"(\d{6,8})", name)
    for d in reversed(digits):
        try:
            if len(d) == 6:   # MMDDYY
                return date(2000 + int(d[4:6]), int(d[0:2]), int(d[2:4]))
            if len(d) == 8 and d.startswith(("19", "20")):   # YYYYMMDD
                return date(int(d[0:4]), int(d[4:6]), int(d[6:8]))
            if len(d) == 8:   # MMDDYYYY
                return date(int(d[4:8]), int(d[0:2]), int(d[2:4]))
        except ValueError:
            continue
    return None


def discover_files(html: str, base_url: str) -> list[SecFile]:
    """Registered-adviser zip files linked from the SEC page, newest first (exempt-reporting files skipped)."""
    out: dict[str, SecFile] = {}
    for href in _ZIP_HREF.findall(html):
        name = href.rsplit("/", 1)[-1].lower()
        if "era" in name or "exempt" in name or not name.startswith("ia"):
            continue
        d = _file_date(name)
        if d:
            url = urljoin(base_url, href)
            out[url] = SecFile(url, d)
    return sorted(out.values(), key=lambda f: f.data_date, reverse=True)


# ------------------------------------------------------------------------------------------------
# parsing
# ------------------------------------------------------------------------------------------------
def _key(h: str) -> str:
    return re.sub(r"[^a-z0-9#]", "", (h or "").lower())


FIELDS = {
    "crd": lambda k: k in ("organizationcrd#", "organizationcrd", "crd#", "crdnumber", "firmcrd#", "crd") or k.endswith("crd#"),
    "sec_number": lambda k: k in ("sec#", "secnumber", "secfile#", "secregistration#", "secfilenumber"),
    "legal_name": lambda k: k in ("legalname", "fulllegalname", "1alegalname"),
    "business_name": lambda k: k in ("primarybusinessname", "businessname", "1bprimarybusinessname", "1b1name"),
    "city": lambda k: k in ("mainofficecity", "1fmainofficecity", "city"),
    "state": lambda k: k in ("mainofficestate", "1fmainofficestate", "state"),
    "aum": lambda k: k in ("5f2c", "5f2ctotal", "totalraum", "regulatoryassetsundermanagement"),
}


def map_headers(headers: list[str]) -> dict[str, int]:
    keys = [_key(h) for h in headers]
    out: dict[str, int] = {}
    for field, test in FIELDS.items():
        for i, k in enumerate(keys):
            if test(k):
                out[field] = i
                break
    return out


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.]", "", str(v))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _rows_from_table(rows: list[list], data_date: date) -> list[dict]:
    header_idx = None
    for i, r in enumerate(rows[:20]):
        m = map_headers([str(c or "") for c in r])
        if "crd" in m and ("legal_name" in m or "business_name" in m):
            header_idx, cols = i, m
            break
    if header_idx is None:
        return []
    out = []
    for r in rows[header_idx + 1:]:
        get = lambda f: (r[cols[f]] if f in cols and cols[f] < len(r) else None)  # noqa: E731
        crd = str(get("crd") or "").strip()
        if crd.endswith(".0"):
            crd = crd[:-2]
        if not crd.isdigit():
            continue
        sec_number = str(get("sec_number") or "").strip() or None
        if sec_number and not sec_number.startswith("801-"):
            continue  # 802- = exempt reporting advisers; keep SEC-registered advisers only
        legal = str(get("legal_name") or "").strip()
        business = str(get("business_name") or "").strip() or legal
        if not (legal or business):
            continue
        out.append({"crd": crd, "sec_number": sec_number, "legal_name": legal or business, "business_name": business,
                    "city": (str(get("city") or "").strip() or None), "state": (str(get("state") or "").strip().upper()[:2] or None),
                    "aum_usd": _num(get("aum")), "data_date": data_date.isoformat()})
    return out


def parse_zip(content: bytes, data_date: date) -> list[dict]:
    rows: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            low = name.lower()
            if low.endswith((".csv", ".txt")):
                raw = zf.read(name).decode("utf-8-sig", errors="replace")
                first = raw.split("\n", 1)[0]
                delim = max([",", "|", "\t"], key=first.count)  # header line decides; quoted values don't matter
                rows += _rows_from_table(list(csv.reader(io.StringIO(raw), delimiter=delim)), data_date)
            elif low.endswith(".xlsx"):
                import openpyxl

                wb = openpyxl.load_workbook(io.BytesIO(zf.read(name)), read_only=True, data_only=True)
                for ws in wb.worksheets:
                    rows += _rows_from_table([list(r) for r in ws.iter_rows(values_only=True)], data_date)
    # one row per CRD (a firm can appear on several sheets)
    return list({r["crd"]: r for r in rows}.values())


def store(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.execute("DELETE FROM sec_firms")
    conn.executemany(
        "INSERT OR REPLACE INTO sec_firms(crd, sec_number, legal_name, business_name, city, state, aum_usd, data_date) "
        "VALUES (:crd, :sec_number, :legal_name, :business_name, :city, :state, :aum_usd, :data_date)", rows)
    conn.commit()


# ------------------------------------------------------------------------------------------------
# monthly update
# ------------------------------------------------------------------------------------------------
def maybe_update(conn: sqlite3.Connection, fetcher, now: datetime, cfg: dict, force: bool = False) -> dict:
    """Check for a newer SEC file (≤ once per check_days) and load it. Never raises: returns a status dict."""
    sec_cfg = cfg.get("sec") or {}
    if not sec_cfg.get("enabled", True):
        return {"status": "disabled"}
    page = sec_cfg.get("page_url") or DEFAULT_PAGE
    have = db.get_meta(conn, "sec_data_date")
    checked = db.get_meta(conn, "sec_checked_at")
    count = conn.execute("SELECT COUNT(*) FROM sec_firms").fetchone()[0]
    if not force and count and checked and now - from_iso(checked) < timedelta(days=int(sec_cfg.get("check_days", 25))):
        return {"status": "cached", "data_date": have, "firms": count}
    try:
        allowed, why = fetcher.robots.check(page)
        if not allowed:
            return {"status": "failed", "reason": f"{page}: {why}", "data_date": have, "firms": count}
        res = fetcher.get(page)
        if not res.ok:
            return {"status": "failed", "reason": f"{page}: {res.describe_failure()}", "data_date": have, "firms": count}
        files = discover_files(res.text, res.url)
        if not files:
            return {"status": "failed", "reason": "no registered-adviser zip linked from the SEC page", "data_date": have, "firms": count}
        latest = files[0]
        db.set_meta(conn, "sec_checked_at", to_iso(now))
        conn.commit()
        if have and latest.data_date.isoformat() <= have and count:
            return {"status": "up to date", "data_date": have, "firms": count, "url": latest.url}
        allowed, why = fetcher.robots.check(latest.url)
        if not allowed:
            return {"status": "failed", "reason": f"{latest.url}: {why}", "data_date": have, "firms": count}
        dl = fetcher.get(latest.url)
        if not dl.ok:
            return {"status": "failed", "reason": f"{latest.url}: {dl.describe_failure()}", "data_date": have, "firms": count}
        rows = parse_zip(dl.content, latest.data_date)
        if len(rows) < 100 and not sec_cfg.get("allow_small_file"):
            return {"status": "failed", "reason": f"{latest.url}: parsed only {len(rows)} advisers; keeping the previous data",
                    "data_date": have, "firms": count}
        store(conn, rows)
        db.set_meta(conn, "sec_data_date", latest.data_date.isoformat())
        db.set_meta(conn, "sec_file_url", latest.url)
        conn.commit()
        return {"status": "updated", "data_date": latest.data_date.isoformat(), "firms": len(rows), "url": latest.url}
    except Exception as exc:  # never let SEC data break a refresh
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}", "data_date": have, "firms": count}
