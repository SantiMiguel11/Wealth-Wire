# Rename inventory: Wealth Wire / Fiduciary Duty → Fiduciary Wire

Step 1 of the rename, written **before any change** (commit `142ff3e`). Search: case-insensitive
`fiduciary[ _-]?duty|wealth[ _-]?wire` over every tracked text file, plus tracked file and directory names. This
covers "Fiduciary Duty", "fiduciary-duty", "fiduciary_duty", "fiduciaryduty", "FiduciaryDuty", "Wealth Wire",
"wealth-wire", "wealth_wire", "wealthwire" and "WealthWire". Binary files (screenshots) are regenerated, not edited.

**254 text hits in 68 files; 31 tracked paths contain an old name.**

Spellings found: `wealthwire` ×170, `Wealth Wire` ×26, `WEALTHWIRE` ×21, `Fiduciary Duty` ×18, `wealth-wire` ×16, `Wealth-Wire` ×5, `WealthWire` ×5, `fiduciary-duty` ×1, `wealth wire` ×1

## Paths containing an old name

- `wealthwire/` (Python package directory, 30 files)
- `design/Fiduciary Wire.dc.html`

## Text hits (file:line)

### `.claude/commands/digest.md` (4)

- 2: `description: Write today's Wealth Wire digest locally, using the same instructions and validation as the refresh workflow`
- 3: `allowed-tools: Bash(python -m wealthwire digest-input), Bash(python -m wealthwire digest-finalize), Read(./prompts/digest.md), Read(./_work/**), Write…`
- 10: `1. Run exactly 'python -m wealthwire digest-input'. It writes '_work/digest_input.json', plus`
- 13: `3. Run exactly 'python -m wealthwire digest-finalize'. It validates what you wrote. If validation fails, it`

### `.claude/settings.json` (2)

- 4: `"Bash(python -m wealthwire digest-input)",`
- 5: `"Bash(python -m wealthwire digest-finalize)",`

### `.github/workflows/probe-feeds.yml` (2)

- 38: `python -m wealthwire state fetch _prev`
- 39: `python -m wealthwire state restore _prev`

### `.github/workflows/refresh-site.yml` (11)

- 22: `- "wealthwire/**"`
- 61: `python -m wealthwire state fetch _prev`
- 62: `python -m wealthwire state restore _prev`
- 65: `run: python -m wealthwire ingest \|\| echo "::warning::no source ingested successfully — see state/SOURCES.md on the live branch"`
- 69: `run: python -m wealthwire digest-input`
- 102: `run: python -m wealthwire digest-finalize \| tee -a "$GITHUB_STEP_SUMMARY"`
- 106: `run: python -m wealthwire eval-firms`
- 109: `run: python -m wealthwire build-site _live`
- 112: `run: python -m wealthwire publish _live --remote-url "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" --message "Refresh $…`
- 118: `run: python -m wealthwire alert`
- 134: `echo "### Wealth Wire refresh"`

### `AUDIT-PHASE2.md` (2)

- 8: `([runs](https://github.com/SantiMiguel11/Wealth-Wire/actions/workflows/refresh-site.yml)). Both succeeded.`
- 201: `# Fiduciary Duty redesign (2026-09-27)`

### `AUDIT.md` (1)

- 23: `\| 6a \| './run.sh' works from a fresh clone \| PASS \| 'git clone' into an empty dir → './run.sh' created '.venv' (python3.13), installed requirement…`

### `DATA-CONTRACT.md` (2)

- 1: `# Wealth Wire data contract`
- 84: `\| 'first_published', 'last_published', 'first_seen' \| timestamp \| 'first_seen' = when Wealth Wire first fetched it \|`

### `DECISIONS.md` (7)

- 12: `offline fixture mode ('python -m wealthwire ingest --fixtures tests/fixtures/demo') that routes the`
- 107: `24. **'python -m wealthwire' re-executes itself under './.venv/bin/python'** when imported by an interpreter`
- 108: `that lacks the dependencies. That lets the settings allow exactly 'python -m wealthwire ingest' while the`
- 140: `the only interface. 'python -m wealthwire serve' now builds the static site and serves it with the same`
- 376: `## Fiduciary Duty redesign (2026-09-27)`
- 378: `R1. **Frontend only.** 'frontend/' was rewritten from 'design/Fiduciary Wire.dc.html'. The pipeline, 'schemas/',`
- 380: `Python package keep the working name "Wealth Wire".`

