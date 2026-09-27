# Fiduciary Wire data contract

The pipeline publishes everything the site needs as static JSON under **`/data/`**. The frontend (currently
`frontend/`) reads only these files. Treat this document as a stable API:

- **Contract version:** every file carries `"schema_version": 1`.
- **Compatibility:** fields are only ever added in a backward-compatible way. A breaking change bumps `schema_version`.
- **Schemas:** each file is validated against a JSON Schema in [`schemas/`](schemas). The test suite fails on any
  drift (`tests/test_site.py::test_generated_json_matches_schemas`), and the build logs a warning.
- **Privacy:** no file contains publisher teasers/descriptions or anything from the database beyond what is
  listed here. `tests/test_privacy.py` enforces this.

Conventions:
- Timestamps are ISO-8601 UTC strings, `"2026-09-25T14:02:00Z"`; dates are `"YYYY-MM-DD"`.
- Money is a number in USD (`1200000000` = $1.2B).
- `null` means unknown or not applicable. Fields are never omitted.

## Files at a glance

| file | schema | used by |
|---|---|---|
| `meta.json` | `meta.schema.json` | every view (header status, filters, footer) |
| `clusters.json` | `clusters.schema.json` | Feed, firm pages, watchlist matching, digest cross-links |
| `stories.json` | `stories.schema.json` | (optional) per-article lists; not needed by the current UI |
| `digest.json` | `digest.schema.json` | Digest / Top Stories |
| `digests/index.json` | `digests-index.schema.json` | Archive |
| `digests/<YYYY-MM-DD>.json` | `digest.schema.json` | Archive → one past digest |
| `digests/<YYYY-MM-DD>.md` | (Markdown, not validated) | The same AI digest as Markdown, for reading or download |
| `weekly/index.json` | `weekly-index.schema.json` | Archive, weekly recap |
| `weekly/<YYYY-Www>.json` | `weekly.schema.json` | Weekly M&A recap |
| `mna.json` | `mna.schema.json` | M&A tracker |
| `firms/index.json` | `firms-index.schema.json` | watchlist matching (SEC names), firm links |
| `firms/<slug>.json` | `firm.schema.json` | Firm page `/firm/<slug>` |
| `trending.json` | `trending.schema.json` | Trending Firms sidebar |
| `sources.json` | `sources.schema.json` | Sources view |

Routes the frontend must handle:
- `/` (feed)
- `/firm/<slug>`: Vercel rewrites it to `/index.html`, and so does the local server
- the query-string views `?tab=digest|archive|weekly|mna|sources`

---

## `meta.json`

Refresh-level facts.

| field | type | notes |
|---|---|---|
| `schema_version` | `1` | |
| `generated_at` | timestamp | when this file was built |
| `last_refresh` | timestamp \| null | when ingestion ran |
| `previous_refresh` | timestamp \| null | the previous successful refresh |
| `top_window_start` | timestamp | Top Stories covers clusters first seen after this (≥ 24h back) |
| `timezone` | string | `America/Los_Angeles` |
| `demo` | bool | true when built from offline fixtures |
| `counts` | `{stories, clusters, deals, firms}` | integers |
| `sources_ok`, `sources_total` | int | |
| `sources[]` | `{name, ok, method, items_last_run}` | compact status for the header/filter; full detail in `sources.json` |
| `categories[]` | string | category names in display order |
| `sec` | `{data_date, firm_count}` | date of the SEC adviser file in use (null if none yet) |
| `digest` | `{date, ai, last_good_date}` | whether today's digest is AI-written, and the last good one |
| `footer_note` | string | "Summaries written with Claude from outlet headlines." |

```json
{"schema_version":1,"generated_at":"2026-09-26T19:05:12Z","last_refresh":"2026-09-26T19:04:40Z",
 "previous_refresh":"2026-09-26T13:06:02Z","top_window_start":"2026-09-25T19:04:40Z","timezone":"America/Los_Angeles",
 "demo":false,"counts":{"stories":412,"clusters":371,"deals":24,"firms":58},"sources_ok":13,"sources_total":16,
 "sources":[{"name":"InvestmentNews","ok":true,"method":"discovered RSS","items_last_run":93}],
 "categories":["M&A","People Moves","Regulation","Wealthtech","Products & Funds","Markets","Other"],
 "sec":{"data_date":"2026-09-01","firm_count":15642},"digest":{"date":"2026-09-26","ai":true,"last_good_date":"2026-09-26"},
 "footer_note":"Summaries written with Claude from outlet headlines."}
```

