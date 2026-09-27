"""Optional watchlist email after each refresh (§8).

Runs only when all three secrets are set in the environment: WATCHLIST_JSON, RESEND_API_KEY, ALERT_EMAIL.
Otherwise it logs a notice and exits cleanly. It sends one email listing the stories first fetched in this
refresh that match the watchlist, and sends nothing when there are no matches.

The watchlist is read only from the environment. It is never written to a file, and it is never printed,
since workflow logs are visible to anyone who can see the repo. Logs show counts only.
"""
from __future__ import annotations

import html
import os
import sqlite3
from collections import OrderedDict
from typing import Callable, Mapping

from . import db
from .config import load_config
from .firms import pretty_name
from .watchlist import Matcher, parse_watchlist

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "Fiduciary Wire <onboarding@resend.dev>"
MAX_STORIES = 40
REQUIRED = ("WATCHLIST_JSON", "RESEND_API_KEY", "ALERT_EMAIL")


def new_matches(conn: sqlite3.Connection, matcher: Matcher) -> list[dict]:
    """Clusters with at least one story first fetched in the latest ingest that matches the watchlist."""
    since = db.get_meta(conn, "last_ingest")
    if not since:
        return []
    exclude = set((load_config().get("site") or {}).get("exclude_sources") or [])
    sec = {r["crd"]: pretty_name(r["business_name"] or r["legal_name"]) for r in conn.execute(
        "SELECT crd, business_name, legal_name FROM sec_firms")}
    firms: dict[int, list[str]] = {}
    for r in conn.execute("SELECT item_id, firm, crd, verified FROM item_firms"):
        firms.setdefault(r["item_id"], []).append(sec.get(r["crd"], r["firm"]) if r["verified"] else r["firm"])
    heads: dict[int, str] = {}  # the site's headline for a cluster: its earliest story
    for r in conn.execute("SELECT cluster_id, title, source FROM items WHERE cluster_id IS NOT NULL ORDER BY published_at, id"):
        if r["source"] not in exclude:
            heads.setdefault(r["cluster_id"], r["title"])
    out: OrderedDict[int, dict] = OrderedDict()
    for r in conn.execute("SELECT id, title, url, source, published_at, cluster_id FROM items "
                          "WHERE fetched_at >= ? AND cluster_id IS NOT NULL ORDER BY published_at DESC, id DESC", (since,)):
        if r["source"] in exclude:
            continue
        hits = matcher.hits(r["title"], *firms.get(r["id"], []))
        if not hits:
            continue
        entry = out.setdefault(r["cluster_id"], {"headline": heads.get(r["cluster_id"], r["title"]), "published_at": r["published_at"],
                                                 "firms": [], "sources": []})
        entry["firms"] = list(dict.fromkeys(entry["firms"] + hits))
        if all(s["name"] != r["source"] for s in entry["sources"]):
            entry["sources"].append({"name": r["source"], "url": r["url"]})
    return list(out.values())


def compose(matches: list[dict], site_url: str | None = None) -> tuple[str, str, str]:
    n = len(matches)
    subject = f"Fiduciary Wire: {n} new {'story' if n == 1 else 'stories'} on your watchlist"
    shown = matches[:MAX_STORIES]
    text, rows = [], []
    for m in shown:
        links = " · ".join(f"{s['name']}: {s['url']}" for s in m["sources"])
        text.append(f"- {m['headline']}\n  Watchlist: {', '.join(m['firms'])}\n  {links}")
        rows.append(
            f"<li style='margin:0 0 14px'><strong>{html.escape(m['headline'])}</strong><br>"
            f"<span style='color:#555'>Watchlist: {html.escape(', '.join(m['firms']))}</span><br>"
            + " · ".join(f"<a href='{html.escape(s['url'], quote=True)}'>{html.escape(s['name'])}</a>" for s in m["sources"])
            + "</li>")
    more = f"\n…and {n - len(shown)} more on the site." if n > len(shown) else ""
    footer = f"\n\nOpen Fiduciary Wire: {site_url}" if site_url else ""
    body_text = "New stories matching your watchlist:\n\n" + "\n".join(text) + more + footer
    body_html = ("<p>New stories matching your watchlist:</p><ul style='padding-left:18px'>" + "".join(rows) + "</ul>"
                 + (f"<p>…and {n - len(shown)} more on the site.</p>" if more else "")
                 + (f"<p><a href='{html.escape(site_url, quote=True)}'>Open Fiduciary Wire</a></p>" if site_url else ""))
    return subject, body_text, body_html


def send_resend(api_key: str, payload: dict) -> tuple[bool, str]:
    import httpx

    try:
        r = httpx.post(RESEND_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=15)
    except httpx.HTTPError as exc:
        return False, type(exc).__name__
    return (r.status_code < 300), f"HTTP {r.status_code}"


def run_alert(conn: sqlite3.Connection, env: Mapping[str, str] | None = None,
              send: Callable[[str, dict], tuple[bool, str]] | None = None) -> dict:
    """Never raises; the refresh must not fail because of the email."""
    env = os.environ if env is None else env
    missing = [k for k in REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        print(f"::notice::Watchlist email skipped: {', '.join(missing)} not set (optional; see MANUAL-STEPS.md)")
        return {"status": "skipped", "missing": missing}
    try:
        firms = parse_watchlist(env["WATCHLIST_JSON"])
    except (ValueError, TypeError, AttributeError):
        print("::warning::Watchlist email skipped: WATCHLIST_JSON is not valid watchlist JSON")
        return {"status": "invalid watchlist"}
    if not firms:
        print("::notice::Watchlist email skipped: WATCHLIST_JSON has no firms")
        return {"status": "empty watchlist"}
    try:
        matches = new_matches(conn, Matcher(firms))
        if not matches:
            print(f"Watchlist email: no new matching stories ({len(firms)} watchlist firms checked)")
            return {"status": "no matches", "firms": len(firms)}
        subject, text, body_html = compose(matches, (env.get("SITE_URL") or "").strip() or None)
        payload = {"from": (env.get("ALERT_FROM") or "").strip() or DEFAULT_FROM,
                   "to": [a.strip() for a in env["ALERT_EMAIL"].split(",") if a.strip()],
                   "subject": subject, "text": text, "html": body_html}
        ok, why = (send or send_resend)(env["RESEND_API_KEY"].strip(), payload)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"::warning::Watchlist email failed: {type(exc).__name__}")
        return {"status": "error"}
    if not ok:
        print(f"::warning::Watchlist email not sent: Resend returned {why}")
        return {"status": "send failed", "reason": why, "stories": len(matches)}
    print(f"Watchlist email sent: {len(matches)} matching {'story' if len(matches) == 1 else 'stories'}")
    return {"status": "sent", "stories": len(matches)}