### `MANUAL-STEPS.md` (10)

- 23: `1. Open https://github.com/SantiMiguel11/Wealth-Wire.`
- 32: `3. Under **Repository access**, make sure either **All repositories** is chosen, or **Wealth-Wire** is in the`
- 50: `2. Open https://github.com/SantiMiguel11/Wealth-Wire/settings/secrets/actions`
- 57: `1. Open https://console.anthropic.com/settings/keys, then click **Create Key**, name it 'wealth-wire', and copy`
- 78: `2. **Create an API key.** In Resend, go to **API Keys** → **Create API Key**, name it 'wealth-wire', choose`
- 80: `3. **Export your watchlist.** On the Wealth Wire site, add your firms in the Watchlist panel, click`
- 81: `**Export JSON**, and open the downloaded 'wealth-wire-watchlist.json' in a text editor. Copy all of it.`
- 92: `- 'SITE_URL': your Vercel URL, e.g. 'https://wealth-wire.vercel.app', adds a link to the email.`
- 93: `- 'ALERT_FROM': e.g. 'Wealth Wire <alerts@yourdomain.com>'. Set this only after verifying a domain in`
- 111: `**GitHub Actions permissions:** open https://github.com/SantiMiguel11/Wealth-Wire/settings/actions.`

### `PLAN-PHASE2.md` (10)

- 1: `# Wealth Wire — Phase 2 plan`
- 5: `- **Pipeline:** 'python -m wealthwire ingest' fetches 11 sources into SQLite and recomputes the derived data`
- 17: `├─ wealthwire/            pipeline (Python)        ├─ site/          ← Vercel serves only this`
- 21: `│   sitebuild.py (emits site/data/*.json)           │   wealthwire.db (items incl. teasers, SEC firms)`
- 34: `\| restore \| 'python -m wealthwire state restore _prev' \| copies DB and archives out of the previous 'live' tree \|`
- 35: `\| ingest \| 'python -m wealthwire ingest' \| includes the monthly SEC check (§4), wires (§5), Google News (§6) \|`
- 36: `\| prepare AI input \| 'python -m wealthwire digest-input' \| writes '_work/digest_input.json'; on Pacific Fridays also '_work/weekly_input.json' \|`
- 38: `\| finalize \| 'python -m wealthwire digest-finalize' \| validates the Claude output → digest archive, or falls back \|`
- 39: `\| build \| 'python -m wealthwire build-site _live' \| writes 'site/data/*.json', copies 'frontend/', runs the privacy check (fails closed) \|`
- 40: `\| alert \| 'python -m wealthwire alert' \| watchlist email; skips quietly when secrets are missing \|`

### `PLAN.md` (4)

- 1: `# Wealth Wire — Plan`
- 12: `┌───────────── ingest (python -m wealthwire ingest / every 2h in server) ─────────────┐`
- 36: `wealthwire/`
- 38: `paths.py        repo root, config dir (WEALTHWIRE_CONFIG), data dir (WEALTHWIRE_HOME)`

### `README.md` (12)

- 1: `# Fiduciary Duty`
- 3: `Daily news for wealth management and RIAs. Fiduciary Duty pulls headlines from trade outlets, SEC and FINRA`
- 12: `the project's working name, Wealth Wire.)`
- 52: `is 'design/Fiduciary Wire.dc.html'.`
- 131: `python -m wealthwire --help               # all commands (ingest, build-site, serve, digest-input, …)`
- 137: `export WEALTHWIRE_HOME=demo WEALTHWIRE_NOW=2026-09-25T18:00:00Z   # fixtures are dated around this instant`
- 138: `python -m wealthwire ingest --fixtures tests/fixtures/demo`
- 139: `python -m wealthwire serve`
- 158: `'frontend/'). Nothing in 'wealthwire/', 'schemas/' or the workflow needs to change.`
- 163: `python -m wealthwire state fetch _prev && python -m wealthwire state restore _prev   # pull the live DB`
- 164: `python -m wealthwire serve            # builds site/data from it and serves http://localhost:8000`
- 177: `python -m wealthwire eval-firms    # firm-matching precision/recall on the 75 labeled headlines`

