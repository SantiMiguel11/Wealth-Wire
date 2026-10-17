"""Recompute all derived data from stored items: deals only, industries, firms, AUM, clusters, deal rows."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import industry
from .cluster import ClusterItem, cluster
from .config import load_config, load_sources, load_stoplist
from .dates import from_iso, utcnow
from .deals import DealSignal, classify
from .extract import extract_aum, extract_firms, money_spans
from .firms import SecMatcher, normalize, tokenize
from .mna import deal_for_cluster

# Industries where a dollar figure next to a firm is assets under management, and SEC adviser AUM means something.
AUM_INDUSTRIES = {"Wealth Management & RIAs", "Private Equity & Asset Management"}
WEALTH = "Wealth Management & RIAs"
SAME_DEAL_DAYS = 7


def _load_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, url, source, published_at, fetched_at, description FROM items ORDER BY published_at, id"
    ).fetchall()
    return [dict(r) for r in rows]


def group_items(items: list[dict], cfg: dict) -> list[list[dict]]:
    by_id = {it["id"]: it for it in items}
    # every item is a deal: one category for all, so outlets that tag different industries still cluster
    citems = [
        ClusterItem(it["id"], it["source"], it["published_at"], it["title"], firms=set(it["title_firms"]), category="M&A")
        for it in items
    ]
    groups = cluster(citems, threshold=float(cfg["cluster"]["threshold"]), window_hours=float(cfg["cluster"]["window_hours"]))
    return merge_same_deal([[by_id[c.id] for c in g] for g in groups])


_KEY_STOP = {"the", "a", "an", "us", "u.s.", "group", "partners", "capital", "holdings", "inc", "corp", "co", "company", "llc"}


def _tokens(name: str) -> list[str]:
    toks = [re.sub(r"(?:'s|’s)$", "", t.strip(".,()").lower()) for t in (name or "").split()]
    return [t for t in toks if t and t not in _KEY_STOP]


def _figures(title: str) -> set[float]:
    return {round(v, -7) for _, _, v in money_spans(title) if v >= 1e7}


def merge_same_deal(groups: list[list[dict]]) -> list[list[dict]]:
    """Join clusters that report the same deal in different words ("Proofpoint to acquire Varonis Systems in $6.3B
    all-cash deal" / "Thoma Bravo’s Proofpoint inks $6.3bn take-private of data security firm Varonis"):
    same target name (first word) and a shared acquirer word or an unnamed acquirer; or, when the target isn't
    named, the same acquirer and the same dollar figure ("Concurrent Buys $5.4 Billion Firm in Virginia")."""
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sigs = []
    for gi, g in enumerate(groups):
        for it in g:
            d: DealSignal | None = it.get("deal")
            if d:
                sigs.append((gi, from_iso(it["published_at"]), _tokens(d.target), set(_tokens(d.acquirer)), _figures(it["title"])))
    for i in range(len(sigs)):
        gi, ti, tgt_i, acq_i, fig_i = sigs[i]
        for j in range(i + 1, len(sigs)):
            gj, tj, tgt_j, acq_j, fig_j = sigs[j]
            if find(gi) == find(gj) or abs(ti - tj) > timedelta(days=SAME_DEAL_DAYS):
                continue
            same_target = bool(tgt_i and tgt_j and tgt_i[0] == tgt_j[0] and (acq_i & acq_j or not acq_i or not acq_j))
            same_buyer_figure = bool((not tgt_i or not tgt_j) and acq_i & acq_j and fig_i & fig_j)
            if same_target or same_buyer_figure:
                parent[find(gj)] = find(gi)
    merged: dict[int, list[dict]] = {}
    for gi, g in enumerate(groups):
        merged.setdefault(find(gi), []).extend(g)
    return list(merged.values())


def firms_in_text(text: str, stoplist: set[str], sec: SecMatcher, body: bool = False) -> list[dict]:
    """SEC-verified firms first; regex-extracted names only for firms the SEC data doesn't cover (unverified).
    body=True (teasers): single-word generated aliases are ignored, because teasers name people far more often
    than headlines do ("…named Jane Frazier president" is not Frazier Healthcare Partners)."""
    out: list[dict] = []
    matches = sec.match(text)
    if body:
        matches = [m for m in matches if " " in m.alias or m.alias in sec.curated]
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
    for f in firms_in_text(it["description"], stoplist, sec, body=True):
        if (f["crd"] or f["name"].lower()) not in keys:
            keys.add(f["crd"] or f["name"].lower())
            firms.append(dict(f, in_title=False))
    it["firms"] = firms
    # clustering compares firm identities: CRD when verified, else the lowercased name
    it["title_firms"] = [f["crd"] or f["name"].lower() for f in title]
    it["title_crds"] = [f["crd"] for f in title if f["crd"]]
    it["subject_crd"] = subject_crd(it["title"], sec)
    # AUM only means something for advisers and asset managers; elsewhere a figure is a price or revenue
    aum = None
    if AUM_INDUSTRIES & set(it.get("industries") or []):
        aum = extract_aum(it["title"]) or extract_aum(it["description"])
        if aum and it.get("deal") and it["deal"].value_usd and round(aum, -5) == round(it["deal"].value_usd, -5):
            aum = None  # the figure is the deal's price
    it["aum_usd"] = aum


def write_clusters(conn: sqlite3.Connection, groups: list[list[dict]], sec: SecMatcher | None = None) -> None:
    conn.execute("DELETE FROM clusters")
    for group in groups:
        group = sorted(group, key=lambda it: (it["published_at"], it["id"]))
        head = group[0]
        cid = min(it["id"] for it in group)
        industries = industry.merge([it.get("industries") or [] for it in group])
        category = industries[0]
        aums = [it.get("aum_usd") for it in group if it.get("aum_usd")]
        aum = head.get("aum_usd") or (max(set(aums), key=aums.count) if aums else None)
        # SEC-reported AUM, only when no headline states one and the headlines agree on one verified subject firm
        # ("Coldstream hires former Kestrel Advisors CIO" is about Coldstream → Kestrel's AUM must not appear)
        sec_aum = sec_crd = None
        subjects = {it.get("subject_crd") for it in group if it.get("subject_crd")}
        if not aum and sec and len(subjects) == 1 and AUM_INDUSTRIES & set(industries):
            sec_crd = subjects.pop()
            sec_aum = sec.firms[sec_crd].get("aum_usd") or None
            if not sec_aum:
                sec_crd = None
        conn.execute(
            "INSERT INTO clusters(id, headline_item_id, headline, url, category, first_seen, first_published, last_published, "
            "outlet_count, item_count, aum_usd, sec_aum_usd, sec_aum_crd, industries) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid, head["id"], head["title"], head["url"], category,
                min(it["fetched_at"] for it in group),
                head["published_at"], max(it["published_at"] for it in group),
                len({it["source"] for it in group}), len(group), aum, sec_aum, sec_crd, json.dumps(industries),
            ),
        )
        conn.executemany("UPDATE items SET cluster_id=? WHERE id=?", [(cid, it["id"]) for it in group])


STAGE_RANK = {"rumored": 0, "bid": 1, "announced": 2, "completed": 3, "terminated": 4}


def best_deal(titles: list[str]) -> DealSignal | None:
    """The clearest parse across a cluster's headlines (press releases first): both parties named beats one;
    the most advanced stage any headline reports wins (a deal reported "completed" later is completed);
    the first stated price is kept."""
    parsed = [d for d in (classify(t) for t in titles) if d]
    if not parsed:
        return None
    best = max(parsed, key=lambda d: (bool(d.acquirer) + bool(d.target), -parsed.index(d)))
    stage = max((d.stage for d in parsed), key=lambda st: STAGE_RANK.get(st, 2))
    value = next((d.value_usd for d in parsed if d.value_usd), None)
    return DealSignal(best.acquirer, best.target, best.deal_type, stage, value, best.seller, list(best.notes))


def write_deals(conn: sqlite3.Connection, wire_sources: set[str] | None = None) -> int:
    """One deal row per cluster (every cluster is a deal). A press release in the cluster raises confidence."""
    wire_sources = wire_sources or set()
    conn.execute("DELETE FROM mna_deals")
    rows = conn.execute("SELECT id, first_published, industries FROM clusters").fetchall()
    for r in rows:
        members = conn.execute("SELECT title, source FROM items WHERE cluster_id=? ORDER BY published_at, id", (r["id"],)).fetchall()
        titles = [m["title"] for m in members if m["source"] in wire_sources] + [m["title"] for m in members if m["source"] not in wire_sources]
        press_release = any(m["source"] in wire_sources for m in members)
        d = best_deal(titles)
        if d is None:
            continue
        industries = json.loads(r["industries"] or "[]")
        aum = None
        if WEALTH in industries:  # RIA headlines state the target's AUM ("buys $1B Louisiana RIA")
            legacy = deal_for_cluster(titles)
            if legacy.target_aum_usd and (not d.target or not legacy.target or legacy.target.lower() in d.target.lower()
                                          or d.target.lower() in legacy.target.lower()):
                aum = legacy.target_aum_usd
        note = d.notes[0] if d.notes else ""
        confidence = "high" if d.acquirer and d.target else "low"
        if press_release and d.acquirer and d.target and note:
            note = f"raised by a matching press release (was: {note})"
        conn.execute(
            "INSERT INTO mna_deals(cluster_id, acquirer, target, target_aum_usd, deal_type, deal_date, confidence, note, press_release, "
            "stage, value_usd, industries) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], d.acquirer, d.target, aum, d.deal_type, r["first_published"], confidence, note, int(press_release),
             d.stage, d.value_usd, r["industries"] or "[]"),
        )
    return len(rows)


def purge_non_deals(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    """Deals only: items stored before the switch (or by an older filter) that aren't deals are deleted."""
    keep, drop = [], []
    for it in items:
        it["deal"] = classify(it["title"])
        (keep if it["deal"] else drop).append(it)
    if drop:
        ids = [(it["id"],) for it in drop]
        conn.executemany("DELETE FROM item_firms WHERE item_id=?", ids)
        conn.executemany("DELETE FROM items WHERE id=?", ids)
    return keep


def recompute(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Recompute all derived data from the stored items."""
    cfg = load_config()
    now = now or utcnow()
    items = purge_non_deals(conn, _load_items(conn))
    stoplist = load_stoplist()
    sec = SecMatcher.from_db(conn)
    hints = {s.name: s.industry for s in load_sources() if s.industry}
    for it in items:
        it["industries"] = industry.classify(it["title"], it["description"], hints.get(it["source"]))
        it["category"] = it["industries"][0]
        extract_item(it, stoplist, sec)
    conn.executemany("UPDATE items SET category=?, aum_usd=? WHERE id=?", [(it["category"], it["aum_usd"], it["id"]) for it in items])
    conn.execute("DELETE FROM item_firms")
    conn.executemany(
        "INSERT OR IGNORE INTO item_firms(item_id, firm, crd, verified, in_title) VALUES (?, ?, ?, ?, ?)",
        [(it["id"], f["name"], f["crd"], int(f["verified"]), int(f["in_title"])) for it in items for f in it["firms"]],
    )
    groups = group_items(items, cfg)
    write_clusters(conn, groups, sec)
    deals = write_deals(conn, {s.name for s in load_sources() if s.kind == "wire"})
    conn.commit()
    local_date = now.astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()
    return {"items": len(items), "clusters": len(groups), "deals": deals, "local_date": local_date}
