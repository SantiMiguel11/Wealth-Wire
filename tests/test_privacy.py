"""§3: the deployed output never contains the database, publisher teasers, or a watchlist."""
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from fiduciarywire import paths
from fiduciarywire.sitebuild import PrivacyError, build_site, privacy_check

from .conftest import NOW

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def built(ingested, tmp_path):
    out = tmp_path / "out"
    build_site(out, now=NOW)
    return out


def teasers():
    con = sqlite3.connect(paths.db_path())
    return [d for t, d in con.execute("SELECT title, description FROM items WHERE description != ''") if d.strip() not in t]


def test_no_database_files_in_deployed_output(built):
    site = built / "site"
    bad = [p for p in site.rglob("*") if p.suffix in {".db", ".sqlite", ".sqlite3"} or p.name.endswith(("-wal", "-shm"))]
    assert bad == []
    assert all(not p.read_bytes().startswith(b"SQLite format 3") for p in site.rglob("*") if p.is_file())
    # the DB does travel in the private state/ directory, which Vercel never serves
    assert (built / "state" / "fiduciarywire.db").exists()
    assert json.loads((built / "vercel.json").read_text())["outputDirectory"] == "site"


def test_no_teaser_text_in_any_public_file(built):
    ts = [t for t in teasers() if len(t) >= 20]
    assert len(ts) > 20, "fixture should contain plenty of teasers"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in (built / "site").rglob("*") if p.is_file())
    leaked = [t for t in ts if t in blob or json.dumps(t)[1:-1] in blob]
    assert leaked == []


def test_public_json_has_no_description_fields(built):
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    for p in (built / "site" / "data").rglob("*.json"):
        ks = set(keys(json.loads(p.read_text())))
        assert not ks & {"description", "descriptions", "teaser", "teasers"}, p


def test_privacy_check_fails_closed(built, tmp_path):
    site = built / "site"
    ts = teasers()
    privacy_check(site, ts)  # clean build passes
    (site / "data" / "leak.json").write_text(json.dumps({"x": ts[0]}))
    with pytest.raises(PrivacyError, match="teaser"):
        privacy_check(site, ts)
    (site / "data" / "leak.json").unlink()
    (site / "copy.sqlite").write_bytes(b"SQLite format 3\x00")
    with pytest.raises(PrivacyError, match="database"):
        privacy_check(site, ts)


def test_watchlist_yaml_is_gone():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert "watchlist.yaml" not in tracked
    assert "watchlist.yaml" in (ROOT / ".gitignore").read_text().split()


def test_no_watchlist_in_build(built):
    names = {p.name for p in built.rglob("*")}
    assert "watchlist.yaml" not in names and "watchlist.json" not in names