### `config.yaml` (2)

- 1: `# Wealth Wire runtime configuration.`
- 5: `user_agent: "WealthWire/0.1 (personal news reader; {contact_email})"`

### `design/Fiduciary Wire.dc.html` (4)

- 40: `<sc-if value="{{ wmSerif }}" hint-placeholder-val="{{ true }}"><span style="display:block; font-family:'Cormorant Garamond',serif; font-weight:500; fo…`
- 41: `<sc-if value="{{ wmCaps }}"><span style="display:block; font-family:'Cormorant SC',serif; font-weight:600; font-size:clamp(34px,4.2cqi,62px); line-hei…`
- 42: `<sc-if value="{{ wmCond }}"><span style="display:block; font-family:'Barlow Condensed',sans-serif; font-weight:500; font-size:clamp(36px,4.4cqi,64px);…`
- 374: `<span style="{{ w.markStyle }}">Fiduciary Duty</span>`

### `frontend/app.js` (4)

- 1: `/* Fiduciary Duty frontend — vanilla JS, no build step.`
- 286: `document.title = (TITLES[s.tab] ? TITLES[s.tab] + " · " : "") + "Fiduciary Duty";`
- 583: `document.title = f.name + " · Fiduciary Duty";`
- 819: `const a = el("a", { href: URL.createObjectURL(blob), download: "fiduciary-duty-watchlist.json" });`

### `frontend/index.html` (3)

- 7: `<title>Fiduciary Duty</title>`
- 33: `Fiduciary Duty frontend. Reads ONLY the static JSON files under /data/ (see DATA-CONTRACT.md).`
- 50: `<a class="wordmark" href="/" data-nav>Fiduciary Duty</a>`

### `frontend/style.css` (1)

- 1: `/* Fiduciary Duty — newspaper-style frontend. Tokens first; hairline rules, no cards, no shadows (drawer excepted). */`

### `prompts/digest.md` (2)

- 1: `# Wealth Wire digest instructions`
- 3: `You write the Wealth Wire digest for U.S. wealth-management and RIA professionals. Your source material is`

### `run.sh` (6)

- 2: `# Wealth Wire: create the venv if missing, install requirements, run one ingestion, start the server.`
- 26: `.venv/bin/python -m wealthwire ingest \|\| echo "!! ingestion reported no successful sources — see SOURCES.md. Starting the server anyway."`
- 28: `HOST="${WEALTHWIRE_HOST:-127.0.0.1}"`
- 29: `PORT="${WEALTHWIRE_PORT:-8000}"`
- 30: `echo "→ Wealth Wire at http://localhost:${PORT}  (re-ingests every 2 hours; Ctrl-C to stop)"`
- 31: `exec .venv/bin/python -m wealthwire serve --host "$HOST" --port "$PORT"`

### `schemas/clusters.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/clusters.schema.json",`

### `schemas/digest.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/digest.schema.json",`

### `schemas/digests-index.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/digests-index.schema.json",`

### `schemas/firm.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/firm.schema.json",`

### `schemas/firms-index.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/firms-index.schema.json",`

### `schemas/meta.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/meta.schema.json",`

### `schemas/mna.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/mna.schema.json",`

### `schemas/sources.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/sources.schema.json",`

### `schemas/stories.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/stories.schema.json",`

### `schemas/trending.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/trending.schema.json",`

### `schemas/weekly-index.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/weekly-index.schema.json",`

### `schemas/weekly.schema.json` (1)

- 3: `"$id": "https://wealth-wire/schemas/weekly.schema.json",`

### `scripts/build_eval_dictionary.py` (3)

- 9: `python scripts/build_eval_dictionary.py path/to/wealthwire.db     # e.g. state/wealthwire.db from 'live'`
- 23: `from wealthwire.config import load_stoplist  # noqa: E402`
- 24: `from wealthwire.firms import SecMatcher, aliases_for, load_curated, normalize  # noqa: E402`

