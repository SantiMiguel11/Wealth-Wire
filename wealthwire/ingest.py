"""Per-source ingestion and SOURCES.md generation."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import db, paths
from .config import PLACEHOLDER_EMAIL, Source, load_config, load_sources
from .dates import to_iso, utcnow
from .discover import common_feed_urls, find_alternate_feeds, parse_listing
from .fetch import Fetcher, FixtureTransport
from .parse import Item, looks_like_feed, parse_feed

log = logging.getLogger("wealthwire.ingest")
_LOCK = threading.Lock()


@dataclass
class SourceRun:
    name: str
    method: str = "failed"            # RSS | discovered RSS | listing fallback | Google News RSS | failed | disabled
    url_used: str = ""
    discovered_feed_url: str = ""
    items: list[Item] = field(default_factory=list)
    fetched: int = 0
    new: int = 0
    ok: bool = False
    notes: list[str] = field(default_factory=list)
    attempts: list[str] = field(default_factory=list)
    dropped: int = 0
    kind: str = "feed"
    src: Source | None = None

    @property
    def reason(self) -> str:
        if self.ok:
            return "; ".join(self.notes)
        return "; ".join(self.attempts + self.notes) or "no feed and no parseable listing"


class SourceIngester:
    def __init__(self, fetcher: Fetcher, conn: sqlite3.Connection, local_tz: str, now: datetime):
        self.fetcher = fetcher
        self.conn = conn
        self.local_tz = local_tz
        self.now = now
        self._sec = None
        self._categorizer = None

    @property
    def sec(self):
        if self._sec is None:
            from .firms import SecMatcher

            self._sec = SecMatcher.from_db(self.conn)
        return self._sec

    @property
    def categorizer(self):
        if self._categorizer is None:
            from .categorize import Categorizer

            self._categorizer = Categorizer()
        return self._categorizer

    def _google_news(self, run: SourceRun, src: Source) -> None:
        from .gnews import feed_url, parse_google_news

        url = src.feed_url or feed_url(src.query or f"site:{src.homepage}")
        res = self.fetcher.get(url, conditional=True)
        if res.not_modified:
            run.method, run.url_used, run.ok = "Google News RSS", url, True
            run.notes.append("not modified since last run (HTTP 304)")
            return
        if not res.ok:
            run.attempts.append(f"{url}: {res.describe_failure()}")
            return
        items, skipped = parse_google_news(res.content, src.name, src.homepage, self.now, self.local_tz)
        run.method, run.url_used, run.ok, run.items = "Google News RSS", url, True, items
        run.notes.append("via Google News RSS (the outlet blocks automated readers); links are Google redirects")
        if skipped:
            run.notes.append(f"{skipped} items from other outlets skipped")

    def _filter(self, run: SourceRun) -> None:
        """Age limit (wires, Google News) and the wealth-management filter (wires)."""
        src = run.src
        if not src or not run.items:
            return
        kept = run.items
        if src.max_age_days:
            from .dates import from_iso

            cutoff = self.now - timedelta(days=src.max_age_days)
            kept = [it for it in kept if from_iso(it.published_at) >= cutoff]
            if len(kept) < len(run.items):
                run.notes.append(f"{len(run.items) - len(kept)} items older than {src.max_age_days} days ignored")
        if src.kind == "wire":
            from .wires import keep_wire_item

            before = len(kept)
            kept = [it for it in kept if keep_wire_item(it.title, it.description, self.sec, self.categorizer)[0]]
            run.dropped = before - len(kept)
            run.notes.append(f"wealth-management filter kept {len(kept)} of {before} (dropped {run.dropped})")
        run.items = kept

    def _try_feed(self, run: SourceRun, src: Source, url: str, method: str) -> bool:
        res = self.fetcher.get(url, conditional=True)
        if res.not_modified:
            run.method, run.url_used, run.ok = method, url, True
            run.notes.append("not modified since last run (HTTP 304)")
            return True
        if not res.ok:
            run.attempts.append(f"{url}: {res.describe_failure()}")
            return False
        items, parsed = parse_feed(res.content, src.name, self.now, gated=src.gated, local_tz=self.local_tz)
        if not looks_like_feed(parsed):
            run.attempts.append(f"{url}: not a feed (content-type {res.content_type or 'unknown'})")
            return False
        if not items:
            run.attempts.append(f"{url}: valid feed but 0 usable items")
            return False
        run.method, run.url_used, run.ok, run.items = method, url, True, items
        return True

    def run(self, src: Source) -> SourceRun:
        run = SourceRun(src.name, kind=src.kind, src=src)
        if not src.enabled:
            run.method = "disabled"
            run.notes.append("disabled in sources.yaml")
            return run
        if src.kind == "google_news":
            self._google_news(run, src)
            if not run.ok:
                run.method = "failed"
            return self._finish(run)
        if src.gated:
            run.notes.append("gated: headline, link, date and source only")

        prior = self.conn.execute("SELECT discovered_feed_url FROM source_status WHERE name=?", (src.name,)).fetchone()
        prior_feed = prior["discovered_feed_url"] if prior else ""

        # 1. configured feed
        if src.feed_url and self._try_feed(run, src, src.feed_url, "RSS"):
            return self._finish(run)
        # 2. feed discovered on an earlier run
        if prior_feed and prior_feed != src.feed_url and self._try_feed(run, src, prior_feed, "discovered RSS"):
            run.discovered_feed_url = prior_feed
            return self._finish(run)

        # 3. autodiscovery on homepage / news page (robots-checked, these are non-feed fetches)
        pages: dict[str, str] = {}
        tried: set[str] = {src.feed_url, prior_feed}
        for page in dict.fromkeys(p for p in (src.homepage, src.listing_url) if p):
            allowed, why = self.fetcher.robots.check(page)
            if not allowed:
                run.attempts.append(f"{page}: skipped, {why}")
                continue
            res = self.fetcher.get(page)
            if not res.ok:
                run.attempts.append(f"{page}: {res.describe_failure()}")
                continue
            pages[page] = res.text
            alternates = find_alternate_feeds(res.text, res.url)
            if not alternates:
                run.attempts.append(f"{page}: no <link rel=alternate> feed")
            for feed in alternates:
                if feed in tried:
                    continue
                tried.add(feed)
                if self._try_feed(run, src, feed, "discovered RSS"):
                    run.discovered_feed_url = feed
                    return self._finish(run)

        # 4. common feed paths (guesses → robots-checked)
        if src.homepage:
            for feed in common_feed_urls(src.homepage):
                if feed in tried:
                    continue
                tried.add(feed)
                allowed, why = self.fetcher.robots.check(feed)
                if not allowed:
                    run.attempts.append(f"{feed}: skipped, {why}")
                    continue
                if self._try_feed(run, src, feed, "discovered RSS"):
                    run.discovered_feed_url = feed
                    return self._finish(run)

        # 5. listing-page fallback
        if src.listing_url:
            html = pages.get(src.listing_url)
            if html is None and not any(src.listing_url in a and "skipped" in a for a in run.attempts):
                allowed, why = self.fetcher.robots.check(src.listing_url)
                if allowed:
                    res = self.fetcher.get(src.listing_url)
                    html = res.text if res.ok else None
                    if not res.ok:
                        run.attempts.append(f"{src.listing_url}: {res.describe_failure()}")
                else:
                    run.attempts.append(f"{src.listing_url}: skipped, {why}")
            if html:
                items = parse_listing(html, src.listing_url, src.name, self.now, self.local_tz)
                if items:
                    run.method, run.url_used, run.ok, run.items = "listing fallback", src.listing_url, True, items
                    return self._finish(run)
                run.attempts.append(f"{src.listing_url}: listing page had no parseable headlines")
        elif not run.attempts:
            run.attempts.append("no feed_url, homepage or listing_url configured")

        run.method = "failed"
        return self._finish(run)

    def _finish(self, run: SourceRun) -> SourceRun:
        raw = len(run.items)
        self._filter(run)
        run.fetched = raw
        new = 0
        for it in run.items:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO items(title, url, canonical_url, source, published_at, published_estimated, fetched_at, description) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (it.title, it.url, it.canonical_url, it.source, it.published_at, int(it.published_estimated), it.fetched_at, it.description[:300]),
            )
            new += cur.rowcount
        run.new = new
        if run.ok and run.method == "RSS":
            run.attempts.clear()  # configured feed worked; earlier attempts are irrelevant
        self.conn.execute(
            "INSERT INTO source_status(name, method, url_used, discovered_feed_url, items_last_run, new_last_run, ok, reason, last_run_at, kind, dropped_last_run) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET method=excluded.method, url_used=excluded.url_used, "
            "discovered_feed_url=CASE WHEN excluded.discovered_feed_url != '' THEN excluded.discovered_feed_url ELSE source_status.discovered_feed_url END, "
            "items_last_run=excluded.items_last_run, new_last_run=excluded.new_last_run, ok=excluded.ok, reason=excluded.reason, "
            "last_run_at=excluded.last_run_at, kind=excluded.kind, dropped_last_run=excluded.dropped_last_run",
            (run.name, run.method, run.url_used, run.discovered_feed_url, run.fetched, run.new, int(run.ok), run.reason,
             to_iso(self.now), run.kind, run.dropped),
        )
        self.conn.commit()
        return run


def write_sources_md(runs: list[SourceRun], now: datetime, cfg: dict, demo: bool, path: Path | None = None,
                     sec_status: dict | None = None) -> Path:
    path = path or paths.sources_md_path()
    ok = sum(1 for r in runs if r.ok)
    lines = [
        "# Sources",
        "",
        f"_Regenerated by every ingestion. Last run: {to_iso(now)} (UTC). {ok} of {len(runs)} sources ingested successfully._",
        "",
    ]
    if demo:
        lines += ["> **Offline fixture run** — these results come from `--fixtures`, not the live sites.", ""]
    if sec_status:
        lines += [f"**SEC adviser data** (firm detection): {sec_status.get('status')} — file dated "
                  f"{sec_status.get('data_date') or 'n/a'}, {sec_status.get('firms', 0)} SEC-registered advisers"
                  + (f". {sec_status['reason']}" if sec_status.get("reason") else "") + ".", ""]
    if cfg.get("contact_email") == PLACEHOLDER_EMAIL:
        lines += ["> ⚠ `contact_email` in config.yaml is still the placeholder `me@example.com`. Set your own address — SEC.gov requires a real contact in the User-Agent.", ""]
    lines += [
        "| Source | Kind | Status | Method | URL used | Items (last run) | New | Dropped | Notes |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for r in runs:
        status = "✅ ok" if r.ok else ("⏸ disabled" if r.method == "disabled" else "❌ failed")
        notes = "; ".join(r.notes) if r.ok else "see below"
        url = f"<{r.url_used}>" if r.url_used else "—"
        lines.append(f"| {r.name} | {r.kind} | {status} | {r.method} | {url} | {r.fetched} | {r.new} | {r.dropped} | {notes.replace('|', '/') or ''} |")
    failures = [r for r in runs if not r.ok]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("None.")
    for r in failures:
        lines.append(f"### {r.name}")
        lines.append("")
        for a in (r.attempts + [n for n in r.notes if n not in r.attempts]) or ["no feed and no parseable listing"]:
            lines.append(f"- {a}")
        lines.append("")
    lines += [
        "",
        "## Method legend",
        "",
        "- **RSS** — the `feed_url` configured in sources.yaml.",
        "- **discovered RSS** — found via `<link rel=\"alternate\">` on the homepage/news page or a common path (`/feed`, `/rss`, `/rss.xml`); cached for later runs.",
        "- **listing fallback** — headlines, links and dates parsed from the public listing page (robots.txt permitting).",
        "- **Google News RSS** — Google News search feed scoped to the outlet's site (`site:` query), for outlets that block automated readers. Items are attributed to the outlet; links are Google redirect URLs (not resolved); deduped by headline + outlet + date.",
        "- **Dropped** — press-release wire items removed by the wealth-management filter (wealth terms AND an SEC firm or an M&A / people-move story).",
        "- **failed** — every step above failed; the exact reasons are listed per attempt.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_ingest(fixtures: Path | None = None, now: datetime | None = None, quiet: bool = False) -> dict:
    """Ingest every enabled source, recompute derived data, regenerate SOURCES.md."""
    from .pipeline import recompute  # local import: pipeline imports heavy modules

    with _LOCK:
        cfg = load_config()
        sources = load_sources()
        now = now or utcnow()
        conn = db.connect()
        http = cfg["http"]
        transport = FixtureTransport(fixtures) if fixtures else None
        fetcher = Fetcher(
            cfg["user_agent"],
            per_host_delay=0 if fixtures else float(http["per_host_delay_seconds"]),
            timeout=float(http["timeout_seconds"]),
            retries=int(http["retries"]),
            backoff=0 if fixtures else float(http["backoff_seconds"]),
            conn=conn,
            transport=transport,
        )
        runs: list[SourceRun] = []
        try:
            from .sec import maybe_update

            if fixtures:  # the offline fixture file is tiny by design
                cfg.setdefault("sec", {})["allow_small_file"] = True
            sec_status = maybe_update(conn, fetcher, now, cfg)
            db.set_meta(conn, "sec_status", json.dumps(sec_status))
            conn.commit()
            if not quiet:
                print(f"[SEC] adviser data: {sec_status.get('status')} (file {sec_status.get('data_date') or '—'}, "
                      f"{sec_status.get('firms', 0)} firms){' — ' + sec_status['reason'] if sec_status.get('reason') else ''}")
            ingester = SourceIngester(fetcher, conn, cfg["timezone"], now)
            for src in sources:
                run = ingester.run(src)
                runs.append(run)
                if not quiet:
                    flag = "ok " if run.ok else "ERR"
                    print(f"[{flag}] {src.name:<28} {run.method:<17} fetched={run.fetched:<3} new={run.new:<3} {'' if run.ok else run.reason[:160]}")
        finally:
            fetcher.close()
        db.set_meta(conn, "last_ingest", to_iso(now))
        db.set_meta(conn, "demo", "1" if fixtures else "0")
        conn.commit()
        write_sources_md(runs, now, cfg, demo=bool(fixtures), sec_status=sec_status)
        result = recompute(conn, now=now)
        conn.close()
        summary = {
            "sources_ok": sum(r.ok for r in runs),
            "sources_total": len(runs),
            "fetched": sum(r.fetched for r in runs),
            "new": sum(r.new for r in runs),
            **result,
        }
        if not quiet:
            print(
                f"Done: {summary['sources_ok']}/{summary['sources_total']} sources ok, "
                f"{summary['fetched']} items fetched, {summary['new']} new, {summary['clusters']} clusters, "
                f"{summary['deals']} M&A rows (local date {summary['local_date']})"
            )
        return summary
