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
