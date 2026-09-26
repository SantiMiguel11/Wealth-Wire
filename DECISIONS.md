# Decisions log

Each entry: **decision** — alternatives considered — why.

## Environment

1. **Live sources were unreachable from the build environment; everything was developed against fixture feeds.**
   Every news host (wealthmanagement.com, thinkadvisor.com, sec.gov, finra.org, …) returned
   `ProxyError: 403 Forbidden` from the sandbox's egress proxy (pypi.org worked). Alternatives: stop and ask
   (the brief says don't), or fake live results (dishonest). Chosen: build the real network path in full,
   run it live once so SOURCES.md records the actual failure reason, and develop/test/screenshot with an
   offline fixture mode (`python -m wealthwire ingest --fixtures tests/fixtures/demo`) that routes the
   same code path through an `httpx.MockTransport`. On a normal machine `./run.sh` hits the real sites.
2. **Headline pairs for clustering were written by hand instead of harvested from ingestion**, because of #1.
   They follow the headline styles of the seeded outlets (sentence case vs. title case, "| Outlet" suffixes,
   "$1.2B" vs "$1.2 billion"), and use fictional firm names so no fixture reads as a real news claim.
   Fixture feeds carry a "synthetic test data" note, and the UI shows a DEMO banner when the DB was filled
   from fixtures.

## Ingestion

3. **Contact email ships as the placeholder `me@example.com`** in config.yaml. Alternatives: the account
   email of whoever ran the build. Why: the UA is sent to every site; the user should choose what to expose.
   The ingest log and SOURCES.md warn while the placeholder is in place.
4. **Known feed URLs are pre-filled where the platform pattern is well established** (WordPress `/feed/`
   for ThinkAdvisor, Kitces, AdvisorHub; SEC's `pressreleases.rss`; Arizent's `?rss=true` for Financial
   Planning). Others are blank so discovery runs. If a configured feed fails, discovery still runs, so a
   wrong guess degrades to "discovered RSS" rather than "failed".
5. **robots.txt is checked for every fetch that is not a configured or previously-discovered feed URL** —
   homepage/news page for autodiscovery, common-path probes (`/feed`, `/rss`, `/rss.xml`), and listing
   pages. Robots 401/403 ⇒ treat as disallow-all, 404 ⇒ allow-all (stdlib robotparser semantics).
6. **Discovered feed URLs are cached in `source_status`** so later runs go straight to the feed (and get
   conditional GET) instead of re-crawling the homepage every 2 hours.
7. **Canonical URL** = lowercase scheme/host, default port dropped, fragment dropped, `utm_*`, `fbclid`,
   `gclid` plus a few other pure trackers (`mc_cid`, `mc_eid`, `_hsenc`, `_hsmi`, `cmpid`, `sr_share`)
   removed, remaining query params sorted, trailing slash removed. `www.` is *not* stripped (not asked,
   and some hosts serve different sites). Scheme is not upgraded.
8. **Descriptions are cut at a word boundary to ≤300 characters including the ellipsis**, after stripping
   HTML and WordPress "The post … appeared first on …" boilerplate. Enforced twice: in code and by a
   `CHECK(length(description) <= 300)` constraint.
9. **feedparser copies `content:encoded` into `summary` when an item has no `<description>`.** Such
   summaries are detected (summary identical to a content value) and discarded, so descriptions only
   ever come from description/summary elements.
10. **Only AdvisorHub is marked gated.** Other outlets have metered/registration walls on some articles,
    but their RSS teaser descriptions are published openly by the publisher. Any source can be flipped
    with `gated: true`.
11. **Missing dates** (listing pages without a machine-readable date) fall back to `fetched_at`, flagged
    `published_estimated=1`. Naive listing dates are interpreted in the configured timezone. Dates more
    than a day in the future are clamped to `fetched_at`.
12. **Retries**: one retry after 2s (doubling backoff base) for connect/read errors, 429 and 5xx.
    4xx other than 429 are not retried.

## Derived data

13. **Derived data is fully recomputed after every ingestion** rather than incrementally.
    Alternative: incremental clustering. Why: tiny corpus, deterministic output, and rule/config edits
    apply retroactively. Cluster id = smallest item id in the cluster, so ids are stable as clusters grow.
14. **Categories use ordered rules with `unless` guards** in categories.yaml: strong M&A verbs first, but
    skipped when the headline also carries advisor-move language ("team", "joins", "breaks away", "hires");
    then People Moves; then weak M&A words ("deal", "sale", "stake"); then Regulation, Wealthtech,
    Products & Funds, Markets; else Other. First match wins. Category of a cluster = category of its
    headline (earliest) item, falling back to the most common non-Other category among its items.
15. **Clustering** = union-find over pairs from *different* sources within 72h. Score = 0.6·token_set_ratio
    + 0.4·token_sort_ratio on normalized titles (source suffix, stopwords, punctuation removed; money
    canonicalized so "$1.2B" = "$1.2 billion"; headline-verb synonyms like buys/acquires/scoops up unified),
    then evidence: +12 identical firm sets, +4 shared firm with extras on one side, −20 when both sides name
    a firm the other lacks (same acquirer, different targets), −10 no firm in common, ±10 shared/conflicting
    AUM, +8 identical first three tokens, −30 conflicting plain numbers (recurring columns), −8 different
    categories, capped at 50 with fewer than 2 shared tokens. Threshold 70: in the pair fixtures matches score
    ≥70.3 and non-matches ≤67.8. Pure token_set_ratio scored 100 for any short headline whose words were a
    subset of a long one, which over-merged. Known limitation (in the fixture file, not asserted): two teams
    with identical AUM joining the same firm differ by one proper noun and would merge.
16. **AUM requires a `$`** and asset context nearby ("with", "managing", "RIA", "team", "in assets",
    "AUM", …); dollar figures next to "fine", "penalty", "pay", "raises", "fund", "for" are not AUM.
    Alternative: treat every dollar figure as AUM — that turned SEC fines into AUM.
17. **Firm extraction** takes capitalized spans broken at headline verbs/prepositions (needed for Title
    Case headlines), trims descriptors, and keeps spans containing a firm word plus at least one
    non-generic word. Spans made only of firm words ("Wealth Management", "Private Capital") are dropped.
    False positives go in `firm_stoplist.yaml`.
18. **M&A confidence is two-level (high / low).** High = a pattern matched and both parties are clean
    proper-noun spans. Everything else is low with blanks rather than guesses. Mergers of equals are
    stored with `deal_type=merger` and shown as "A ⇄ B". M&A-category clusters with no matching pattern
    still get a (low, blank) row so nothing is silently dropped. Target AUM is only taken from a figure
    attached to the target (prefix "$1.2B RIA X", appositive "X, a $1.2B firm", "X with $1.2B", "X ($1.2B)");
    prices ("for $50M") and combined figures ("to form $5B firm") are ignored.
18a. **"AUM can't be determined" means ambiguous, not absent.** A headline that states no AUM keeps a blank
    AUM and can still be high confidence (most deal headlines omit it). A headline with a dollar figure that
    can't be attached to the target — "acquires Texas RIA in $2.4B deal" (AUM or price?) — forces low.
    Multiple targets ("buys X and Y", "buys X, Y") blank the target and force low. When several outlets'
    headlines agree on both parties, one that states the target's AUM fills it in; disagreement on parties → low.
    Only M&A-category clusters get rows, so advisor moves ("team joins X") never appear in the tracker.

19. **Watchlist matches** are computed at query time from watchlist.yaml, so UI edits apply instantly.
    Aliases shorter than 3 characters are ignored. Possessives ("Goldman's") match.
    Known limitation: a person surnamed Goldman also matches the "Goldman" alias the user asked for.
20. **Pinned block** = watchlist clusters from the last 7 days that also satisfy the active filters (max 10);
    they are removed from the main list below to avoid duplicates. The "Watchlist only" filter shows all.

## Digest

21. **"New" cluster = first fetched after `.last_digest`** (fallback 24h), and additionally published within
    72h before that window start, so the first-ever run doesn't drag weeks of feed backfill into the digest.
22. **The /digest command writes `.last_digest` = `generated_at` from new_stories.json**, not "now", so
    anything ingested between the command's ingest and its write is not skipped next time.
23. **Local date for the digest filename is written into new_stories.json (`local_date`)** so the command
    needs no `date` shell permission.
24. **`python -m wealthwire` re-executes itself under `./.venv/bin/python`** when imported by an interpreter
    that lacks the dependencies. That lets the settings allow exactly `python -m wealthwire ingest` while the
    scheduled task works regardless of which `python` is on PATH.
25. **Generated files are git-ignored**: `data/`, `new_stories.json`, `digests/*.md`, `digests/.last_digest`,
    `.venv/`. SOURCES.md and screenshots are committed as documentation.

## UI

26. Vanilla JS with `fetch`; URL is the single source of truth for filter state (`history.pushState` +
    `popstate`). Theme: `data-theme` on `<html>`, initial value from localStorage or system preference.
27. Date filters are interpreted as local calendar days in the browser and sent as UTC bounds.
28. **Feed order = most recent activity** (a cluster's latest item), while the card shows when the story was
    first reported and the headline of the earliest item. A story that breaks Monday and gets new coverage
    Tuesday moves back up. Alternative: first-reported order, which buries developing stories.
29. **Outgoing links drop tracking params and fragments** (`#comments`, `fbclid`, `utm_*`) but otherwise keep
    the URL exactly as published. The fully canonicalized URL (lowercase host, no trailing slash) is only for
    dedupe, because some servers treat the trailing slash as significant.
30. **`/digest` permissions are declared twice**: in `.claude/settings.json` and in the command's
    `allowed-tools` frontmatter, with the same five narrow rules. A headless test showed Claude Code ignores
    project settings until the folder is trusted, while command frontmatter still applies. The command text
    also forbids any other shell command (a first headless run tried an unneeded `mkdir`, which was denied).
    The second run had 0 denials.
31. **Watchlist firms absorb longer extracted names that start with them** ("Goldman Sachs Asset Management"
    → Goldman Sachs, "Pugh Capital Management" → Pugh Capital), so Trending Firms counts each watched firm once.
32. **Search uses the FTS5 porter stemmer**, so "custody" also finds "custodian(s)". Better recall for news
    search; exact phrases can be narrowed with more words.

## Phase 2

P1. **Build order differs from the brief's numbering.** Every feature publishes through the data contract,
    so §7 (state round trip) and §9 (data files + schemas + frontend split) came first, then §1, §3, §4, §5+§6,
    §2+§8. Each section is still its own commit. See PLAN-PHASE2.md.
P2. **The FastAPI JSON API is gone; the frontend reads only `/data/*.json`.** The brief makes the static files
    the only interface. `python -m wealthwire serve` now builds the static site and serves it with the same
    `/firm/<slug>` fallback Vercel uses. That keeps local preview identical to production. `run.sh` still works.
P3. **The refresh is a sequence of CLI steps** (`state fetch/restore`, `ingest`, `digest-input`,
    `digest-finalize`, `build-site`, `alert`, `publish`) instead of shell in the workflow, so the round trip is
    unit-tested (`tests/test_state.py` pushes to a real bare git remote twice and checks no data loss and a
    single orphan commit).
P4. **The DB is copied with SQLite's backup API**, not a file copy. The DB runs in WAL mode, so a plain copy
    can miss the newest writes.
P5. **"Previous successful refresh" is recorded by `build-site` just before state is saved.** If publishing
    fails, the old state (with the old marker) stays on `live`, so the next run's window still starts at the
    last refresh that actually went out.
P6. **Schemas are strict** (`additionalProperties: false`, required fields, typed nulls), and the test suite
    enforces them. At build time, contract drift only logs a warning instead of blocking the refresh; the tests
    are the gate. `category` is a free string (not an enum) because `categories.yaml` is user-editable.
P7. **The public site excludes `site.exclude_sources` (AdvisorHub) everywhere**: clusters, M&A sources,
    sources.json. Clusters made only of excluded items are dropped.
P8. **The cron schedule is anchored to Pacific Daylight Time** (the season when this was built), at minute :07.
    In Pacific Standard Time, every run lands one hour earlier in local terms. That's documented in the
    workflow and asserted by `tests/test_schedule.py`, which expands the crons for a July week and a January
    week. The 17:00 weekday run is `0 * * 2-6` UTC because 17:00 PDT is already the next UTC day.
P9. **Top Stories window = max(24h, time since the previous successful refresh).** After a missed or failed
    run it grows to cover the gap. Clusters also need activity within 48h before the window start, so a newly
    added source's backlog (first seen now, published weeks ago) doesn't flood Top Stories.
P10. **Concurrency uses `cancel-in-progress: false`.** A queued run waits rather than killing a run
    mid-publish.
P11. **The privacy check runs inside every build and fails closed.** No `.db`/`.sqlite`/WAL file or SQLite
     header may appear under `site/`, and no stored publisher teaser (40+ chars, compared raw and
     JSON-decoded) may appear in any public file. A teaser that is just a copy of its own headline is not
     treated as private. If the check fails, nothing is published; that's the right trade for a leak.
P12. **The watchlist is browser-only** (`localStorage["ww-watchlist"]`, import/export in the same JSON format).
     The server-side `watchlist.yaml` and its alias roll-up in firm extraction are gone. The file is
     git-ignored so it can't be re-committed by accident. Matching on the site: headline regex
     (case-insensitive, word boundaries, 3+ char terms), plus the CRDs of any SEC firm whose name or legal
     name starts with a watchlist term, so "Goldman Sachs" also catches stories tagged with Goldman Sachs'
     SEC entity.
P13. **SEC data source and cadence.** The monthly "Investment Adviser Information Reports" zip is found by parsing
     the SEC page for `ia*.zip` links (exempt-reporting `era*` files skipped) and dating each file from its
     name (MMDDYY). The page is checked at most every 25 days, and the zip is downloaded only when it's newer
     than the loaded one. Every request goes through the same polite fetcher (UA with contact email, ≥2s per
     host, robots.txt). Only `801-` (SEC-registered) rows are kept. A file that parses to fewer than 100
     advisers is rejected, keeping the previous data, since a real month has ~15k.
     Header names are matched loosely, and CSV/XLSX are both handled, because the exact column labels weren't
     verifiable from the build sandbox.
P14. **Firm matching guards** (the brief's "Summit/Focus/Pinnacle/Mercer" rule):
     - a single-word alias matches alone only if it's distinctive: not in the `english-words` web2 dictionary,
       3+ letters, and capitalized in the headline;
     - multi-word aliases made only of dictionary/generic words must appear Title Cased;
     - aliases made only of generic words are never used;
     - an alias shared by unrelated firms is dropped, unless it is some firm's full name or a proper-noun brand
       ("goldman sachs", "raymond james" → the largest registration by AUM);
     - matches never cross sentence punctuation, and the longest match wins.
     Result on 75 real labeled headlines, fixture dictionary: precision 0.95 / recall 0.86 with curated aliases,
     0.96 / 0.71 generated-only. Real-SEC-data numbers come from `eval-firms` in the workflow.
P15. **`firm_aliases.yaml`: a short, user-editable list of brand aliases** (Vanguard, Merrill, BofA, JPMorgan,
     Schwab, …) mapped to SEC names and resolved to CRDs each refresh. These brands dominate headlines but are
     dictionary words or don't match the registered name. Curated aliases only match when capitalized, and
     unresolved names are reported. P/R is reported with and without them, so the list can't hide weak
     automatic matching.
P16. **SEC AUM is attached to a story only through its subject.** It applies when no headline states an AUM and
     the headlines agree on one verified firm that opens the headline (after an optional "People Moves:"
     label). "Coldstream hires former Kestrel Advisors CIO" is about Coldstream, so Kestrel's AUM never shows.
     It is labeled "SEC-reported AUM (as of <file date>)".
P17. **Firm identity for clustering is now the CRD** when verified. Identical firm sets get the +12 bonus only if
     the categories also match. "Northgate and Pinecrest merge" and "Pinecrest names CEO ahead of Northgate
     merger" name the same two firms but are different stories.
P18. **The demo SEC file is synthetic** (fictional firms, fake CRDs 9990xx, plus look-alike distractors). Its
     IAPD links point at non-existent CRDs, and the DEMO DATA badge is shown.
