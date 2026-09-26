"""Build the public static site: site/data/*.json (the data contract, see DATA-CONTRACT.md) + frontend/.

Only public fields are ever written: headlines, links, outlets, dates, categories, firms, AUM, M&A rows,
digest text. Publisher teasers (items.description) and the database never leave the private state.
`privacy_check` enforces that on the finished output and fails the build if it is violated.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from . import db, paths
from .config import load_config, load_sources
from .dates import from_iso, to_iso, utcnow
from .firms import pretty_name
from .urls import clean_link
from .window import rank_clusters, top_window

SCHEMA_VERSION = 1
FOOTER_NOTE = "Summaries written with Claude from outlet headlines."

VERCEL_JSON = {
    "buildCommand": "echo static site",
    "installCommand": "echo no install",
    "framework": None,
    "outputDirectory": "site",
    "rewrites": [{"source": "/firm/:slug", "destination": "/index.html"}],
    "headers": [
        {"source": "/(.*)", "headers": [{"key": "X-Robots-Tag", "value": "noindex, nofollow"}]},
        {"source": "/data/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
    ],
}
LIVE_README = """# live branch (generated — do not edit)

Rebuilt and force-pushed as a single orphan commit by `.github/workflows/refresh-site.yml` on `main`.

- `site/` is the static website Vercel serves (`vercel.json` → outputDirectory).
- `state/` carries the private database and archives to the next refresh. It is never deployed.
"""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "firm"


def _title(city: str | None) -> str | None:
    return city.title() if city and city.isupper() else (city or None)


def firm_slug(name: str, crd: str) -> str:
    return f"{slugify(name)}-{crd}"


# ------------------------------------------------------------------------------------------------
# collectors
# ------------------------------------------------------------------------------------------------
class Snapshot:
    """Everything the public files are built from, loaded once from the DB with exclusions applied."""

    def __init__(self, conn: sqlite3.Connection, cfg: dict, now: datetime):
        self.conn, self.cfg, self.now = conn, cfg, now
        site_cfg = cfg.get("site") or {}
        self.exclude = set(site_cfg.get("exclude_sources") or [])
        self.sources_cfg = {s.name: s for s in load_sources()}
        self.sec = {r["crd"]: dict(r) for r in conn.execute("SELECT * FROM sec_firms")}
        self.sec_date = db.get_meta(conn, "sec_data_date")
        self._load()

    def _firm_obj(self, name: str, crd: str | None, verified: bool) -> dict:
        if verified and crd and crd in self.sec:
            f = self.sec[crd]
            display = pretty_name(f["business_name"] or f["legal_name"])
            return {"name": display, "slug": firm_slug(display, crd), "crd": crd, "verified": True,
                    "city": _title(f["city"]), "state": f["state"] or None}
        return {"name": name, "slug": None, "crd": None, "verified": False, "city": None, "state": None}

    def _load(self) -> None:
        conn = self.conn
        items_by_cluster: dict[int, list[dict]] = defaultdict(list)
        for r in conn.execute(
            "SELECT id, title, url, source, published_at, published_estimated, fetched_at, category, cluster_id, aum_usd "
            "FROM items WHERE cluster_id IS NOT NULL ORDER BY published_at, id"
        ):
            if r["source"] in self.exclude:
                continue
            it = dict(r)
            it["url"] = clean_link(it["url"])
            items_by_cluster[it["cluster_id"]].append(it)
        firms_by_item: dict[int, list[dict]] = defaultdict(list)
        for r in conn.execute("SELECT item_id, firm, crd, verified, in_title FROM item_firms ORDER BY rowid"):
            firms_by_item[r["item_id"]].append(dict(r))

        self.clusters: list[dict] = []
        cluster_rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM clusters")}
        for cid, items in items_by_cluster.items():
            row = cluster_rows.get(cid)
            if not row:
                continue
            head = items[0]
            sources, seen = [], set()
            for it in items:
                if it["source"] not in seen:
                    seen.add(it["source"])
                    kind = getattr(self.sources_cfg.get(it["source"]), "kind", "feed")
                    sources.append({"name": it["source"], "url": it["url"], "published_at": it["published_at"], "kind": kind})
            firms, fseen = [], set()
            for it in items:
                for f in firms_by_item.get(it["id"], []):
                    obj = self._firm_obj(f["firm"], f["crd"], bool(f["verified"]))
                    key = obj["crd"] or obj["name"].lower()
                    if key not in fseen:
                        fseen.add(key)
                        firms.append(obj)
            aum = row["aum_usd"]
            aum_source = "headline" if aum else None
            sec_aum = row.get("sec_aum_usd")
            if not aum and sec_aum:
                aum, aum_source = sec_aum, "sec"
            self.clusters.append({
                "id": cid,
                "headline": head["title"],
                "url": head["url"],
                "category": row["category"] or "Other",
                "first_published": head["published_at"],
                "last_published": max(it["published_at"] for it in items),
                "first_seen": min(it["fetched_at"] for it in items),
                "outlet_count": len(sources),
                "sources": sources,
                "firms": firms,
                "states": sorted({f["state"] for f in firms if f["state"]}),
                "aum_usd": aum,
                "aum_source": aum_source,
                "sec_aum_as_of": self.sec_date if aum_source == "sec" else None,
                "press_release": any(s["kind"] == "wire" for s in sources),
                "item_ids": [it["id"] for it in items],
            })
            for it in items:
                it["firm_slugs"] = [self._firm_obj(f["firm"], f["crd"], bool(f["verified"]))["slug"]
                                    for f in firms_by_item.get(it["id"], [])]
        self.clusters.sort(key=lambda c: (c["last_published"], c["id"]), reverse=True)
        self.by_id = {c["id"]: c for c in self.clusters}
        self.items = [it for items in items_by_cluster.values() for it in items if it["cluster_id"] in self.by_id]

    # -- files ------------------------------------------------------------------------------------
    def clusters_json(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(self.now),
                "clusters": [{k: v for k, v in c.items() if k != "item_ids"} for c in self.clusters]}

    def stories_json(self) -> dict:
        out = []
        for it in sorted(self.items, key=lambda i: (i["published_at"], i["id"]), reverse=True):
            c = self.by_id[it["cluster_id"]]
            out.append({
                "id": it["id"], "cluster_id": it["cluster_id"], "title": it["title"], "url": it["url"],
                "outlet": it["source"], "published_at": it["published_at"],
                "date_estimated": bool(it["published_estimated"]), "category": c["category"],
                "firm_slugs": [s for s in it.get("firm_slugs", []) if s],
            })
        return {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(self.now), "stories": out}

    def mna_json(self) -> dict:
        rows = []
        for r in self.conn.execute("SELECT * FROM mna_deals ORDER BY deal_date DESC, cluster_id DESC"):
            c = self.by_id.get(r["cluster_id"])
            if not c:
                continue
            rows.append({
                "cluster_id": r["cluster_id"], "date": r["deal_date"], "headline": c["headline"],
                "acquirer": self._party(r["acquirer"], c), "target": self._party(r["target"], c),
                "target_aum_usd": r["target_aum_usd"],
                "target_aum_source": "headline" if r["target_aum_usd"] else None,
                "deal_type": r["deal_type"] or None, "confidence": r["confidence"], "note": r["note"] or "",
                "press_release": bool(r["press_release"]) or c["press_release"],
                "sources": [{"name": s["name"], "url": s["url"]} for s in c["sources"]],
            })
            party = rows[-1]["target"]
            if not rows[-1]["target_aum_usd"] and party.get("crd") and self.sec.get(party["crd"], {}).get("aum_usd"):
                rows[-1]["target_aum_usd"] = self.sec[party["crd"]]["aum_usd"]
                rows[-1]["target_aum_source"] = "sec"
        return {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(self.now), "sec_aum_as_of": self.sec_date, "deals": rows}

    def _party(self, name: str, cluster: dict) -> dict:
        """Link an M&A party to a verified firm in the same cluster when the names agree."""
        if not name:
            return {"name": None, "slug": None, "crd": None}
        low = name.lower()
        for f in cluster["firms"]:
            if f["verified"] and (low in f["name"].lower() or f["name"].lower() in low):
                return {"name": name, "slug": f["slug"], "crd": f["crd"]}
        return {"name": name, "slug": None, "crd": None}

    def firms(self) -> tuple[dict, dict[str, dict]]:
        by_slug: dict[str, dict] = {}
        for c in self.clusters:
            for f in c["firms"]:
                if not f["verified"]:
                    continue
                entry = by_slug.setdefault(f["slug"], {**f, "cluster_ids": []})
                entry["cluster_ids"].append(c["id"])
        mna = self.mna_json()["deals"]
        pages, index = {}, []
        for slug, f in sorted(by_slug.items()):
            sec = self.sec[f["crd"]]
            stories = [self.by_id[cid] for cid in f["cluster_ids"]]
            deals = [d for d in mna if slug in (d["acquirer"]["slug"], d["target"]["slug"])]
            page = {
                "schema_version": SCHEMA_VERSION, "slug": slug, "name": f["name"], "legal_name": pretty_name(sec["legal_name"]),
                "crd": f["crd"], "sec_number": sec["sec_number"], "city": _title(sec["city"]), "state": sec["state"],
                "sec_aum_usd": sec["aum_usd"], "sec_aum_as_of": sec["data_date"],
                "iapd_url": f"https://adviserinfo.sec.gov/firm/summary/{f['crd']}",
                "stories": [{"cluster_id": c["id"], "headline": c["headline"], "url": c["url"], "category": c["category"],
                             "last_published": c["last_published"], "outlet_count": c["outlet_count"],
                             "sources": [{"name": s["name"], "url": s["url"]} for s in c["sources"]]} for c in stories],
                "deals": [{**d, "role": "acquirer" if d["acquirer"]["slug"] == slug else "target"} for d in deals],
            }
            pages[slug] = page
            index.append({"slug": slug, "name": f["name"], "legal_name": pretty_name(sec["legal_name"]), "crd": f["crd"],
                          "city": _title(sec["city"]), "state": sec["state"], "sec_aum_usd": sec["aum_usd"],
                          "story_count": len(stories)})
        return {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(self.now), "sec_data_date": self.sec_date,
                "firms": index}, pages

    def trending_json(self, days: int = 7, limit: int = 15) -> dict:
        since = to_iso(self.now - timedelta(days=days))
        counts: Counter = Counter()
        info: dict[str, dict] = {}
        for c in self.clusters:
            if c["last_published"] < since:
                continue
            for f in {(f["crd"] or f["name"].lower()): f for f in c["firms"]}.values():
                key = f["crd"] or f["name"].lower()
                counts[key] += 1
                info[key] = f
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], info[kv[0]]["name"].lower()))[:limit]
        return {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(self.now), "days": days,
                "firms": [{"name": info[k]["name"], "slug": info[k]["slug"], "crd": info[k]["crd"],
                           "verified": info[k]["verified"], "stories": n} for k, n in ranked]}

    def sources_json(self) -> dict:
        status = {r["name"]: dict(r) for r in self.conn.execute("SELECT * FROM source_status")}
        out = []
        for s in self.sources_cfg.values():
            if s.name in self.exclude:
                continue
            st = status.get(s.name, {})
            out.append({"name": s.name, "kind": s.kind, "homepage": s.homepage or None, "enabled": s.enabled,
                        "ok": bool(st.get("ok")), "method": st.get("method", "not run"),
                        "url_used": st.get("url_used") or None, "items_last_run": st.get("items_last_run", 0),
                        "new_last_run": st.get("new_last_run", 0), "dropped_last_run": st.get("dropped_last_run", 0),
                        "reason": st.get("reason", ""), "last_run_at": st.get("last_run_at") or None})
        return {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(self.now), "sources": out}


# ------------------------------------------------------------------------------------------------
# digest + archive files (written by aidigest/weekly into the data dir; copied here)
# ------------------------------------------------------------------------------------------------
def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def window_ranked(snap: Snapshot, window_start: datetime) -> list[dict]:
    """Top Stories candidates: first seen since the window start, still recent, ranked by outlets then recency."""
    return rank_clusters([c for c in snap.clusters if from_iso(c["first_seen"]) > window_start
                          and from_iso(c["last_published"]) >= window_start - timedelta(hours=48)])


def public_item(c: dict) -> dict:
    """A cluster as a digest item (summary fields empty until Claude's validated text fills them)."""
    return {"cluster_id": c["id"], "headline": c["headline"], "url": c["url"], "category": c["category"],
            "outlet_count": c["outlet_count"], "sources": [{"name": s["name"], "url": s["url"]} for s in c["sources"]],
            "firms": [{"name": f["name"], "slug": f["slug"]} for f in c["firms"]],
            "aum_usd": c["aum_usd"], "aum_source": c["aum_source"], "summary": None, "why_it_matters": None}


def digest_files(snap: Snapshot, window_start: datetime) -> dict[str, dict]:
    """digest.json (latest good AI digest for today, else the plain ranked list) + archive."""
    files: dict[str, dict] = {}
    ddir = paths.digests_dir()
    archived = sorted(ddir.glob("????-??-??.json")) if ddir.exists() else []
    index = []
    for p in archived:
        d = _read_json(p)
        if d:
            files[f"digests/{p.name}"] = d
            index.append({"date": d["date"], "generated_at": d["generated_at"], "item_count": len(d["items"]),
                          "path": f"data/digests/{p.name}"})
    index.sort(key=lambda e: e["date"], reverse=True)
    weekly = []
    wdir = paths.weekly_dir()
    for p in sorted(wdir.glob("*.json")) if wdir.exists() else []:
        w = _read_json(p)
        if w:
            files[f"weekly/{p.name}"] = w
            weekly.append({"week": w["week"], "start": w["start"], "end": w["end"], "deal_count": len(w["deals"]),
                           "path": f"data/weekly/{p.name}"})
    weekly.sort(key=lambda e: e["week"], reverse=True)
    files["digests/index.json"] = {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(snap.now),
                                   "digests": index, "weekly": weekly}
    files["weekly/index.json"] = {"schema_version": SCHEMA_VERSION, "generated_at": to_iso(snap.now), "weekly": weekly}

    top = [public_item(c) for c in window_ranked(snap, window_start)[:25]]
    latest = _read_json(ddir / "latest.json") if ddir.exists() else None
    last_good = index[0] if index else None
    local_today = snap.now.astimezone(_tz(snap.cfg)).date().isoformat()
    if latest and latest.get("date") == local_today and latest.get("ai"):
        digest = dict(latest)
        # keep the AI items first, then any other ranked stories not covered
        covered = {i["cluster_id"] for i in digest["items"]}
        digest["more"] = [t for t in top if t["cluster_id"] not in covered][:10]
    else:
        digest = {"schema_version": SCHEMA_VERSION, "date": local_today, "generated_at": to_iso(snap.now), "ai": False,
                  "opener": None, "items": top[:15], "more": []}
    digest["window_start"] = to_iso(window_start)
    digest["last_good_digest"] = {"date": last_good["date"], "path": last_good["path"]} if last_good else None
    digest["footer_note"] = FOOTER_NOTE
    files["digest.json"] = digest
    return files


def _tz(cfg: dict):
    from zoneinfo import ZoneInfo

    return ZoneInfo(cfg["timezone"])


# ------------------------------------------------------------------------------------------------
# build
# ------------------------------------------------------------------------------------------------
def collect(conn: sqlite3.Connection, now: datetime | None = None) -> dict[str, dict]:
    """All public data files, keyed by their path under site/data/."""
    cfg = load_config()
    now = now or utcnow()
    snap = Snapshot(conn, cfg, now)
    window_start = top_window(conn, now)
    files: dict[str, dict] = {
        "clusters.json": snap.clusters_json(),
        "stories.json": snap.stories_json(),
        "mna.json": snap.mna_json(),
        "trending.json": snap.trending_json(),
        "sources.json": snap.sources_json(),
    }
    firm_index, firm_pages = snap.firms()
    files["firms/index.json"] = firm_index
    for slug, page in firm_pages.items():
        files[f"firms/{slug}.json"] = page
    files.update(digest_files(snap, window_start))
    src = files["sources.json"]["sources"]
    files["meta.json"] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": to_iso(now),
        "last_refresh": db.get_meta(conn, "last_ingest"),
        "previous_refresh": db.get_meta(conn, "previous_success"),
        "top_window_start": to_iso(window_start),
        "timezone": cfg["timezone"],
        "demo": db.get_meta(conn, "demo") == "1",
        "counts": {"stories": len(files["stories.json"]["stories"]), "clusters": len(snap.clusters),
                   "deals": len(files["mna.json"]["deals"]), "firms": len(firm_index["firms"])},
        "sources_ok": sum(1 for s in src if s["ok"]),
        "sources_total": len(src),
        "sources": [{"name": s["name"], "ok": s["ok"], "method": s["method"], "items_last_run": s["items_last_run"]} for s in src],
        "categories": _categories(),
        "sec": {"data_date": snap.sec_date, "firm_count": len(snap.sec)},
        "digest": {"date": files["digest.json"]["date"], "ai": files["digest.json"]["ai"],
                   "last_good_date": (files["digest.json"]["last_good_digest"] or {}).get("date")},
        "footer_note": FOOTER_NOTE,
    }
    return files


