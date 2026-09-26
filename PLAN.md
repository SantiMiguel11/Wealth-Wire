# Wealth Wire — Plan

A local, single-user news aggregator for the U.S. wealth management / RIA industry.
Everything runs on the laptop: Python ingestion → SQLite (FTS5) → FastAPI JSON API → one static page.
No LLM or hosted NLP calls anywhere in the code; all "intelligence" is keyword rules, regexes and rapidfuzz.

## Architecture

```
            sources.yaml ─┐
                          ▼
  ┌───────────── ingest (python -m wealthwire ingest / every 2h in server) ─────────────┐
  │ fetch.py   polite HTTP: UA w/ contact email, ≥2s per host, 15s timeout,             │
  │            1 retry w/ backoff, ETag/Last-Modified, robots.txt for non-feed fetches  │
  │ discover.py feed_url → cached discovered feed → <link rel=alternate> → /feed,/rss…  │
  │            → listing-page fallback (BeautifulSoup: headline, link, date)             │
  │ parse.py   feedparser → Item(title,url,canonical_url,source,published_at,           │
  │            fetched_at,description≤300, no content:encoded; gated → empty desc)      │
  │ db.py      INSERT OR IGNORE on UNIQUE(canonical_url)                                 │
  └──────────────────────────────┬───────────────────────────────────────────────────────┘
                                 ▼  pipeline.py (full recompute of derived data, deterministic)
        categorize.py → extract.py (firms, AUM) → cluster.py → mna.py → digest.py
                                 ▼                                    ▼
                        SOURCES.md                          new_stories.json
                                 ▼
             server.py (FastAPI)  /api/*  +  static/ (index.html, app.js, style.css)
```

Derived data (category, firms, AUM, clusters, M&A rows) is recomputed from the stored items after
every ingestion. The corpus is small (thousands of rows), recompute takes well under a second, and it
means edits to categories.yaml / watchlist.yaml / thresholds apply retroactively with no migrations.

## Module layout

```
wealthwire/
  __main__.py     CLI: ingest [--fixtures DIR], serve, recompute
  paths.py        repo root, config dir (WEALTHWIRE_CONFIG), data dir (WEALTHWIRE_HOME)
  config.py       load/validate config.yaml, sources.yaml, categories.yaml, watchlist.yaml, firm_stoplist.yaml
  db.py           schema, connect(), migrations-by-CREATE-IF-NOT-EXISTS
  urls.py         canonicalize()
  text.py         strip_html(), truncate(), normalize helpers
  dates.py        parse feed/listing dates → UTC ISO
  fetch.py        Fetcher (httpx), RobotsCache, fixture transport for offline runs/tests
  discover.py     autodiscovery, common paths, listing parser
  parse.py        feed → items
  ingest.py       per-source orchestration, SOURCES.md writer
  categorize.py   ordered keyword rules
  extract.py      AUM parsing/extraction, firm extraction
  watchlist.py    alias matching, YAML read/write
  cluster.py      title normalization, scoring, union-find within window
  mna.py          acquirer/target/AUM/confidence extraction
  pipeline.py     recompute everything, write new_stories.json
  digest.py       new_stories windowing/ranking, digest markdown rendering
  server.py       FastAPI app, background re-ingest loop
  static/         index.html, app.js, style.css
```

## DB schema (SQLite, WAL)

| table | purpose |
|---|---|
| `items(id, title, url, canonical_url UNIQUE, source, published_at, published_estimated, fetched_at, description CHECK(len≤300), category, cluster_id, aum_usd)` | stored items + derived columns |
| `items_fts` (FTS5, external content = items; title, description; porter tokenizer) + triggers | full-text search |
| `item_firms(item_id, firm)` | extracted firm mentions |
| `clusters(id, headline_item_id, headline, url, category, first_seen, first_published, last_published, outlet_count, item_count, aum_usd)` | one row per story |
| `mna_deals(cluster_id PK, acquirer, target, target_aum_usd, deal_type, deal_date, confidence, note)` | M&A tracker |
| `source_status(name PK, method, url_used, discovered_feed_url, items_last_run, new_last_run, ok, reason, last_run_at)` | drives SOURCES.md and the Sources tab |
| `http_cache(url PK, etag, last_modified)` | conditional GET |
| `meta(key PK, value)` | last ingest time, demo flag |

Only title, url, canonical_url, source, published_at, fetched_at and a ≤300-char description are stored
from the article. No content fields are ever read.

## API

`GET /api/feed?q&source&category&from&to&watch&limit&offset` → `{pinned, clusters, total}`
`GET /api/meta` · `GET /api/trending` · `GET /api/mna?confidence=` · `GET /api/digest` · `GET /api/sources`
`GET/POST /api/watchlist`, `DELETE /api/watchlist/{name}` (writes watchlist.yaml)

## UI

Single page, tabs Feed · M&A · Digest · Sources. All filter state in the query string
(`?tab=feed&q=…&source=…&category=…&from=…&to=…&watch=1`, `?tab=mna&conf=low`).
Feed: filter bar, pinned watchlist block, clustered cards; right sidebar with Trending Firms and
Watchlist manager (stacks below on mobile). Dark/light via `prefers-color-scheme` + toggle in localStorage.

## Test plan (pytest, no network — saved fixture feeds + httpx MockTransport)

| feature | tests |
|---|---|
| 1 ingestion | canonicalize cases; ingest fixture set twice → 0 new rows; description ≤300 and HTML stripped; content:encoded ignored (incl. feedparser's copy into summary); gated source → empty description; date parsing RFC-822 w/ offsets, ISO-8601 Atom, `Z`, naive listing dates in config tz; discovery via `<link rel=alternate>`, via `/feed`, listing fallback; robots disallow recorded; conditional GET sends If-None-Match and handles 304; per-host delay; SOURCES.md content |
| 2 web UI | API tests via FastAPI TestClient: search, source/category/date filters; Playwright screenshots |
| 3 categories | People Moves vs M&A cases ("team joins", "breaks away", "hires" vs "acquires", "takes stake", "sells to"), each category |
| 4 clustering | should-match / should-not-match headline pair fixtures; card grouping; window |
| 5 extraction | every AUM format; context rules (fines are not AUM); firm spans; stoplist false positives |
| 6 M&A | each pattern; role inversion ("sells to", "acquired by"); blanks + low confidence when ambiguous |
| 7 watchlist | case-insensitive, word boundaries, <3-char aliases ignored, false positives; YAML round-trip |
| 8 digest | windowing from `.last_digest` / 24h fallback, ranking order, fields |

Playwright (`scripts/screenshots.py`): Feed, filtered Feed, search, watchlist highlight, M&A, Digest ×
1440×900 & 390×844 × light & dark → `screenshots/`, failing on any console error or failed request.