### `scripts/make_fixtures.py` (1)

- 311: `from wealthwire.gnews import feed_url as gnews_url`

### `scripts/probe_feeds.py` (8)

- 22: `from wealthwire import db  # noqa: E402`
- 23: `from wealthwire.categorize import Categorizer  # noqa: E402`
- 24: `from wealthwire.config import load_categories, load_config  # noqa: E402`
- 25: `from wealthwire.dates import utcnow  # noqa: E402`
- 26: `from wealthwire.fetch import Fetcher  # noqa: E402`
- 27: `from wealthwire.firms import SecMatcher  # noqa: E402`
- 28: `from wealthwire.parse import parse_feed  # noqa: E402`
- 29: `from wealthwire.wires import WEALTH_TERMS, keep_wire_item  # noqa: E402`

### `scripts/screenshots.py` (4)

- 79: `env = dict(os.environ, WEALTHWIRE_HOME=str(DEMO_HOME), WEALTHWIRE_CONFIG=str(cfg), WEALTHWIRE_NO_BACKGROUND="1",`
- 80: `WEALTHWIRE_NOW=FIXED_NOW)`
- 81: `run = lambda *a: subprocess.run([sys.executable, "-m", "wealthwire", *a], cwd=ROOT, env=env, check=True,  # noqa: E731`
- 93: `proc = subprocess.Popen([sys.executable, "-m", "wealthwire", "serve", "--port", str(port)], cwd=ROOT, env=env,`

### `scripts/tune_cluster.py` (4)

- 8: `from wealthwire.cluster import ClusterItem, score  # noqa: E402`
- 9: `from wealthwire.config import load_stoplist  # noqa: E402`
- 10: `from wealthwire.categorize import Categorizer  # noqa: E402`
- 11: `from wealthwire.extract import extract_firms  # noqa: E402`

### `tests/conftest.py` (3)

- 25: `monkeypatch.setenv("WEALTHWIRE_CONFIG", str(cfg))`
- 26: `monkeypatch.setenv("WEALTHWIRE_HOME", str(data))`
- 32: `from wealthwire.ingest import run_ingest`

### `tests/fixtures/firm_headlines.yaml` (1)

- 5: `# Used by tests/test_firms.py (fixture SEC dictionary) and 'python -m wealthwire eval-firms' (real SEC data).`

### `tests/test_aidigest.py` (6)

- 7: `from wealthwire import db, paths`
- 8: `from wealthwire.aidigest import (INPUT, OUTPUT, WEEKLY_INPUT, WEEKLY_OUTPUT, build_inputs, finalize,`
- 10: `from wealthwire.contract import validate_data_dir`
- 11: `from wealthwire.sitebuild import FOOTER_NOTE, build_site`
- 206: `from wealthwire.__main__ import main`
- 236: `alert = next(s for s in steps if s.get("run", "").strip() == "python -m wealthwire alert")`

### `tests/test_alert.py` (12)

- 9: `from wealthwire import db, paths`
- 10: `from wealthwire.alert import REQUIRED, compose, run_alert`
- 66: `assert payload["from"] == "Wealth Wire <onboarding@resend.dev>"`
- 67: `assert payload["subject"] == f"Wealth Wire: {r['stories']} new stories on your watchlist"`
- 91: `assert subject == "Wealth Wire: 1 new story on your watchlist"`
- 96: `from wealthwire.__main__ import main`
- 115: `from wealthwire.__main__ import main`
- 116: `from wealthwire.aidigest import build_inputs, finalize`
- 117: `from wealthwire.ingest import run_ingest`
- 118: `from wealthwire.sitebuild import build_site`
- 127: `monkeypatch.setattr("wealthwire.alert.send_resend", box)`
- 144: `assert (out / "state" / "wealthwire.db").exists() and paths.db_path().exists()  # the scan covered them`

### `tests/test_categorize.py` (1)

- 3: `from wealthwire.categorize import Categorizer`

### `tests/test_cluster.py` (7)