## `clusters.json`

`{schema_version, generated_at, clusters[]}`. One cluster per story, newest activity first.

| field | type | notes |
|---|---|---|
| `id` | int | stable cluster id (smallest article id in the cluster) |
| `headline`, `url` | string | from the earliest article |
| `category` | string | one of `meta.categories` |
| `first_published`, `last_published`, `first_seen` | timestamp | `first_seen` = when Fiduciary Wire first fetched it |
| `outlet_count` | int ≥ 1 | |
| `sources[]` | `{name, url, published_at, kind}` | every outlet covering the story. `kind`: `feed` \| `wire` (press release) \| `google_news` |
| `firms[]` | `{name, slug, crd, verified, city, state}` | `verified` = matched in SEC adviser data (`slug`/`crd` set); unverified = regex fallback, `slug` null |
| `states[]` | string | 2-letter HQ states of verified firms (region filter; "Pacific Northwest" = WA/OR/ID) |
| `aum_usd` | number \| null | |
| `aum_source` | `"headline"` \| `"sec"` \| null | `sec` = no AUM in the headline; this is the SEC-reported AUM of the only verified firm |
| `sec_aum_as_of` | date \| null | set when `aum_source` is `sec`: label it "SEC-reported AUM (as of …)" |
| `press_release` | bool | a wire press release is among the sources |

```json
{"id":1841,"headline":"Mariner acquires $1.2B Summit Ridge Advisors","url":"https://www.thinkadvisor.com/…",
 "category":"M&A","first_published":"2026-09-24T10:00:00Z","last_published":"2026-09-24T20:00:00Z",
 "first_seen":"2026-09-24T13:05:10Z","outlet_count":3,
 "sources":[{"name":"ThinkAdvisor","url":"https://…","published_at":"2026-09-24T10:00:00Z","kind":"feed"},
            {"name":"PR Newswire","url":"https://…","published_at":"2026-09-24T09:30:00Z","kind":"wire"}],
 "firms":[{"name":"Mariner Wealth Advisors","slug":"mariner-wealth-advisors-140195","crd":"140195","verified":true,"city":"Overland Park","state":"KS"}],
 "states":["KS"],"aum_usd":1200000000,"aum_source":"headline","sec_aum_as_of":null,"press_release":true}
```

## `stories.json`

`{schema_version, generated_at, stories[]}`: every article, newest first. Fields: `id`, `cluster_id`,
`title`, `url`, `outlet`, `published_at`, `date_estimated` (bool; true = no date in the source, fetch time
used), `category`, `firm_slugs[]`.

## `digest.json` and `digests/<YYYY-MM-DD>.json`

The Digest / Top Stories view.

| field | type | notes |
|---|---|---|
| `date` | date | local (Pacific) date of the digest |
| `generated_at` | timestamp | |
| `ai` | bool | true = written by Claude and validated. False = plain ranked list (`summary`/`why_it_matters` null) |
| `opener` | string \| null | 2–3 sentence "Today in wealth management" |
| `items[]` | digest item | ranked by outlet count, then recency. The browser moves watchlist hits to the top |
| `more[]` | digest item | further ranked stories not covered by the AI items (digest.json only) |
| `window_start` | timestamp | (digest.json only) |
| `last_good_digest` | `{date, path}` \| null | (digest.json only) the most recent valid AI digest, for "last good digest" |
| `footer_note` | string | (digest.json only) |

Digest item: `{cluster_id, headline, url, category, outlet_count, sources[{name,url}], firms[{name,slug}],
aum_usd, aum_source, summary, why_it_matters}`.

```json
{"schema_version":1,"date":"2026-09-26","generated_at":"2026-09-26T13:07:44Z","ai":true,
 "opener":"Two consolidators closed deals and a large wirehouse team went independent.",
 "items":[{"cluster_id":1841,"headline":"Mariner acquires $1.2B Summit Ridge Advisors","url":"https://…","category":"M&A",
   "outlet_count":3,"sources":[{"name":"ThinkAdvisor","url":"https://…"}],"firms":[{"name":"Mariner Wealth Advisors","slug":"mariner-wealth-advisors-140195"}],
   "aum_usd":1200000000,"aum_source":"headline","summary":"Mariner is buying Summit Ridge Advisors, which manages $1.2 billion.",
   "why_it_matters":"Another mid-sized RIA sale sets a reference point for valuations."}],
 "more":[],"window_start":"2026-09-25T13:05:00Z","last_good_digest":{"date":"2026-09-26","path":"data/digests/2026-09-26.json"},
 "footer_note":"Summaries written with Claude from outlet headlines."}
```

