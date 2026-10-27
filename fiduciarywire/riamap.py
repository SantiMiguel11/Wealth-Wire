"""Public data for the RIA map (DATA-CONTRACT.md → riamap.json, riamap/details-NN.json).

riamap.json holds one compact row per SEC-registered adviser placed on the map; the details a click shows are
split into 32 shards by CRD so the page only loads what it needs. Everything comes from the SEC's public Form ADV
extract; firms are placed at their ZIP centroid (never a street address).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from .dates import from_iso, to_iso
from .firms import pretty_name
from .geo import HEIGHT, WIDTH, albers_usa, fan_out, zip_points

SCHEMA_VERSION = 1
SHARDS = 32
FOCUS = ["Wealth management", "Funds & alternatives", "Institutional", "Other"]
CLIENT_TYPE = {
    "a": "Individuals", "b": "High-net-worth individuals", "c": "Banks and thrifts", "d": "Investment companies",
    "e": "Business development companies", "f": "Pooled investment vehicles", "g": "Pension and profit-sharing plans",
    "h": "Charities", "i": "State and municipal entities", "j": "Other investment advisers", "k": "Insurance companies",
    "l": "Sovereign wealth funds", "m": "Corporations", "n": "Other clients",
}
SERVICE = {  # Item 5G
    1: "Financial planning", 2: "Portfolio management for individuals", 3: "Portfolio management for investment companies",
    4: "Portfolio management for pooled vehicles", 5: "Portfolio management for institutions", 6: "Pension consulting",
    7: "Selecting other advisers", 8: "Newsletters and periodicals", 9: "Security ratings or pricing", 10: "Market timing",
    11: "Educational seminars", 12: "Other services",
}
COMPENSATION = {1: "Percentage of AUM", 2: "Hourly charges", 3: "Subscription fees", 4: "Fixed fees", 5: "Commissions",
                6: "Performance-based fees", 7: "Other"}
OTHER_BUSINESS = {  # Item 6A
    1: "Broker-dealer", 2: "Registered representative of a broker-dealer", 3: "Commodity pool operator or CTA",
    4: "Futures commission merchant", 5: "Real estate broker or agent", 6: "Insurance broker or agent", 7: "Bank",
    8: "Trust company", 9: "Municipal advisor", 10: "Security-based swap dealer", 11: "Major swap participant",
    12: "Accounting firm", 13: "Law firm", 14: "Other financial product sales",
}
# flags in the compact row
F_PAGE, F_DEAL, F_DISCLOSURE, F_WRAP = 1, 2, 4, 8
FIELDS = ["crd", "name", "x", "y", "aum_usd", "city", "state", "focus", "services", "flags"]
INDIVIDUAL, FUNDS = set("ab"), set("def")


def focus_of(client_aum: dict[str, float] | None) -> int:
    """0 wealth management (most client AUM from individuals), 1 funds & alternatives, 2 institutional, 3 other."""
    if not client_aum or sum(client_aum.values()) <= 0:
        return 3
    ind = sum(v for k, v in client_aum.items() if k in INDIVIDUAL)
    fun = sum(v for k, v in client_aum.items() if k in FUNDS)
    ins = sum(client_aum.values()) - ind - fun
    return max(((ind, 0), (fun, 1), (ins, 2)), key=lambda t: (t[0], -t[1]))[1]


def _website(v: str | None) -> str | None:
    v = (v or "").strip().lower()
    if not v or " " in v or "." not in v:
        return None
    return v if v.startswith(("http://", "https://")) else "https://" + v


def build(conn: sqlite3.Connection, now: datetime, page_slugs: dict[str, str], deals: list[dict]) -> dict[str, dict]:
    """→ {"riamap.json": …, "riamap/details-00.json": …}. `page_slugs`: CRD → firm page slug (firms in the news);
    `deals`: mna.json rows (for a firm's recent deals)."""
    exact, zip3 = zip_points(conn)
    rows = [dict(r) for r in conn.execute("SELECT * FROM sec_firms")]
    sec_date = rows[0]["data_date"] if rows else None
    since = now - timedelta(days=14)
    deals_by_crd: dict[str, list[dict]] = {}
    for d in deals:
        for role in ("acquirer", "target"):
            crd = (d.get(role) or {}).get("crd")
            if crd:
                deals_by_crd.setdefault(crd, []).append({"date": d["date"], "headline": d["headline"], "role": role,
                                                          "url": (d.get("sources") or [{}])[0].get("url")})
    placed, unmapped = [], 0
    for r in rows:
        country = (r.get("country") or "United States").strip().lower()
        pt = None
        if country in ("united states", "usa", "us"):
            ll = exact.get(r.get("zip") or "") or zip3.get((r.get("zip") or "")[:3])
            pt = albers_usa(ll[1], ll[0]) if ll else None
        if pt is None:
            unmapped += 1
            continue
        placed.append((r, pt))
    spots = fan_out([(r["crd"], x, y) for r, (x, y) in placed])
    compact, shards = [], {i: {} for i in range(SHARDS)}
    total_aum = 0.0
    for r, _ in placed:
        prof = json.loads(r.get("profile") or "{}")
        crd = r["crd"]
        x, y = spots[crd]
        aum = r.get("aum_usd") or 0
        total_aum += aum
        recent = [d for d in deals_by_crd.get(crd, []) if from_iso(d["date"]) >= since]
        flags = (F_PAGE if crd in page_slugs else 0) | (F_DEAL if recent else 0) | \
                (F_DISCLOSURE if prof.get("disclosures") else 0) | (F_WRAP if prof.get("wrap") else 0)
        services = sum(1 << (i - 1) for i in prof.get("services", []))
        name = pretty_name(r["business_name"] or r["legal_name"])
        city = (r.get("city") or "").title() or None
        compact.append([int(crd), name, round(x, 1), round(y, 1), round(aum) if aum else 0, city, r.get("state"),
                        focus_of(prof.get("client_aum")), services, flags])
        mix = prof.get("client_aum") or {}
        mix_total = sum(mix.values())
        accounts = prof.get("accounts")
        detail = {
            "legal_name": pretty_name(r["legal_name"]),
            "zip": r.get("zip"),
            "website": _website(prof.get("website")),
            "registered": prof.get("registered"), "adv_date": prof.get("adv_date"), "org_type": prof.get("org_type"),
            "employees": prof.get("employees"), "advisory_staff": prof.get("advisory_staff"), "offices": prof.get("offices"),
            "clients": prof.get("clients"), "accounts": accounts,
            "avg_account_usd": round(aum / accounts) if aum and accounts else None,
            "discretionary_pct": round(100 * prof["aum_discretionary"] / aum) if aum and prof.get("aum_discretionary") else None,
            "client_mix": [[CLIENT_TYPE[k], round(100 * v / mix_total)] for k, v in sorted(mix.items(), key=lambda kv: -kv[1])
                           if mix_total and round(100 * v / mix_total) >= 1][:6],
            "services": [SERVICE[i] for i in prof.get("services", []) if i in SERVICE],
            "compensation": [COMPENSATION[i] for i in prof.get("compensation", []) if i in COMPENSATION],
            "other_business": [OTHER_BUSINESS[i] for i in prof.get("other_business", []) if i in OTHER_BUSINESS],
            "private_funds": prof.get("private_funds") or 0,
            "disclosures": bool(prof.get("disclosures")),
            "iapd_url": f"https://adviserinfo.sec.gov/firm/summary/{crd}",
            "slug": page_slugs.get(crd),
            "deals": sorted(deals_by_crd.get(crd, []), key=lambda d: d["date"], reverse=True)[:3],
        }
        shards[int(crd) % SHARDS][crd] = detail
    compact.sort(key=lambda f: -f[4])   # largest first: drawn first, revealed first, ties to the biggest firm on hover
    files: dict[str, dict] = {
        "riamap.json": {
            "schema_version": SCHEMA_VERSION, "generated_at": to_iso(now), "sec_data_date": sec_date,
            "width": WIDTH, "height": HEIGHT, "shards": SHARDS,
            "counts": {"advisers": len(rows), "mapped": len(compact), "unmapped": unmapped},
            "total_aum_usd": round(total_aum),
            "focus": FOCUS, "services": [SERVICE[i] for i in range(1, 13)],
            "fields": FIELDS, "firms": compact,
        }
    }
    for i, firms in shards.items():
        files[f"riamap/details-{i:02d}.json"] = {"schema_version": SCHEMA_VERSION, "firms": firms}
    return files
