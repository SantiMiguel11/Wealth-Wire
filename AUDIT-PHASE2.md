# Phase 2 audit

> **Name history.** This project was called Wealth Wire, then Fiduciary Duty (the 2026-09-27 redesign), and is now
> **Fiduciary Wire**. On 2026-09-27 the names, commands and paths in this file were updated to the current ones so
> they still work; RENAME.md lists what changed and what deliberately keeps an old name.

State on 2026-09-27. Verified with:
- the test suite: 334 tests, network mocked, all passing;
- a local refresh on the offline fixtures;
- a Playwright pass of every view (52 screenshots, `screenshots/`);
- two real GitHub Actions runs on `main`: a push run and a `workflow_dispatch` run
  ([runs](https://github.com/SantiMiguel11/Wealth-Wire/actions/workflows/refresh-site.yml)). Both succeeded.

Legend: ✅ pass · ⚠️ pass with a caveat · ⏸ built and tested offline, not yet exercised live because it
needs a secret you haven't added.

## Per section

| § | Requirement | Result | Evidence / notes |
|---|---|---|---|
| 1 | Weekday ~6/12/17 PT, weekend ~8 PT; UTC crons, DST drift documented | ✅ | `refresh-site.yml` comments; `test_schedule.py` expands the crons for a July and a January week |
| 1 | `workflow_dispatch` kept, concurrency group | ✅ | the dispatch run queued behind the push run and never overlapped it |
| 1 | Top Stories = first seen since previous successful refresh, min 24h; old 4-day window removed | ✅ | `window.py`; `test_schedule.py` |
| 2 | Claude writes the digest via `anthropics/claude-code-action` (OAuth token preferred, API key fallback) | ⏸ | step is present and skipped with a notice (no secret yet). File tools only; no shell or web. |
| 2 | `digest_input.json`: top 15, ranked by outlets then recency, with teasers | ✅ | `test_input_is_top_15_ranked_with_teasers` |
| 2 | Output `digests/DATE.md` + `digest.json` (summary, why it matters, 2–3 sentence opener) | ✅ | demo digest in the screenshots went through the real validator |
| 2 | Validation (JSON, real cluster ids, rules) with fallback to the ranked list + last good date | ✅ | 11 rejection cases and 3 fallback cases tested. The validator also caught me copying a teaser while writing the demo digest. |
| 2 | Archive page, footer note | ✅ | `archive-*.png`, footer on every view |
| 3 | DB and teasers never in deployed output; build test | ✅ | `privacy_check` runs on every build and fails it. Live `site/` has no DB; the DB is only in `state/`, outside Vercel's output folder. |
| 3 | Public JSON limited to the allowed fields | ✅ | strict JSON Schemas (`additionalProperties: false`) validated by tests |
| 3 | watchlist.yaml removed; browser-only watchlist with import/export, word-boundary, aliases, SEC names, highlight, pin, re-rank | ✅ | Playwright: add, pin, export (file checked), remove, import |
| 3 | noindex: meta, robots.txt, X-Robots-Tag | ✅ | `test_site.py` |
| 3 | Private repo recommendation; Vercel works with private repos | ✅ | MANUAL-STEPS.md §1 |
| 4 | Monthly SEC download at most once a month, fair access | ✅ | live: `cached — file dated 2026-09-01, 17149 SEC-registered advisers` |
| 4 | Firms table fields | ✅ | `sec_firms` |
| 4 | Aho-Corasick with precision guards; regex fallback unverified | ✅ | see firm matching below |
| 4 | 60+ real headline eval with P/R | ✅ | 75 headlines, results below |
| 4 | SEC AUM fallback labeled with date | ✅ | "SEC-reported AUM (as of 2026-09-01)" |
| 4 | Region filter (Pacific NW = WA/OR/ID) + state | ✅ | `region-*.png` |
| 4 | Firm pages `/firm/<slug>` with IAPD link, stories, M&A; Trending links to them | ✅ | `firm-*.png`. Trending now lists only SEC-verified firms. |
| 5 | Business Wire, PR Newswire, GlobeNewswire; SOURCES.md | ⚠️ | PR Newswire and GlobeNewswire OK. The Business Wire feed URL returns an empty feed (see sources). |
| 5 | Wealth filter + dropped counts | ✅ | live: 20/20 dropped for both wires (no wealth news in them that run) |
| 5 | Press release clusters with trade coverage, raises M&A confidence | ✅ | fixture test: Crestline row → high, "raised by a matching press release" |
| 6 | Google News RSS for ThinkAdvisor, FA Magazine, Citywire; suffix stripped; dedupe; no redirect resolution | ⚠️ | Works on fixtures. Live, Google returns **HTTP 503 to GitHub's runners**. Not worked around, per the spec. |
| 7 | `live` = one orphan commit, force-pushed; state round trip | ✅ | `test_state.py` (bare remote); the second live run restored the first run's DB (SEC data "cached") |
| 7 | `main` = source only | ✅ | |
| 8 | Friday weekly M&A recap with Claude paragraph + fallback, linked from archive | ✅ / ⏸ | numbers-only recap tested; the Claude paragraph is waiting on the secret |
| 8 | Watchlist email via Resend, only with all three secrets; nothing when no matches | ⏸ | tested with a mocked sender. Live run: skipped with a notice. |
| 8 | Secret watchlist never written anywhere (test) | ✅ | `test_secret_watchlist_is_never_written_anywhere` scans every file after a full refresh, plus stdout/stderr |
| 9 | Static JSON under /data, DATA-CONTRACT.md, schemas validated by a test | ✅ | |
| 9 | Frontend reads only /data; one folder; "Replacing the frontend" | ✅ | `test_frontend_reads_only_static_data`; README |

## Firm matching (§4)

75 real headlines with 67 labeled firm mentions and 23 headlines with no firm.

| Dictionary | Aliases | Precision | Recall |
|---|---|---:|---:|
| **Real SEC file** (2026-09-01, 17,149 advisers) | generated + curated | **0.984** | **0.925** |
| Real SEC file | generated only | 0.909 | 0.597 |
| Test fixture dictionary (66 firms + distractors) | generated + curated | 0.968 | 0.910 |
| Test fixture dictionary | generated only | 0.957 | 0.657 |

The first live run measured 0.828 / 0.791 on the real file. Its mistakes were:
- surnames ("Commissioner Peirce");
- places ("Wisconsin", "Long Island", "Wall Street");
- "M&A" matching "M & A Consulting";
- inflected words ("Members");
- missing brands.

The fixes are in DECISIONS P29. The refresh workflow recomputes these numbers against the current SEC file
on every run, and the report is kept in `state/firm_eval.json` on the `live` branch.

Remaining known errors:
- Missed:
  - Prudential and American Portfolios (not SEC-registered advisers under those names);
  - RBC (registered name not checked);
  - "Horizon" (ambiguous).
- Wrong: "Luma", a fintech that shares its name with Luma Capital.

## Sources (live run, 2026-09-27 00:02 UTC)

| Source | Method | Status |
|---|---|---|
| WealthManagement.com | RSS | ✅ 50 items |
| InvestmentNews | discovered RSS | ✅ 93 items |
| RIABiz | discovered RSS | ✅ (304 not modified) |
| Financial Planning | RSS | ✅ 10 items |
| AdvisorHub | RSS, headline only | ✅ (304). Stored, excluded from the public site. |
| Kitces | RSS | ✅ (304) |
| SEC Press Releases | RSS | ✅ 25 items |
| FINRA News | discovered RSS | ✅ (304) |
| PR Newswire | RSS (wire) | ✅ 20 fetched, 0 kept by the wealth filter |
| GlobeNewswire | RSS (wire) | ✅ 20 fetched, 0 kept by the wealth filter |
| Business Wire | RSS (wire) | ❌ feed URL returns an empty feed |
| ThinkAdvisor | Google News RSS | ❌ HTTP 503 from Google to GitHub runners |
| Financial Advisor Magazine | Google News RSS | ❌ HTTP 503 |
| Citywire RIA | Google News RSS | ❌ HTTP 503 |
| SEC adviser data | monthly zip | ✅ 17,149 advisers, file dated 2026-09-01 |

Per-source status is regenerated on every run in `state/SOURCES.md`, and shown on the Sources tab.

## UI check (Playwright)

The run covered:
- 13 views × 1440/390 widths × light/dark (52 screenshots): feed, filtered feed, region, search, watchlist,
  firm page, M&A, low-confidence M&A, digest, archive, weekly, sources, empty;
- the error state;
- interactions: search, category, back button, region, clear, watchlist add/pin/export/remove/import, and the
  theme toggle.

Final run: 0 console errors, 0 failed requests, no horizontal overflow.

Fixed during review:
1. **`app.js` had a syntax error** (an extra `)` in the M&A table), so the whole frontend failed to run. A
   `node --check` test now guards it.
2. Trending Firms showed an unverified regex match ("Boise Office").
3. The weekly recap table was squeezed into the narrow digest column.
4. The digest footer note was duplicated.
5. The "Morning digest" label was stale under a 3×-daily schedule.

## Not verified live

- **The Claude step.** It can't run until you add `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`
  (MANUAL-STEPS §2). The action inputs follow its v1 documentation, but the first real run is the true test.
  If it fails, the refresh still succeeds and the site shows the ranked list.
- **The Resend email.** It needs three secrets (MANUAL-STEPS §3).
- **A local end-to-end refresh against the real sources.** This build sandbox's network blocks every news
  host and sec.gov (HTTP 403 at the proxy), so the local "real" run failed all 14 sources. That confirmed the
  total-failure path is handled: the site builds, and the privacy and contract checks pass. The real
  end-to-end runs are the two GitHub Actions runs above.

---

# Follow-ups (2026-09-27)

## 1. Honest firm-matching evaluation

**Held-out set A:** `tests/fixtures/firm_headlines_heldout.yaml`.
- 162 real headlines from the live site's refreshes of 2026-09-26/27, excluding every headline in the
  original test set.
- 50 labeled firm mentions; 127 headlines name no adviser.
- Labeled by hand under one rule: a mention counts only if the named organization has an SEC-registered
  adviser under that brand in the real SEC file, checked row by row (DECISIONS F1).

| | Precision | Recall | TP / FP / FN |
|---|---:|---:|---:|
| **Held-out A, logic as deployed (`a6a9741`), before any change — the real score** | **0.957** | **0.900** | 45 / 2 / 5 |
| Held-out A, generated aliases only (same logic) | 0.933 | 0.560 | |
| Held-out A after the fixes (in-sample: the fixes were made on this set) | 1.000 | 0.980 | 49 / 0 / 1 |
| Original 75-headline set after the fixes | 0.984 | 0.940 | 63 / 1 / 4 |

**Caveat on the 0.957.** It is biased upward. On 2026-09-27 I inspected the matcher's output over this same
corpus while tuning (fixing false positives such as "Members", "Focused" and "Frazier") before this set was
built. Recall wasn't tuned on it.

**Blind set B.** A truly blind score needs headlines first fetched after the tuning commit. When the set was
built, only 6 such headlines existed. Set B will be labeled and scored the same way, without changing the
logic first, once 75 or more new headlines have accumulated from the scheduled refreshes. It will be
reported here.

Pre-fix errors on set A, and what was done:

| Headline | Error | Fix |
|---|---|---|
| Concurrent adds $425 million Houston team… | missed Concurrent (dictionary word) | subject rule (F3) |
| EQT raises Perpetual takeover bid… | missed EQT (3-letter acronym) | subject rule (F3) |
| Bain Capital (mostly) funds Envestnet buy of Vestmark… | missed Bain Capital and Orion | curated aliases (verified SEC names) |
| …Prior Problematic Financial Decisions: Kitces & Carl | "Financial Decisions" false positive | stoplist now applies to SEC aliases |
| FINRA Fines Pictet Overseas and Blue Ocean ATS… | "Blue Ocean Capital" false positive | word-only alias followed by an ALL-CAPS token is a different name |
| Ritik Malhotra sells not-for-sale Savvy stake… | missed Savvy | **not fixed**: a curated "Savvy" would fire on "How Savvy Advisors…" |

Across all 235 real headlines, the fixes changed exactly 6 results, all corrections. That includes one
old-set miss fixed as a side effect ("Advisor moves: RBC lands…").

**Regression test.** `tests/test_firms_real.py` runs both sets against
`tests/fixtures/sec_firms_real_subset.csv`, the 594 real SEC registrants needed to reproduce full-file
matching exactly. `scripts/build_eval_dictionary.py` verifies that equality when it rebuilds the slice.

## 2 and 3. Press-release wires, verified from GitHub's network

The build sandbox can't reach these hosts, so every candidate feed was checked with
`.github/workflows/probe-feeds.yml`, run through `workflow_dispatch` via the GitHub API. `gh` isn't installed
here, but it's the same event.

| Wire | Result | Evidence |
|---|---|---|
| GlobeNewswire | **Fixed: 4 keyword feeds** (registered investment advisor · wealth management · RIA · family office) | Probe run 36286878218: 20 items each; the filter kept 12 / 10 / 12 / 11. **Live refresh run 36287163800: 80 fetched, 7 kept, 4 unique new stories stored** (Meristead Wealth launch, Wedbush hire, Callan Family Office appointment, AssetMark research). |
| PR Newswire | **Disabled.** No keyword-scoped feed exists. | Probe runs 36286878218 and 36286976221: every financial-services subject slug either returns the all-news firehose or is off-topic (banking 0 kept, M&A 1 irrelevant). |
| Business Wire | **Removed.** | `feed.businesswire.com/robots.txt` disallows `/rss/home/`; `businesswire.com/robots.txt` returns 403. Wire feeds are now robots-checked. |

**Also new:**
- award/ranking releases are dropped from wires;
- `wire_stats.csv` (in `state/` on `live`) gets one row per wire feed per run: fetched, too old, dropped by
  the filter, kept, and new. The first rows are from run 36287163800. Each run's summary prints its rows.

## 4. First live Claude digest

**Not yet run.** No `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` secret exists in the repository. In
every run so far (including 36286484901 and 36287163800), "Write the digest with Claude" was **skipped** and
the "No Claude secret" notice ran. So there is no Claude output or validator result to paste yet. Once a
secret is added (MANUAL-STEPS §2), the next scheduled or manual run will produce it, and it will be recorded
here with the validator's verdict.

# Fiduciary Wire redesign (2026-09-27)

- **Scope:** frontend only, per the brief (`frontend/`, design reference in `design/`); DECISIONS R1–R7.
- **Playwright:** 14 views × 1440/390 × light/dark (56 screenshots) plus interaction runs. Result: 0 console
  errors, 0 failed requests, no horizontal scroll at 390 px, and every tap target is 44 px or taller at 390 px.
- **Interactions checked:** search, category, back button, region, clear filters, `/` shortcut, deals sort
  (`aria-sort`), watchlist add/pin/export/remove/import, drawer focus trap and Esc, `ww-theme` → `fd-theme`
  migration, theme persistence, and an error state that names the failed file.
- **Contrast** (computed, WCAG): lowest text pair 5.21:1 (muted on the review-row tint, light theme); every
  category color is at least 6.3:1.
- **Tests:** 354 passed.
