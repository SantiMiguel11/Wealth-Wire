# Acceptance audit

> **Name history.** This project was called Wealth Wire, then Fiduciary Duty (the 2026-09-27 redesign), and is now
> **Fiduciary Wire**. On 2026-09-27 the names, commands and paths in this file were updated to the current ones so
> they still work; RENAME.md lists what changed and what deliberately keeps an old name.

Audited 2026-09-26 against commit `HEAD` of `claude/dreamy-turing-b5xpzl`.
Evidence commands: `python -m pytest` (238 passed), `python scripts/screenshots.py` (36 screenshots,
0 problems), a fresh-clone `./run.sh`, and a headless `claude -p "/digest"`.

**Environment caveat.** The build sandbox's egress proxy refused every news domain with `403 Forbidden`
(pypi.org was reachable). Everything below marked *fixture* ran the real ingestion code path — fetcher,
discovery, robots, parsing, DB, pipeline — against a saved fixture site via `httpx.MockTransport`. It did
not run against the live outlets.

## Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1a | ≥7 sources ingest successfully | **PASS (live)** | First live run on GitHub Actions (2026-09-26): **8/11 sources, 229 real items → 193 stories**. RSS: WealthManagement.com, Financial Planning, AdvisorHub, Kitces, SEC. Discovered RSS: InvestmentNews (`/rss`), RIABiz (`/rss`), FINRA (`/media-center/newsreleases/rss`). Failed, with reasons in SOURCES.md on the `live` branch: ThinkAdvisor and FA Magazine answer HTTP 403 to automated clients from cloud IPs (not circumvented); Citywire has no feed and a JavaScript-rendered listing. The build sandbox itself could not reach any outlet (proxy 403), which is why earlier development used fixtures. |
| 1b | SOURCES.md explains every failure | PASS | Every failed attempt is listed with its exact reason: HTTP status, proxy refusal, `robots.txt disallows /media-center/newsreleases`, "no <link rel=alternate> feed", "listing page had no parseable headlines", gated note. `test_sources_md_written` |
| 2 | Multi-outlet stories appear as one clustered card listing all sources | PASS | 57 fixture items → 35 clusters, exactly the intended stories: the 4-outlet Summit Ridge deal is one card and the Harborview breakaway team is a separate card (`test_demo_clusters`, `test_api_card_lists_all_sources`). 24 should-match and 18 should-not-match headline pairs pass at threshold 70 (`test_should_match`, `test_should_not_match`). Screenshot `feed-desktop-light.png` shows the source chips with per-outlet times. |
| 3 | Search, source/category/date filters, watchlist highlighting + pinning work | PASS | API: `test_search`, `test_source_filter`, `test_date_filter`, `test_pins_respect_filters`, `test_watch_filter`, `test_pinned_and_highlighted`. Browser, in `scripts/screenshots.py`: typing a search updates `?q=`, category chips update `?category=`, the back button restores state, source select → `?source=`, Clear empties the URL, adding a firm in the UI pins its stories and removing it unpins them. Screenshots: `search-*`, `feed-filtered-*`, `watchlist-*`, `watchlist-added-desktop-light.png`. |
| 4 | M&A table populates from real ingested headlines, low-confidence rows flagged | PASS on fixtures · live not verified | Rows come from ingested items through the real pipeline: 11 M&A clusters → 11 rows, 8 high, 3 low (`test_demo_mna_table`). Low rows are tinted, carry a ⚠ LOW chip with the reason visible, and can be filtered with `?conf=low` (`mna-low-*.png`, `test_mna_api_filter`). 18 high-confidence and 6 low-confidence headline cases pass (`tests/test_mna.py`). The headlines are synthetic because of the network block. |
| 5a | Re-running ingestion creates no duplicates | PASS | `test_ingest_twice_inserts_zero_duplicates` (second run inserts 0), `UNIQUE(canonical_url)` (`test_unique_constraint_on_canonical_url`), canonicalization cases in `tests/test_urls.py`. Conditional GET returns 304 on re-run (`test_conditional_get_uses_etag_and_handles_304`). |
| 5b | No full article text is stored | PASS | Only title/url/canonical_url/source/published_at/fetched_at/description are stored, plus derived metadata (`test_no_full_text_stored` checks the column set). Descriptions are ≤300 chars, enforced in code **and** by a DB `CHECK` (`test_description_length_enforced_by_db`). `content:encoded` is ignored, including feedparser's silent copy of it into `summary` (`test_content_encoded_ignored_even_when_feedparser_copies_it`). Gated AdvisorHub stores empty descriptions (`test_gated_source_has_empty_descriptions`). |
| 6a | `./run.sh` works from a fresh clone | PASS | `git clone` into an empty dir → `./run.sh` created `.venv` (python3.13), installed requirements, ran the ingestion (recording the proxy failures), and served `GET /` 200 and `/api/meta` 200 on the chosen port. The same test found and fixed a bug: `python -m fiduciarywire` didn't re-exec into `.venv` when `.venv/bin/python` symlinks to the same interpreter. |
| 6b | `/digest` runs without permission prompts | PASS (with a one-time trust step) | `claude -p "/digest" --permission-mode default` in the fresh clone: exit 0, `permission_denials: []`, wrote `digests/2026-09-25.md` (6 watchlist hits + top 10) and `digests/.last_digest`. All 36 links in the digest appear verbatim in `new_stories.json`. Claude Code ignores `.claude/settings.json` until the folder is trusted; the command's `allowed-tools` frontmatter carries the same narrow allowlist, which is why the untrusted run still needed no prompts (README documents the trust step). |
| 7 | Zero console errors across all Playwright runs | PASS | `scripts/screenshots.py` records console errors, page errors, failed requests, HTTP ≥400 responses and horizontal overflow across 9 scenes × 2 viewports × 2 themes, plus interactions and the theme toggle: **0 problems**. The error-state screenshot uses a deliberately failed request and is excluded from that count. |

