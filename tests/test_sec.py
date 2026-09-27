"""§4 SEC adviser data: discovery, parsing, monthly caching, and what it does to the public data."""
import io
import zipfile
from datetime import date, datetime, timedelta, timezone

import httpx
import openpyxl
import pytest

from fiduciarywire import db
from fiduciarywire.fetch import Fetcher
from fiduciarywire.sec import DEFAULT_PAGE, discover_files, maybe_update, parse_zip

from .conftest import NOW

PAGE_HTML = """<html><body>
<a href="/files/investment/data/other/ia090126.zip">September 2026</a>
<a href="/files/investment/data/other/era090126.zip">ERA September 2026</a>
<a href="/files/investment/data/other/ia080126.zip">August 2026</a>
<a href="https://www.sec.gov/files/other/report.pdf">pdf</a></body></html>"""


def test_discover_registered_adviser_files_newest_first():
    files = discover_files(PAGE_HTML, DEFAULT_PAGE)
    assert [f.url.rsplit("/", 1)[-1] for f in files] == ["ia090126.zip", "ia080126.zip"]
    assert files[0].data_date == date(2026, 9, 1)
    assert files[0].url.startswith("https://www.sec.gov/files/")


HEADER = ["SEC#", "Organization CRD#", "Legal Name", "Primary Business Name", "Main Office City", "Main Office State", "5F(2)(c)"]
ROWS = [["801-1", "123", "ACME WEALTH PARTNERS, LLC", "ACME WEALTH", "SEATTLE", "WA", "1,200,000,000"],
        ["802-9", "999", "EXEMPT FUND ADVISER LLC", "EXEMPT", "BOISE", "ID", ""],
        ["801-2", "456.0", "BETA ADVISORS INC.", "", "PORTLAND", "or", 850000000]]


def zip_csv(delim=","):
    body = "\n".join(delim.join(f'"{c}"' if "," in str(c) else str(c) for c in r) for r in [HEADER] + ROWS)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("IA_FIRM.csv", "﻿" + body)
    return buf.getvalue()


def zip_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Investment Adviser Information Report"])  # a title row above the header
    ws.append(HEADER)
    for r in ROWS:
        ws.append(r)
    x = io.BytesIO()
    wb.save(x)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ia090126.xlsx", x.getvalue())
    return buf.getvalue()


@pytest.mark.parametrize("content", [zip_csv(), zip_csv("|"), zip_xlsx()])
def test_parse_zip_keeps_registered_advisers(content):
    rows = {r["crd"]: r for r in parse_zip(content, date(2026, 9, 1))}
    assert set(rows) == {"123", "456"}                      # 802- exempt reporting adviser dropped
    assert rows["123"]["aum_usd"] == 1.2e9 and rows["123"]["state"] == "WA" and rows["123"]["business_name"] == "ACME WEALTH"
    assert rows["456"]["business_name"] == "BETA ADVISORS INC."  # falls back to the legal name
    assert rows["456"]["state"] == "OR" and rows["456"]["data_date"] == "2026-09-01"


class Site:
    def __init__(self, zip_bytes):
        self.requests = []
        self.zip = zip_bytes

    def __call__(self, req):
        self.requests.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if str(req.url) == DEFAULT_PAGE:
            return httpx.Response(200, text=PAGE_HTML)
        if req.url.path.endswith("ia090126.zip"):
            return httpx.Response(200, content=self.zip)
        return httpx.Response(404)


def test_monthly_update_and_cache(home):
    conn = db.connect()
    site = Site(zip_csv())
    f = Fetcher("FiduciaryWire/0.1 (test; me@example.com)", per_host_delay=0, transport=httpx.MockTransport(site))
    cfg = {"sec": {"allow_small_file": True}}
    t0 = datetime(2026, 9, 26, tzinfo=timezone.utc)
    st = maybe_update(conn, f, t0, cfg)
    assert st["status"] == "updated" and st["firms"] == 2 and st["data_date"] == "2026-09-01"
    assert any(u.endswith("ia090126.zip") for u in site.requests)
    assert all("FiduciaryWire/" in f.client.headers["user-agent"] for _ in [0])
    # within check_days: no network at all
    n = len(site.requests)
    assert maybe_update(conn, f, t0 + timedelta(days=5), cfg)["status"] == "cached" and len(site.requests) == n
    # after check_days: checks the page, sees the same file, doesn't download again
    st = maybe_update(conn, f, t0 + timedelta(days=30), cfg)
    assert st["status"] == "up to date" and sum(u.endswith(".zip") for u in site.requests) == 1