- 7: `from wealthwire import paths`
- 8: `from wealthwire.categorize import Categorizer`
- 9: `from wealthwire.cluster import ClusterItem, cluster, normalize_title, score`
- 10: `from wealthwire.config import load_config, load_stoplist`
- 11: `from wealthwire.extract import extract_firms`
- 68: `from wealthwire import db`
- 69: `from wealthwire.sitebuild import collect`

### `tests/test_dates.py` (3)

- 3: `from wealthwire.dates import parse_date, sane_published`
- 4: `from wealthwire.parse import parse_feed`
- 5: `from wealthwire.discover import parse_listing`

### `tests/test_extract.py` (5)

- 3: `from wealthwire.config import load_stoplist`
- 4: `from wealthwire.extract import extract_aum, extract_firms, firm_spans, parse_aum`
- 91: `from wealthwire import db`
- 92: `from wealthwire.config import load_config`
- 93: `from wealthwire.sitebuild import Snapshot`

### `tests/test_firms.py` (3)

- 7: `from wealthwire.firmeval import evaluate`
- 8: `from wealthwire.firms import SecMatcher, aliases_for, load_curated, normalize, pretty_name`
- 123: `from wealthwire.pipeline import firms_in_text`

### `tests/test_firms_real.py` (3)

- 9: `from wealthwire.config import load_stoplist`
- 10: `from wealthwire.firmeval import evaluate`
- 11: `from wealthwire.firms import SecMatcher, load_curated`

### `tests/test_ingest.py` (6)

- 6: `from wealthwire import db, paths`
- 7: `from wealthwire.fetch import Fetcher, FixtureTransport`
- 8: `from wealthwire.ingest import run_ingest`
- 100: `from wealthwire.config import Source`
- 101: `from wealthwire.ingest import SourceIngester`
- 139: `f = Fetcher("WealthWire/0.1 (personal news reader; me@example.com)", per_host_delay=0, transport=transport)`

### `tests/test_mna.py` (4)

- 5: `from wealthwire import paths`
- 6: `from wealthwire.mna import deal_for_cluster, extract_deal`
- 98: `from wealthwire import db`
- 99: `from wealthwire.sitebuild import collect`

### `tests/test_privacy.py` (3)

- 9: `from wealthwire import paths`
- 10: `from wealthwire.sitebuild import PrivacyError, build_site, privacy_check`
- 35: `assert (built / "state" / "wealthwire.db").exists()`

### `tests/test_schedule.py` (4)

- 8: `from wealthwire import db`
- 9: `from wealthwire.dates import to_iso`
- 10: `from wealthwire.window import rank_clusters, top_window`
- 88: `from wealthwire.sitebuild import collect`

### `tests/test_sec.py` (6)

- 10: `from wealthwire import db`
- 11: `from wealthwire.fetch import Fetcher`
- 12: `from wealthwire.sec import DEFAULT_PAGE, discover_files, maybe_update, parse_zip`
- 87: `f = Fetcher("WealthWire/0.1 (test; me@example.com)", per_host_delay=0, transport=httpx.MockTransport(site))`
- 93: `assert all("WealthWire" in f.client.headers["user-agent"] for _ in [0])`
- 119: `from wealthwire.sitebuild import collect`

### `tests/test_site.py` (7)

- 8: `from wealthwire import paths`
- 9: `from wealthwire.contract import RULES, schema_for, validate_data_dir`
- 10: `from wealthwire.sitebuild import build_site`
- 64: `assert "wealthwire" not in p.read_text(errors="ignore").lower().replace("wealth wire", "")`
- 79: `from wealthwire.server import create_app`
- 82: `os.environ["WEALTHWIRE_NO_BACKGROUND"] = "1"`
- 87: `assert r.status_code == 200 and "<title>Fiduciary Duty</title>" in r.text`

### `tests/test_state.py` (6)

- 6: `from wealthwire import paths`
- 7: `from wealthwire.ingest import run_ingest`
- 8: `from wealthwire.sitebuild import build_site`
- 9: `from wealthwire.state import fetch_previous, publish, restore`
- 50: `assert "state/wealthwire.db" in tree and "vercel.json" in tree`
- 55: `con = sqlite3.connect(restore_dir / "state" / "wealthwire.db")`