def _categories() -> list[str]:
    from .config import load_categories

    return load_categories().categories


def build_site(out: Path, now: datetime | None = None, write_state: bool = True) -> dict:
    """Write out/site (public) and, optionally, out/state (private) + out/vercel.json."""
    conn = db.connect()
    try:
        files = collect(conn, now)
        # a teaser identical to (part of) its own headline isn't private text
        teasers = [r["description"] for r in conn.execute("SELECT title, description FROM items WHERE description != ''")
                   if r["description"].strip() not in r["title"]]
    finally:
        conn.close()
    site = out / "site"
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(paths.FRONTEND_DIR, site)
    data = site / "data"
    for rel, obj in files.items():
        p = data / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ddir = paths.digests_dir()
    for md in sorted(ddir.glob("????-??-??.md")) if ddir.exists() else []:
        (data / "digests").mkdir(parents=True, exist_ok=True)
        shutil.copy(md, data / "digests" / md.name)
    (site / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (out / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(LIVE_README, encoding="utf-8")
    privacy_check(site, teasers)
    from .contract import validate_data_dir

    for problem in validate_data_dir(data):  # the test suite enforces this strictly; at runtime, warn
        print(f"::warning::data contract: {problem}")
    if write_state:
        from .state import save

        # this refresh becomes "the previous successful refresh" for the next Top Stories window
        conn = db.connect()
        db.set_meta(conn, "previous_success", db.get_meta(conn, "last_ingest") or to_iso(now or utcnow()))
        conn.commit()
        conn.close()
        save(out)
    return {"files": len(files), "clusters": len(files["clusters.json"]["clusters"]),
            "firms": len(files["firms/index.json"]["firms"]), "digest_ai": files["digest.json"]["ai"]}


# ------------------------------------------------------------------------------------------------
# privacy
# ------------------------------------------------------------------------------------------------
class PrivacyError(RuntimeError):
    pass


MIN_TEASER_CHECK = 40  # shorter strings are too generic to be a meaningful leak signal


def privacy_check(site: Path, teasers: list[str]) -> None:
    """Fail the build if the public output contains a database or any raw publisher teaser."""
    problems = []
    blobs: list[tuple[Path, str]] = []
    for p in site.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm"} or p.name.endswith(("-wal", "-shm")):
            problems.append(f"database file in public output: {p.relative_to(site)}")
            continue
        try:
            blobs.append((p, p.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            if p.read_bytes()[:16].startswith(b"SQLite format 3"):
                problems.append(f"SQLite file in public output: {p.relative_to(site)}")
    needles = {t.strip() for t in teasers if len(t.strip()) >= MIN_TEASER_CHECK}
    for p, text in blobs:
        # JSON escapes non-ASCII and quotes differently; compare against the decoded form too
        variants = [text]
        if p.suffix == ".json":
            try:
                variants.append(json.dumps(json.loads(text), ensure_ascii=False))
            except ValueError:
                pass
        for n in needles:
            if any(n in v for v in variants):
                problems.append(f"publisher teaser text in {p.relative_to(site)}: {n[:60]!r}…")
                break
    if problems:
        raise PrivacyError("; ".join(problems[:10]))
