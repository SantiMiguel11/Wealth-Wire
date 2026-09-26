"""Recompute all derived data from stored items (categories, firms, AUM, clusters, M&A)."""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .categorize import Categorizer
from .cluster import ClusterItem, cluster
from .config import load_config, load_stoplist
from .dates import utcnow
from .extract import extract_aum, extract_firms
from .firms import SecMatcher, normalize, tokenize
from .mna import deal_for_cluster


def _load_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, url, source, published_at, fetched_at, description FROM items ORDER BY published_at, id"
    ).fetchall()
    return [dict(r) for r in rows]


def group_items(items: list[dict], cfg: dict) -> list[list[dict]]:
    by_id = {it["id"]: it for it in items}
    citems = [
        ClusterItem(it["id"], it["source"], it["published_at"], it["title"], firms=set(it["title_firms"]), category=it["category"])
        for it in items
    ]
    groups = cluster(citems, threshold=float(cfg["cluster"]["threshold"]), window_hours=float(cfg["cluster"]["window_hours"]))
    return [[by_id[c.id] for c in g] for g in groups]


def firms_in_text(text: str, stoplist: set[str], sec: SecMatcher) -> list[dict]:
    """SEC-verified firms first; regex-extracted names only for firms the SEC data doesn't cover (unverified)."""
    out: list[dict] = []
    matches = sec.match(text)
    verified_aliases = [m.alias for m in matches]
    for crd in dict.fromkeys(m.crd for m in matches):
        out.append({"name": sec.display(crd), "crd": crd, "verified": True})
    covered = [normalize(f["name"]) for f in out] + verified_aliases
    for name in extract_firms(text, stoplist):
        n = normalize(name)
        if any(a in n or n in a for a in covered):
            continue  # the regex span is (part of) a firm we already verified
        out.append({"name": name, "crd": None, "verified": False})
    return out


def subject_crd(title: str, sec: SecMatcher) -> str | None:
    """The verified firm the headline is about: its name opens the headline, after an optional label
    ("People Moves: Mercer Advisors hires …" → Mercer Advisors; "Coldstream hires Kestrel's CIO" → none)."""
    toks = [n for _, n in tokenize(title)]
    start = 0
    for i, t in enumerate(toks[:6]):
        if t == "|":
            start = i + 1
    for m in sec.match(title):
        if m.start_token == start:
            return m.crd
    return None


def extract_item(it: dict, stoplist: set[str], sec: SecMatcher) -> None:
    """Firms from title and description (separately, so spans never cross fields)."""
    title = firms_in_text(it["title"], stoplist, sec)
    firms = [dict(f, in_title=True) for f in title]
    keys = {f["crd"] or f["name"].lower() for f in firms}
    for f in firms_in_text(it["description"], stoplist, sec):
        if (f["crd"] or f["name"].lower()) not in keys:
            keys.add(f["crd"] or f["name"].lower())
            firms.append(dict(f, in_title=False))
    it["firms"] = firms
    # clustering compares firm identities: CRD when verified, else the lowercased name
    it["title_firms"] = [f["crd"] or f["name"].lower() for f in title]
    it["title_crds"] = [f["crd"] for f in title if f["crd"]]
    it["subject_crd"] = subject_crd(it["title"], sec)
    it["aum_usd"] = extract_aum(it["title"]) or extract_aum(it["description"])