### `tests/test_text.py` (2)

- 1: `from wealthwire.parse import parse_feed`
- 2: `from wealthwire.text import clean_description, strip_html, truncate`

### `tests/test_urls.py` (2)

- 3: `from wealthwire.urls import canonicalize`
- 40: `from wealthwire.urls import clean_link`

### `tests/test_watchlist.py` (2)

- 3: `from wealthwire.watchlist import Firm, Matcher`
- 48: `from wealthwire.watchlist import parse_watchlist`

### `tests/test_wire_stats.py` (11)

- 7: `from wealthwire import paths`
- 8: `from wealthwire.categorize import Categorizer`
- 9: `from wealthwire.ingest import append_wire_stats, run_ingest`
- 41: `from wealthwire import state`
- 52: `from wealthwire.config import Source`
- 53: `from wealthwire.fetch import Fetcher`
- 54: `from wealthwire.ingest import SourceIngester`
- 55: `from wealthwire import db`
- 76: `from wealthwire import db`
- 77: `from wealthwire.firms import SecMatcher`
- 78: `from wealthwire.wires import keep_wire_item`

### `tests/test_wires_gnews.py` (8)

- 7: `from wealthwire import db, paths`
- 8: `from wealthwire.categorize import Categorizer`
- 9: `from wealthwire.firms import SecMatcher`
- 10: `from wealthwire.gnews import dedupe_key, feed_url, parse_google_news, strip_outlet_suffix`
- 11: `from wealthwire.ingest import run_ingest`
- 12: `from wealthwire.wires import keep_wire_item`
- 46: `from wealthwire import fetch`
- 100: `from wealthwire.sitebuild import collect`

### `wealthwire/__init__.py` (1)

- 1: `"""Wealth Wire — personal news aggregator for the U.S. wealth management / RIA industry."""`

### `wealthwire/__main__.py` (4)

- 1: `"""CLI: python -m wealthwire <command>; see --help."""`
- 13: `Lets 'python -m wealthwire ingest' work from a scheduled task whatever 'python' is on PATH."""`
- 21: `os.execv(str(venv_py), [str(venv_py), "-m", "wealthwire", *sys.argv[1:]])`
- 29: `parser = argparse.ArgumentParser(prog="python -m wealthwire", description="Wealth Wire news aggregator")`

### `wealthwire/aidigest.py` (1)

- 273: `lines = [f"# Wealth Wire digest: {d['date']}", "", f"**Today in wealth management.** {d['opener']}", ""]`

### `wealthwire/alert.py` (4)

- 24: `DEFAULT_FROM = "Wealth Wire <onboarding@resend.dev>"`
- 62: `subject = f"Wealth Wire: {n} new {'story' if n == 1 else 'stories'} on your watchlist"`
- 74: `footer = f"\n\nOpen Wealth Wire: {site_url}" if site_url else ""`
- 78: `+ (f"<p><a href='{html.escape(site_url, quote=True)}'>Open Wealth Wire</a></p>" if site_url else ""))`

### `wealthwire/config.py` (1)

- 14: `"user_agent": "WealthWire/0.1 (personal news reader; {contact_email})",`

### `wealthwire/dates.py` (2)

- 26: `"""Current UTC time. WEALTHWIRE_NOW (ISO '...Z') pins the clock, for the offline demo whose fixture`
- 28: `pinned = os.environ.get("WEALTHWIRE_NOW")`

### `wealthwire/ingest.py` (1)

- 19: `log = logging.getLogger("wealthwire.ingest")`

### `wealthwire/paths.py` (5)

- 3: `Config (the editable YAML files) lives in the repo root unless WEALTHWIRE_CONFIG points elsewhere.`
- 5: `WEALTHWIRE_HOME points elsewhere — used for the offline demo dataset, tests and the refresh workflow.`
- 18: `return Path(os.environ.get("WEALTHWIRE_CONFIG") or ROOT)`
- 22: `return Path(os.environ.get("WEALTHWIRE_HOME") or ROOT)`
- 26: `return data_home() / "data" / "wealthwire.db"`

