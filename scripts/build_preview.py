"""Build a single self-contained HTML preview of the Wealth Wire UI (no server needed).

It inlines the real static files (index.html, style.css, app.js) and answers /api/* calls in the browser
from a snapshot of the current data dir, so the page can be opened as a file or shown inside Claude.

    WEALTHWIRE_HOME=demo WEALTHWIRE_CONFIG=demo/config python scripts/build_preview.py
    → preview/wealth-wire-preview.html

Differences from the real app: search is a simple word-prefix match (no FTS5 stemming), and watchlist
edits live only in the page (nothing is written to watchlist.yaml).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WEALTHWIRE_NO_BACKGROUND", "1")

from fastapi.testclient import TestClient  # noqa: E402

from wealthwire import paths  # noqa: E402
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


def main() -> None:
    with TestClient(app) as c:
        feed = c.get("/api/feed", params={"limit": 200}).json()
        data = {
            "meta": c.get("/api/meta").json(),
            "clusters": feed["pinned"] + feed["clusters"],
            "trending": c.get("/api/trending").json(),
            "mna": c.get("/api/mna").json(),
            "digest": c.get("/api/digest").json(),
            "watchlist": [{"name": f["name"], "aliases": f["aliases"]} for f in c.get("/api/watchlist").json()["firms"]],
        }
    static = paths.STATIC_DIR
    html = (static / "index.html").read_text(encoding="utf-8")
    css = (static / "style.css").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace('<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">', "")
    html = html.replace('<link rel="stylesheet" href="/static/style.css">', f"<style>\n{css}\n</style>")
    html = html.replace("<body>", "<body>\n" + BANNER, 1)
    html = html.replace(
        '<script src="/static/app.js"></script>',
        f"<script>window.__WW_DATA__ = {payload};</script>\n<script>{SHIM}</script>\n<script>\n{js}\n</script>",
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html) // 1024} KB, {len(data['clusters'])} stories)")


if __name__ == "__main__":
    main()