def write_clusters(conn: sqlite3.Connection, groups: list[list[dict]], sec: SecMatcher | None = None) -> None:
    conn.execute("DELETE FROM clusters")
    for group in groups:
        group = sorted(group, key=lambda it: (it["published_at"], it["id"]))
        head = group[0]
        cid = min(it["id"] for it in group)
        cats = [it.get("category") for it in group]
        category = head.get("category") or "Other"
        if category == "Other":
            non_other = [c for c in cats if c and c != "Other"]
            if non_other:
                category = Counter(non_other).most_common(1)[0][0]
        aums = [it.get("aum_usd") for it in group if it.get("aum_usd")]
        aum = head.get("aum_usd") or (Counter(aums).most_common(1)[0][0] if aums else None)
        # SEC-reported AUM, only when no headline states one and the headlines agree on one verified subject firm
        # ("Coldstream hires former Kestrel Advisors CIO" is about Coldstream → Kestrel's AUM must not appear)
        sec_aum = sec_crd = None
        subjects = {it.get("subject_crd") for it in group if it.get("subject_crd")}
        if not aum and sec and len(subjects) == 1:
            sec_crd = subjects.pop()
            sec_aum = sec.firms[sec_crd].get("aum_usd") or None
            if not sec_aum:
                sec_crd = None
        conn.execute(
            "INSERT INTO clusters(id, headline_item_id, headline, url, category, first_seen, first_published, last_published, "
            "outlet_count, item_count, aum_usd, sec_aum_usd, sec_aum_crd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid, head["id"], head["title"], head["url"], category,
                min(it["fetched_at"] for it in group),
                head["published_at"], max(it["published_at"] for it in group),
                len({it["source"] for it in group}), len(group), aum, sec_aum, sec_crd,
            ),
        )
        conn.executemany("UPDATE items SET cluster_id=? WHERE id=?", [(cid, it["id"]) for it in group])


def write_deals(conn: sqlite3.Connection, wire_sources: set[str] | None = None) -> int:
    """One M&A row per M&A-category cluster. A press release in the cluster raises confidence (§5)."""
    wire_sources = wire_sources or set()
    conn.execute("DELETE FROM mna_deals")
    rows = conn.execute("SELECT id, first_published FROM clusters WHERE category = 'M&A'").fetchall()
    for r in rows:
        members = conn.execute("SELECT title, source FROM items WHERE cluster_id=? ORDER BY published_at, id", (r["id"],)).fetchall()
        # press-release headlines are the most explicit statement of a deal: parse them first
        titles = [m["title"] for m in members if m["source"] in wire_sources] + [m["title"] for m in members if m["source"] not in wire_sources]
        press_release = any(m["source"] in wire_sources for m in members)
        d = deal_for_cluster(titles)
        note = d.note
        if press_release and d.acquirer and d.target:
            if d.confidence == "low":
                note = "raised by a matching press release" + (f" (was: {note})" if note else "")
            d.confidence = "high"
        conn.execute(
            "INSERT INTO mna_deals(cluster_id, acquirer, target, target_aum_usd, deal_type, deal_date, confidence, note, press_release) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (r["id"], d.acquirer, d.target, d.target_aum_usd, d.deal_type, r["first_published"], d.confidence, note, int(press_release)),
        )
    return len(rows)


def recompute(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Recompute all derived data from the stored items."""
    cfg = load_config()
    now = now or utcnow()
    items = _load_items(conn)
    categorizer = Categorizer()
    stoplist = load_stoplist()
    sec = SecMatcher.from_db(conn)
    for it in items:
        it["category"] = categorizer.categorize(it["title"], it["description"])
        extract_item(it, stoplist, sec)
    conn.executemany("UPDATE items SET category=?, aum_usd=? WHERE id=?", [(it["category"], it["aum_usd"], it["id"]) for it in items])
    conn.execute("DELETE FROM item_firms")
    conn.executemany(
        "INSERT OR IGNORE INTO item_firms(item_id, firm, crd, verified, in_title) VALUES (?, ?, ?, ?, ?)",
        [(it["id"], f["name"], f["crd"], int(f["verified"]), int(f["in_title"])) for it in items for f in it["firms"]],
    )
    groups = group_items(items, cfg)
    write_clusters(conn, groups, sec)
    from .config import load_sources

    deals = write_deals(conn, {s.name for s in load_sources() if s.kind == "wire"})
    conn.commit()
    local_date = now.astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()
    return {"items": len(items), "clusters": len(groups), "deals": deals, "local_date": local_date}