### `wealthwire/server.py` (5)

- 3: `python -m wealthwire serve           # build from the current data dir, then serve http://localhost:8000`
- 6: `index.html (Vercel does the same with a rewrite). With WEALTHWIRE_NO_BACKGROUND unset, the server`
- 24: `log = logging.getLogger("wealthwire.server")`
- 52: `if os.environ.get("WEALTHWIRE_NO_BACKGROUND") != "1":`
- 61: `app = FastAPI(title="Wealth Wire (static preview)", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)`

### `wealthwire/state.py` (4)

- 8: `state/             private carry-over: wealthwire.db, digests/*.md\|json, weekly/*.json, SOURCES.md`
- 50: `if (state / "wealthwire.db").exists():`
- 52: `shutil.copy(state / "wealthwire.db", paths.db_path())`
- 73: `db.backup_to(state / "wealthwire.db")`

## Outside the repository (not searchable here)

- GitHub repository name `SantiMiguel11/Wealth-Wire`.
- Vercel project name `wealth-wire` and its `*.vercel.app` URL.
- The `live` branch's `state/wealthwire.db` (data carried between refreshes).
- A local clone's `data/wealthwire.db`, if the project was ever run locally.
- `WEALTHWIRE_*` environment variables in anyone's shell or scheduled task.
- Browser storage keys in visitors' browsers: `ww-watchlist`, `fd-theme` and the older `ww-theme`.

---

# After the rename (verification, step 4)

The same search was re-run over every tracked file (excluding this file). **No tracked path contains an old name.**
**No old name appears in user-facing text.** The site, email, digest prompt, generated digest header, User-Agent,
workflow names, README, MANUAL-STEPS, DATA-CONTRACT and other docs all say "Fiduciary Wire". The tagline is
unchanged: "Daily news for wealth management and RIAs".

The regression test `tests/test_rename_compat.py::test_public_site_carries_only_the_new_name` builds the site and
fails on any old name in its HTML, JS, CSS, JSON, SVG or `live` README.

## What changed

| Area | Before | After |
|---|---|---|
| Wordmark, `<title>`, meta/Open Graph, footer | Fiduciary Duty | Fiduciary Wire (Open Graph tags added; `noindex` kept) |
| Python package, CLI | `wealthwire/`, `python -m wealthwire` | `fiduciarywire/`, `python -m fiduciarywire` (all imports, tests, scripts, workflows, `run.sh`, `.claude/`) |
| Environment variables | `WEALTHWIRE_HOME` / `_CONFIG` / `_NOW` / `_NO_BACKGROUND` / `_HOST` / `_PORT` | `FIDUCIARYWIRE_*` (old names still read as a fallback) |
| Database file | `data/wealthwire.db`, `state/wealthwire.db` on `live` | `fiduciarywire.db` (an old file is adopted or restored automatically) |
| Browser storage | `ww-watchlist`, `fd-theme` (+ older `ww-theme`) | `fw-watchlist`, `fw-theme`, with a one-time copy-then-delete migration |
| User-Agent | `WealthWire/0.1 (personal news reader; <email>)` | `FiduciaryWire/0.1 (personal news reader; santimiguel10@outlook.com)` |
| Email alert | subject "Wealth Wire: …", sender "Wealth Wire <onboarding@resend.dev>" | "Fiduciary Wire: …", "Fiduciary Wire <onboarding@resend.dev>" |
| Claude instructions / digest files | "You write the Wealth Wire digest", `# Wealth Wire digest: DATE` | "You write the Fiduciary Wire digest", `# Fiduciary Wire digest: DATE` |
| Workflows | "Refresh site", "Probe feeds", summary "### Wealth Wire refresh" | "Fiduciary Wire refresh", "Fiduciary Wire feed probe", "### Fiduciary Wire refresh" |
| JSON Schema `$id`s | `https://wealth-wire/schemas/…` | `https://fiduciary-wire/schemas/…` |
| Design reference | `design/Fiduciary Duty.dc.html` | `design/Fiduciary Wire.dc.html` (wordmark text updated) |
| Watchlist export filename | `fiduciary-duty-watchlist.json` | `fiduciary-wire-watchlist.json` (import accepts any file) |

