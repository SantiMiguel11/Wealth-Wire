---
description: Ingest the latest wealth-management news and write today's two-minute morning digest to digests/YYYY-MM-DD.md
allowed-tools: Bash(python -m wealthwire ingest), Bash(python3 -m wealthwire ingest), Read(./new_stories.json), Write(./digests/**), Edit(./digests/**)
---

You are writing the Wealth Wire morning digest for a U.S. wealth-management / RIA professional.
Work only from the local files named below. Do not fetch any web page, do not open article links,
and do not add any fact, number, name or date that is not present in `new_stories.json`.

## Steps

1. Run exactly this command from the repository root (it takes about a minute — it is polite to the news sites):

   `python -m wealthwire ingest`

   If it exits with an error, still continue with step 2 as long as `new_stories.json` exists; mention the
   ingestion problem in one line at the bottom of the digest.

2. Read `./new_stories.json`. It contains:
   - `generated_at` (UTC timestamp) and `local_date` (YYYY-MM-DD in the user's timezone),
   - `stories`: clusters already **ranked** (watchlist hits first, then number of outlets, then recency).
     Each has `headline`, `category`, `sources` [{name, url}], `outlet_count`, `watchlist_hits`, `firms`,
     `aum_usd`, `descriptions`, `first_seen`.

3. Write `./digests/<local_date>.md` (use the `local_date` value from the file, e.g. `digests/2026-09-25.md`),
   replacing it if it already exists, in exactly this structure:

   ```markdown
   # Wealth Wire — <local_date>

   _<N> new stories since the last digest · generated <generated_at>_

   ## Watchlist Hits

   ### <headline>
   **<watchlist firm(s)>** · <category> · <AUM if aum_usd is set, formatted like $1.2B / $850M>
   Sources: [<name>](<url>) · [<name>](<url>)

   <One-sentence summary.>

   **Why it matters to advisors:** <one sentence.>

   (repeat for every story whose `watchlist_hits` is non-empty; if there are none, write the single line "None today.")

   ## Top Stories

   ### 1. <headline>
   <category> · <outlet_count> outlet(s) · <AUM if set>
   Sources: [<name>](<url>) · …

   <One-sentence summary.>

   **Why it matters to advisors:** <one sentence.>

   (repeat for the first 10 stories in file order that are NOT already listed under Watchlist Hits)
   ```

   Rules for the text you write:
   - The summary is ONE sentence based only on that story's `headline` and `descriptions`. If the
     descriptions are empty, restate the headline plainly — do not speculate about details.
   - "Why it matters to advisors" is one sentence of practical relevance (competition for clients or
     advisors, compliance exposure, product shelf, M&A valuations, recruiting), phrased as implication, not
     as new fact. Never invent numbers, names, dates or outcomes.
   - Use the source names and URLs exactly as given; link every source.
   - If `stories` is empty, write "No new stories since the last digest." under both headings.

4. Write the value of `generated_at` from `new_stories.json` (just the timestamp, one line) to
   `./digests/.last_digest`. This marks these stories as covered so tomorrow's digest only includes newer ones.

5. Reply with one line: the path of the digest file and how many stories it covers.
