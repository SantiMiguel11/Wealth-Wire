# Wealth Wire — Phase 2 plan

## Where phase 1 left off

- **Pipeline:** `python -m wealthwire ingest` fetches 11 sources into SQLite and recomputes the derived data
  (categories, regex firms, clusters, M&A).
- **Build:** `scripts/build_preview.py --site` inlines the UI plus a JSON snapshot into one `index.html`,
  and a "fetch shim" fakes the old FastAPI endpoints in the browser.
- **Workflow:** `.github/workflows/refresh-site.yml` runs every 3 days. It restores the DB from `live`,
  ingests, builds, and force-pushes one orphan commit to `live`, which Vercel serves.
- **Watchlist:** lives in `watchlist.yaml`, committed to `main`.

## Target architecture

```
main (source only)                                live (one orphan commit per refresh, force-pushed)
├─ wealthwire/            pipeline (Python)        ├─ site/          ← Vercel serves only this
│   ingest, sources (feed, google_news, wire)      │   index.html, app.js, style.css (copied from frontend/)
│   sec.py (IA data), firms.py (matcher)            │   data/*.json   ← the public data contract
│   refresh.py (orchestration), state.py            ├─ state/         ← never served
│   sitebuild.py (emits site/data/*.json)           │   wealthwire.db (items incl. teasers, SEC firms)
│   aidigest.py, weekly.py, alerts.py               │   digests/*.md, SOURCES.md, firm_eval.json
├─ frontend/              the only rendering code   └─ vercel.json   (outputDirectory site, noindex, rewrites)
├─ schemas/*.schema.json  JSON Schemas for data/*
└─ .github/workflows/refresh-site.yml
```

### Refresh = discrete, testable CLI steps

The workflow calls these in order:

| step | command | notes |
|---|---|---|
| restore | `python -m wealthwire state restore _prev` | copies DB and archives out of the previous `live` tree |
| ingest | `python -m wealthwire ingest` | includes the monthly SEC check (§4), wires (§5), Google News (§6) |
| prepare AI input | `python -m wealthwire digest-input` | writes `_work/digest_input.json`; on Pacific Fridays also `_work/weekly_input.json` |
| AI | `anthropics/claude-code-action@v1` | skipped with a notice when no secret; `continue-on-error: true` |
| finalize | `python -m wealthwire digest-finalize` | validates the Claude output → digest archive, or falls back |
| build | `python -m wealthwire build-site _live` | writes `site/data/*.json`, copies `frontend/`, runs the privacy check (fails closed) |
| alert | `python -m wealthwire alert` | watchlist email; skips quietly when secrets are missing |
| publish | shell | orphan commit → force-push `live` |

### Data contract (`site/data/`)

- `meta.json`, `stories.json`, `clusters.json`, `digest.json`
- `digests/index.json`, `digests/<date>.json`
- `weekly/index.json`, `weekly/<week>.json`
- `mna.json`, `firms/index.json`, `firms/<slug>.json`
- `trending.json`, `sources.json`

Each file has a JSON Schema in `schemas/`, and a test validates every generated file against it.
DATA-CONTRACT.md documents fields, examples, and which view uses which file.

### Frontend

`frontend/` holds `index.html`, `app.js` and `style.css`. They only `fetch('/data/...')`: no API and no
inlined data. Routes:
- `/` feed; `?tab=digest|archive|weekly|mna|sources`
- `/firm/<slug>` via a Vercel rewrite and the local server's SPA fallback

The watchlist is kept in localStorage, with import and export as JSON.

## Section order (one commit each)

Build order differs from the brief's numbering, because every feature publishes through the data contract:

1. **§7 + §9 foundation.** State round-trip, `sitebuild`, data files + schemas + contract, `frontend/` split,
   static local server. Replaces `build_preview.py` and the FastAPI API.
2. **§1** Schedule, concurrency, Top Stories window.
3. **§3** Privacy check + test, remove `watchlist.yaml`, client-side watchlist.
4. **§4** SEC data download/parse, firm matcher (pyahocorasick), SEC AUM, region/state filter, firm pages,
   labeled eval set.
5. **§5 + §6** Press-release wires with the wealth filter + drop counts; Google News for the 3 blocked outlets.
6. **§2 + §8** AI digest (claude-code-action), validation/fallback, archive, weekly recap, watchlist email.
7. **Verification.** End-to-end local refresh, `workflow_dispatch`, Playwright pass, AUDIT-PHASE2.md,
   MANUAL-STEPS.md, README.

## Test plan (all network mocked with saved fixtures)

| area | tests |
|---|---|
| §7 | restore → ingest → publish round trip through a local bare git repo: item count never drops; orphan branch has 1 commit |
| §9 | every `site/data` file validates against its schema; frontend references only `/data/*` |
| §1 | window = max(24h, since previous success); workflow YAML crons parse and are UTC |
| §3 | no `.db`/`.sqlite` in output; no teaser string in any public file; no `watchlist.yaml`; JSON has no description fields |
| §4 | SEC page link discovery, zip (CSV and XLSX) parsing, monthly cache logic; alias generation; single-word guard; ambiguity; 60+ real headlines P/R; SEC AUM labeling; region filter; firm page data |
| §5 | wealth filter keeps/drops, drop counts logged; press release + trade story cluster; confidence raised |
| §6 | Google News parsing, suffix stripped, outlet attribution, dedupe key, no redirect resolution |
| §2 | digest input ranking/fields; output validation (bad JSON, unknown id, emoji, verbatim teaser) → fallback; archive index |
| §8 | Friday detection, weekly aggregates; email skipped without secrets, sent (mocked) with matches, nothing on no match; secret watchlist never written anywhere |