## Hard rules

| Rule | Result | Evidence |
|---|---|---|
| No LLM/API calls, keys, embeddings, hosted NLP | PASS | `grep -riE "anthropic\|openai\|api_key\|embedding\|transformers\|spacy\|nltk"` over code and requirements: no matches except the "no embeddings" docstring. Dependencies are exactly the requested stack. |
| Nothing behind login/paywall; gated = headline/link/date/source only | PASS | No auth code anywhere. `gated: true` → `description=""` (parse + tests). |
| RSS first → autodiscovery → common paths → listing fallback | PASS | `SourceIngester.run` order; each step tested on the fixture site. |
| robots.txt before non-feed fetches; skip and record | PASS | `RobotsCache` (urllib.robotparser); FINRA fixture disallow is recorded; `test_robots_disallow_blocks_listing`. An unreachable robots.txt is treated conservatively as "not crawling". |
| UA with contact email; ≥2s/host; 15s timeout; 1 retry w/ backoff; conditional GET | PASS | `config.yaml`; `test_user_agent_sent`, `test_per_host_delay`, `test_retry_once_with_backoff`, `test_no_retry_on_404_and_only_one_retry`, conditional GET test. The placeholder email triggers a warning in SOURCES.md. |
| Dedupe by canonical URL with UNIQUE constraint | PASS | See 5a. |
| Descriptions: HTML stripped, ≤300 chars | PASS | See 5b; `test_strip_html_and_wordpress_boilerplate`, `test_truncate_word_boundary`. |
| Dates normalized to UTC across formats | PASS | `tests/test_dates.py`: RFC-822 offsets, GMT, named zones, Atom `Z`/offset, naive listing dates in the configured tz, missing/future dates. |

## Required tests (brief §Workflow 4)

| Area | File |
|---|---|
| canonicalization + dedupe (ingest twice → 0 new) | `test_urls.py`, `test_ingest.py` |
| no full text (≤300, content:encoded ignored) | `test_ingest.py`, `test_text.py` |
| date parsing across formats/timezones | `test_dates.py` |
| category rules incl. People Moves vs M&A | `test_categorize.py` (36 cases) |
| clustering on fixture pairs | `test_cluster.py` + `tests/fixtures/cluster_pairs.yaml` |
| AUM parsing | `test_extract.py` (17 formats + 15 context cases) |
| M&A extraction incl. low confidence | `test_mna.py` |
| watchlist matching incl. false positives | `test_watchlist.py` (17 cases + API) |
| new_stories.json windowing and ranking | `test_digest.py` |

## Process

- PLAN.md was written before code; DECISIONS.md logs every judgment call (33 entries).
- One commit per feature (1–8), then separate commits for the UI verification pass and fixes.
- Screenshots were reviewed by eye after each pass. Fixed along the way: mobile header overflow (theme
  toggle off-screen), unlabeled mobile date inputs, orphaned Clear button, digest markdown lines running
  together, low-confidence reasons only visible as tooltips, empty mobile table cells, tracking params and
  `#comments` in outgoing links, duplicate firm names in Trending.

## Open items (need a real network)

1. Run `./run.sh` and read `SOURCES.md`. Fix any failing feed URL or `listing_url` in `sources.yaml`.
2. Add real mis-clustered headline pairs to `tests/fixtures/cluster_pairs.yaml`, re-run
   `scripts/tune_cluster.py`, and adjust `cluster.threshold` if needed.
3. Add real firm-extraction false positives to `firm_stoplist.yaml`.