## `digests/index.json`

`{schema_version, generated_at, digests[], weekly[]}`:
- `digests[]`: `{date, generated_at, item_count, path}`, newest first.
- `weekly[]`: `{week, start, end, deal_count, path}`, same as `weekly/index.json`.

## `weekly/index.json` and `weekly/<YYYY-Www>.json`

The index is `{schema_version, generated_at, weekly[]}`. Each recap:

| field | type | notes |
|---|---|---|
| `week` | `"2026-W39"` | ISO week (Mon–Sun, Pacific) |
| `start`, `end` | date | Monday of that week → the Friday the recap was written |
| `deals[]` | M&A row | see `mna.json`; deals dated `start`…`end` (Pacific) |
| `total_disclosed_aum_usd` | number \| null | sum of target AUM over deals whose AUM came from a headline (SEC-reported fallbacks excluded) |
| `disclosed_aum_deals` | int | how many deals contributed to that sum |
| `top_acquirers[]` | `{name, slug, deals}` | most active acquirers this week |
| `paragraph` | string \| null | Claude-written summary; null if unavailable (numbers are always present) |
| `ai` | bool | |

## `mna.json`

`{schema_version, generated_at, sec_aum_as_of, deals[]}`. Each deal:

| field | type | notes |
|---|---|---|
| `cluster_id` | int | |
| `date` | timestamp | |
| `headline` | string | |
| `acquirer`, `target` | `{name, slug, crd}` | `name` null when it can't be determined unambiguously. For `merger`, these are party A / party B |
| `target_aum_usd` | number \| null | |
| `target_aum_source` | `"headline"` \| `"sec"` \| null | |
| `deal_type` | `acquisition` \| `stake` \| `merger` \| `recapitalization` \| null | |
| `confidence` | `"high"` \| `"low"` | low rows are visibly flagged; `note` says why |
| `note` | string | |
| `press_release` | bool | a matching press release raised confidence |
| `sources[]` | `{name, url}` | |

## `firms/index.json` and `firms/<slug>.json`

Only SEC-verified firms mentioned in at least one story get an entry and a page.

- Index: `{schema_version, generated_at, sec_data_date, firms[{slug, name, legal_name, crd, city, state, sec_aum_usd, story_count}]}`.
- Page: `{schema_version, slug, name, legal_name, crd, sec_number, city, state, sec_aum_usd, sec_aum_as_of, iapd_url, stories[], deals[]}`.
  - `stories[]` = `{cluster_id, headline, url, category, last_published, outlet_count, sources[{name,url}]}`.
  - `deals[]` = M&A rows plus `role` (`acquirer` | `target`).
  - `iapd_url` is the firm's public page on adviserinfo.sec.gov.

## `trending.json`

`{schema_version, generated_at, days, firms[{name, slug, crd, verified, stories}]}`: firms ranked by the
number of distinct stories (clusters) mentioning them in the last `days` days. `slug` is null for unverified
firms, which have no page to link to.

## `sources.json`

`{schema_version, generated_at, sources[]}`. Each source has:
- `name`, `kind` (`feed` | `wire` | `google_news`), `homepage`, `enabled`, `ok`
- `method` (`RSS` | `discovered RSS` | `listing fallback` | `Google News RSS` | `failed` | `disabled`)
- `url_used`, `items_last_run`, `new_last_run`
- `dropped_last_run`: items the wealth-management filter removed (wires)
- `reason`, `last_run_at`

## Watchlist (not in the data)

The watchlist is browser-only: `localStorage["fw-watchlist"]` = `{"version":1,"firms":[{"name":"…","aliases":["…"]}]}`
(the theme is `localStorage["fw-theme"]`). Keys from the project's earlier names (`ww-watchlist`; `fd-theme`,
`ww-theme`) are copied to the new keys once, only when the new key is empty, and then removed. Import and export
use the same JSON. Matching happens client-side against:
- `clusters[].headline`, case-insensitive on word boundaries, with aliases of 3+ characters;
- `clusters[].firms[].crd` of any SEC firm (from `firms/index.json`) whose name or legal name starts with a
  watchlist term.
