"""Build a self-contained static version of the Wealth Wire UI (no server needed).

It inlines the real static files (index.html, style.css, app.js) and answers /api/* calls in the browser
from a snapshot of the current data dir.

Preview (single file, e.g. to open locally or show inside Claude):
    WEALTHWIRE_HOME=demo WEALTHWIRE_CONFIG=demo/config python scripts/build_preview.py
    → preview/wealth-wire-preview.html

Public site (what the GitHub Action publishes to the `live` branch that Vercel serves):
    python scripts/build_preview.py --site _live
    → _live/site/index.html, _live/site/robots.txt, _live/vercel.json, _live/state/ (DB for the next run)
    Uses the `site:` section of config.yaml: publisher descriptions are left out unless
    show_descriptions is true, excluded sources are dropped, the watchlist is read-only, pages are noindex.

Differences from the real app: search is a simple word-prefix match (no FTS5 stemming).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WEALTHWIRE_NO_BACKGROUND", "1")

from fastapi.testclient import TestClient  # noqa: E402

from wealthwire import paths  # noqa: E402
from wealthwire.config import load_config  # noqa: E402
from wealthwire.server import app  # noqa: E402

OUT = ROOT / "preview" / "wealth-wire-preview.html"

SHIM = r"""
(function () {
  const D = window.__WW_DATA__;
  const NOW = new Date(D.meta.last_ingest || Date.now()).getTime();
  let watch = D.watchlist.map((f) => ({ name: f.name, aliases: f.aliases.slice() }));

  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  function terms(f) {
    const out = [], seen = new Set();
    for (const t of [f.name, ...f.aliases]) {
      const n = t.split(/\s+/).join(" ").trim();
      if (n.replace(/ /g, "").length < 3 || seen.has(n.toLowerCase())) continue;
      seen.add(n.toLowerCase()); out.push(n);
    }
    return out;
  }
  function matcher(f) {
    const ts = terms(f).sort((a, b) => b.length - a.length);
    if (!ts.length) return null;
    return new RegExp("(?<![\\w&-])(?:" + ts.map((t) => esc(t).replace(/ /g, "\\s+")).join("|") + ")(?![\\w&]|-\\w)", "i");
  }
  const text = (c) => c.items.map((i) => i.title + "\n" + i.description).join("\n");
  function hits(c) {
    const t = text(c);
    return watch.filter((f) => { const re = matcher(f); return re && re.test(t); }).map((f) => f.name);
  }
  const recent = (c) => new Date(c.last_published).getTime() >= NOW - 7 * 864e5;

  function matchesQ(c, q) {
    const qs = (q || "").toLowerCase().match(/[\w$&.'-]+/g) || [];
    if (!qs.length) return true;
    return c.items.some((it) => {
      const words = (it.title + " " + it.description).toLowerCase().match(/[\w$&.'-]+/g) || [];
      return qs.every((t) => words.some((w) => w.startsWith(t.replace(/^[.'-]+|[.'-]+$/g, ""))));
    });
  }

  function feed(p) {
    const q = p.get("q") || "", src = (p.get("source") || "").split(",").filter(Boolean);
    const cats = (p.get("category") || "").split(",").filter(Boolean);
    const from = p.get("from"), to = p.get("to"), w = p.get("watch") === "1" || p.get("watch") === "true";
    const offset = +(p.get("offset") || 0), limit = +(p.get("limit") || 50);
    let list = D.clusters.filter((c) => {
      if (cats.length && !cats.includes(c.category)) return false;
      return c.items.some((it) =>
        (!src.length || src.includes(it.source)) &&
        (!from || it.published_at >= new Date(from).toISOString().replace(/\.\d+Z$/, "Z")) &&
        (!to || it.published_at < new Date(to).toISOString().replace(/\.\d+Z$/, "Z"))) && matchesQ(c, q);
    }).map((c) => ({ ...c, watchlist_hits: hits(c) }));
    list.sort((a, b) => (b.last_published > a.last_published ? 1 : b.last_published < a.last_published ? -1 : b.id - a.id));
    let pinned = [];
    if (w) list = list.filter((c) => c.watchlist_hits.length);
    else {
      pinned = list.filter((c) => c.watchlist_hits.length && recent(c)).slice(0, 10);
      const ids = new Set(pinned.map((c) => c.id));
      list = list.filter((c) => !ids.has(c.id));
    }
    return { pinned: offset === 0 ? pinned : [], clusters: list.slice(offset, offset + limit), total: list.length, offset, limit };
  }

  function json(body, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  }
  const realFetch = window.fetch.bind(window);
  window.fetch = function (input, opts = {}) {
    const url = new URL(typeof input === "string" ? input : input.url, "http://preview.local/");
    const path = url.pathname, method = (opts.method || "GET").toUpperCase();
    if (!path.startsWith("/api/")) return realFetch(input, opts);
    if (path === "/api/meta") return json(D.meta);
    if (path === "/api/feed") return json(feed(url.searchParams));
    if (path === "/api/trending") return json(D.trending);
    if (path === "/api/digest") return json(D.digest);
    if (path === "/api/mna") {
      const c = url.searchParams.get("confidence");
      return json(c ? D.mna.filter((r) => r.confidence === c) : D.mna);
    }
    if (path === "/api/watchlist" && method === "GET") {
      return json({ firms: watch.map((f) => {
        const re = matcher(f);
        return { name: f.name, aliases: f.aliases, recent: D.clusters.filter((c) => recent(c) && re && re.test(text(c))).length };
      }) });
    }
    if (D.readonly && path.startsWith("/api/watchlist") && method !== "GET") {
      return json({ detail: "Edit watchlist.yaml in the GitHub repo to change the watchlist." }, 403);
    }
    if (path === "/api/watchlist" && method === "POST") {
      const b = JSON.parse(opts.body || "{}");
      const name = (b.name || "").split(/\s+/).join(" ").trim();
      if (name.replace(/ /g, "").length < 3) return json({ detail: "Name must be at least 3 characters (shorter terms are never matched)." }, 422);
      if (watch.some((f) => f.name.toLowerCase() === name.toLowerCase())) return json({ detail: name + " is already on the watchlist." }, 409);
      watch.push({ name, aliases: (b.aliases || []).filter(Boolean) });
      return json({ ok: true, name }, 201);
    }
    if (path.startsWith("/api/watchlist/") && method === "DELETE") {
      const name = decodeURIComponent(path.slice("/api/watchlist/".length)).toLowerCase();
      const before = watch.length;
      watch = watch.filter((f) => f.name.toLowerCase() !== name);
      return before === watch.length ? json({ detail: "not on the watchlist" }, 404) : json({ ok: true });
    }
    return json({ detail: "not found" }, 404);
  };
})();
"""

BANNER = (
    '<div style="background:#fef3c7;color:#78350f;border-bottom:1px solid #f59e0b;padding:6px 16px;'
    'font:600 12px/1.4 ui-monospace,Menlo,monospace;text-align:center">'
    "STATIC PREVIEW · synthetic demo data from offline fixtures — not real news · "
    "search is simplified and watchlist edits aren't saved</div>"
)


SITE_README = """# live branch (generated — do not edit)

Rebuilt and force-pushed every 2 hours by `.github/workflows/refresh-site.yml` on `main`.

- `site/` is the static website Vercel serves (see `vercel.json`).
- `state/` carries the database between runs so history accumulates. It is not served.
"""

VERCEL_JSON = {
    "buildCommand": "echo static site",
    "installCommand": "echo no install",
    "framework": None,
    "outputDirectory": "site",
    "headers": [{"source": "/(.*)", "headers": [{"key": "X-Robots-Tag", "value": "noindex, nofollow"}]}],
}

READONLY_CSS = "#watch-add, .watchlist button { display: none !important; }"
READONLY_NOTE = (
    '<p class="form-msg">To change this list, edit <code>watchlist.yaml</code> in the GitHub repo. '
    "The site picks it up on its next refresh.</p>"
)


def snapshot() -> dict:
    with TestClient(app) as c:
        feed = c.get("/api/feed", params={"limit": 200}).json()
        return {
            "meta": c.get("/api/meta").json(),
            "clusters": feed["pinned"] + feed["clusters"],
            "trending": c.get("/api/trending").json(),
            "mna": c.get("/api/mna").json(),
            "digest": c.get("/api/digest").json(),
            "watchlist": [{"name": f["name"], "aliases": f["aliases"]} for f in c.get("/api/watchlist").json()["firms"]],
        }


def public_view(data: dict, show_descriptions: bool, exclude: set[str], top_hours: float = 24) -> dict:
    """Drop excluded sources and (unless allowed) publisher descriptions from everything embedded in the page."""
    clusters = []
    for c in data["clusters"]:
        items = [dict(it) for it in c["items"] if it["source"] not in exclude]
        if not items:
            continue
        if not show_descriptions:
            for it in items:
                it["description"] = ""
        c = dict(c, items=items)
        c["sources"] = [s for s in c["sources"] if s["name"] not in exclude]
        c["outlet_count"] = len(c["sources"])
        head = items[0]
        c["headline"], c["url"] = head["title"], head["url"]
        c["first_published"] = head["published_at"]
        c["last_published"] = max(it["published_at"] for it in items)
        c["description"] = next((it["description"] for it in items if it["description"]), "")
        clusters.append(c)
    data["clusters"] = clusters

    rows = []
    for r in data["mna"]:
        r = dict(r, sources=[s for s in r["sources"] if s["name"] not in exclude])
        if r["sources"]:
            rows.append(r)
    data["mna"] = rows

    # trending firms, recounted on what is actually shown
    now = datetime.fromisoformat((data["meta"].get("last_ingest") or "1970-01-01T00:00:00Z").replace("Z", "+00:00"))
    since = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts: dict[str, int] = {}
    for c in clusters:
        if c["last_published"] >= since:
            for f in set(c["firms"]):
                counts[f] = counts.get(f, 0) + 1
    data["trending"] = [{"firm": f, "stories": n} for f, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:15]]

    # "Top stories" tab: stories from the window before the latest refresh (the Claude-written digest is not
    # part of the public site). Rank: watchlist hits, then outlet count, then recency.
    cutoff = (now - timedelta(hours=top_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ranked = sorted((c for c in clusters if c["last_published"] >= cutoff), key=lambda c: c["last_published"], reverse=True)
    ranked.sort(key=lambda c: (-len(c.get("watchlist_hits") or []), -c["outlet_count"]))
    top = [
        {"cluster_id": c["id"], "headline": c["headline"], "category": c["category"],
         "sources": [{"name": s["name"], "url": s["url"]} for s in c["sources"]], "outlet_count": c["outlet_count"],
         "watchlist_hits": c.get("watchlist_hits") or [], "firms": c["firms"], "aum_usd": c["aum_usd"],
         "descriptions": [], "first_seen": c["first_seen"]}
        for c in ranked
    ]
    data["digest"] = {"date": None, "filename": None, "html": None, "top": top[:10], "site_mode": True,
                      "window_hours": top_hours}

    data["meta"]["sources"] = [s for s in data["meta"]["sources"] if s["name"] not in exclude]
    data["meta"]["items"] = sum(len(c["items"]) for c in clusters)
    data["meta"]["clusters"] = len(clusters)
    data["readonly"] = True
    return data


def render(data: dict, banner: str = "", extra_head: str = "", extra_css: str = "", watch_note: str = "") -> str:
    static = paths.STATIC_DIR
    html = (static / "index.html").read_text(encoding="utf-8")
    css = (static / "style.css").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")
    icon = base64.b64encode((static / "favicon.svg").read_bytes()).decode()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace('<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">',
                        f'<link rel="icon" href="data:image/svg+xml;base64,{icon}">' + extra_head)
    html = html.replace('<link rel="stylesheet" href="/static/style.css">', f"<style>\n{css}\n{extra_css}\n</style>")
    if banner:
        html = html.replace("<body>", "<body>\n" + banner, 1)
    if watch_note:
        html = html.replace('<ul id="watchlist" class="watchlist"></ul>', '<ul id="watchlist" class="watchlist"></ul>' + watch_note)
    return html.replace(
        '<script src="/static/app.js"></script>',
        f"<script>window.__WW_DATA__ = {payload};</script>\n<script>{SHIM}</script>\n<script>\n{js}\n</script>",
    )


def build_site(out: Path) -> None:
    cfg = load_config().get("site") or {}
    data = public_view(snapshot(), bool(cfg.get("show_descriptions", False)), set(cfg.get("exclude_sources") or []),
                       float(cfg.get("top_stories_hours", 24)))
    html = render(data, extra_head='\n<meta name="robots" content="noindex, nofollow">',
                  extra_css=READONLY_CSS, watch_note=READONLY_NOTE)
    if not cfg.get("show_descriptions", False):
        html = html.replace('placeholder="Search headlines &amp; descriptions"', 'placeholder="Search headlines"')
    if out.exists():
        shutil.rmtree(out)
    (out / "site").mkdir(parents=True)
    (out / "state").mkdir()
    (out / "site" / "index.html").write_text(html, encoding="utf-8")
    (out / "site" / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (out / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(SITE_README, encoding="utf-8")
    for src in (paths.db_path(), paths.sources_md_path(), paths.new_stories_path()):
        if src.exists():
            shutil.copy(src, out / "state" / src.name)
    print(f"wrote {out}/site/index.html ({len(html) // 1024} KB, {len(data['clusters'])} stories, "
          f"{data['meta']['items']} items, descriptions {'on' if cfg.get('show_descriptions') else 'off'})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, metavar="OUTDIR", help="build the public site into OUTDIR instead of the preview")
    args = ap.parse_args()
    if args.site:
        build_site(args.site)
        return
    data = snapshot()
    html = render(data, banner=BANNER)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html) // 1024} KB, {len(data['clusters'])} stories)")


if __name__ == "__main__":
    main()