## Remaining mentions, all intentional

| Where | Why it keeps an old name |
|---|---|
| `DECISIONS.md`, `AUDIT.md`, `AUDIT-PHASE2.md`, `PLAN.md`, `PLAN-PHASE2.md` line 3; `README.md` line 12 | One name-history note per document, so older references (commits, issues) still make sense. |
| `https://github.com/SantiMiguel11/Wealth-Wire…` in `MANUAL-STEPS.md` and `AUDIT-PHASE2.md` | The GitHub repository really is named `Wealth-Wire`. Renaming it is outside this change; GitHub would redirect, but the links are correct as they are. |
| `wealth-wire` / `wealth-wire.vercel.app` in `MANUAL-STEPS.md` §5 | The Vercel project and its current address really have that name. The steps tell you to redirect that address to fiduciarywire.com. |
| `ALERT_FROM` example in `MANUAL-STEPS.md` §5 | It tells you how to update a sender name you may have set by hand. |
| `fiduciarywire/paths.py`, `fiduciarywire/db.py`, `run.sh` | Compatibility: `WEALTHWIRE_*` env vars are still read as a fallback, and an existing `wealthwire.db` is adopted once. |
| `frontend/app.js` line 32 | A comment explaining the one-time storage-key migration (`ww-`/`fd-` → `fw-`). |
| `tests/test_rename_compat.py` | Tests that the old env vars, old database file, old `live` state file and old browser keys still work, and that no old name leaks into the site. |

## Outside the repository (unchanged, by decision)

- **GitHub repository name** `SantiMiguel11/Wealth-Wire`. Unchanged; workflows use `${GITHUB_REPOSITORY}`, so a later
  rename wouldn't break them.
- **Vercel project name** `wealth-wire`. Unchanged; the domain move is in MANUAL-STEPS §5.
- **The `live` branch.** Never renamed. Its current commit still holds `state/wealthwire.db`, which the next refresh
  restores and then republishes as `state/fiduciarywire.db`.
- **Past digests.** There are no archived digests yet. When there are, their content is left as written; only the
  site chrome around them changed.

## Verification results

- **Search re-run:** no old name in any tracked path; the remaining text mentions are exactly the intentional ones
  in the table above.
- **Tests:** 360 passed, including the privacy tests and `tests/test_rename_compat.py` (old env vars, old local
  database, pre-rename `live` state, no old name in the built site, User-Agent, email, digest text).
- **Browser, demo data:** `scripts/screenshots.py` ran 56 screenshots and all interaction checks with 0 problems.
  That includes the storage migration: `ww-watchlist` and `fd-theme` move to `fw-watchlist` and `fw-theme`, the
  old keys are removed, the migrated watchlist still pins its stories, and a leftover old key never overwrites
  the new one.
- **Browser, real data:** built from the `live` database, which was restored from its pre-rename file
  `state/wealthwire.db`. `screenshots/real-data/` holds Today, Feed, Deals and Archive at 1440 and 390, light and
  dark (16 images). Measured on every page:
  - the wordmark reads "Fiduciary Wire" in Cormorant Garamond, on one line (it ends at 244 px on a 390 px screen);
  - the four nav items sit on one row;
  - the tagline sits beside the wordmark on desktop and below it on mobile;
  - no horizontal overflow and no console errors.
- **Refresh workflow, end to end:**
  - [push run 36302341142](https://github.com/SantiMiguel11/Wealth-Wire/actions/runs/36302341142) restored
    `db_file: 'wealthwire.db'` from the pre-rename `live` commit, ingested 12 of 13 sources and published
    `state/fiduciarywire.db`;
  - the explicit [`workflow_dispatch` run 36302344969](https://github.com/SantiMiguel11/Wealth-Wire/actions/runs/36302344969)
    then succeeded on the renamed state. `gh` isn't installed in the build sandbox, so it was triggered through the
    GitHub API, which is the same event.
  `live` now carries `<title>Fiduciary Wire</title>` and `# Fiduciary Wire — live branch`.