def test_update_failure_never_raises_and_keeps_data(home):
    conn = db.connect()
    f = Fetcher("UA", per_host_delay=0, transport=httpx.MockTransport(lambda r: httpx.Response(503)), sleep=lambda s: None)
    st = maybe_update(conn, f, NOW, {"sec": {}})
    assert st["status"] == "failed" and "503" in st["reason"]


def test_small_file_rejected_in_production(home):
    conn = db.connect()
    f = Fetcher("UA", per_host_delay=0, transport=httpx.MockTransport(Site(zip_csv())))
    st = maybe_update(conn, f, NOW, {"sec": {}})
    assert st["status"] == "failed" and "only 2 advisers" in st["reason"]


# ---- demo integration: verified firms, SEC AUM, regions, firm pages --------------------------------
@pytest.fixture
def files(ingested):
    from fiduciarywire.sitebuild import collect

    return collect(db.connect(), NOW)


def test_verified_firms_and_region(files):
    cl = {c["headline"]: c for c in files["clusters.json"]["clusters"]}
    deal = cl["Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"]
    assert [(f["name"], f["verified"], f["state"]) for f in deal["firms"]] == [
        ("Harborview Wealth Partners", True, "WA"), ("Summit Ridge Advisors", True, "CO")]
    assert deal["states"] == ["CO", "WA"]
    # not in the SEC data → regex fallback, unverified, no page
    bear = cl["Bear Mountain Capital makes minority investment in Willowbrook Wealth"]
    assert ("Bear Mountain Capital", False, None) in [(f["name"], f["verified"], f["slug"]) for f in bear["firms"]]
    pnw = [c for c in cl.values() if set(c["states"]) & {"WA", "OR", "ID"}]
    assert len(pnw) >= 4


def test_sec_aum_labeled_and_only_when_unambiguous(files):
    cl = {c["headline"]: c for c in files["clusters.json"]["clusters"]}
    # headline AUM wins over SEC AUM
    assert cl["Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"]["aum_source"] == "headline"
    # two firms named (Coldstream + Kestrel) → no SEC AUM (it would be ambiguous whose)
    c = cl["Coldstream hires former Kestrel Advisors CIO to lead investments"]
    assert c["aum_usd"] is None and c["aum_source"] is None
    sec = [c for c in cl.values() if c["aum_source"] == "sec"]
    assert all(c["sec_aum_as_of"] == "2026-09-01" and len(c["firms"]) >= 1 for c in sec)


def test_firm_pages(files):
    idx = files["firms/index.json"]
    slugs = {f["slug"]: f for f in idx["firms"]}
    hv = next(s for s in slugs if s.startswith("harborview-wealth-partners-"))
    page = files[f"firms/{hv}.json"]
    assert page["crd"] == slugs[hv]["crd"] and page["state"] == "WA" and page["city"] == "Seattle"
    assert page["iapd_url"] == f"https://adviserinfo.sec.gov/firm/summary/{page['crd']}"
    assert page["sec_aum_as_of"] == "2026-09-01" and page["sec_aum_usd"] == 9.8e9
    assert len(page["stories"]) == 2                          # the deal + the breakaway team
    assert [d["role"] for d in page["deals"]] == ["acquirer"]
    # only firms mentioned in at least one story get a page; unverified firms never do
    assert all(f["story_count"] >= 1 for f in idx["firms"])
    assert not any("bear-mountain" in s for s in slugs)
    assert all(f"firms/{s}.json" in files for s in slugs)


def test_trending_links_to_firm_pages(files):
    t = files["trending.json"]["firms"]
    hv = next(f for f in t if f["name"] == "Harborview Wealth Partners")
    assert hv["verified"] and hv["slug"] and f"firms/{hv['slug']}.json" in files
    assert all((f["slug"] is None) == (not f["verified"]) for f in t)


def test_meta_reports_sec_file(files):
    assert files["meta.json"]["sec"] == {"data_date": "2026-09-01", "firm_count": 22}
