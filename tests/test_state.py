"""§7: the live branch round-trips data (checkout live → ingest → publish) without loss or history growth."""
import sqlite3
import subprocess
from datetime import timedelta

from wealthwire import paths
from wealthwire.ingest import run_ingest
from wealthwire.sitebuild import build_site
from wealthwire.state import fetch_previous, publish, restore

from .conftest import DEMO, NOW


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def count_items():
    return sqlite3.connect(paths.db_path()).execute("SELECT COUNT(*) FROM items").fetchone()[0]


def test_live_round_trip(home, tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", str(remote), cwd=tmp_path)
    repo = tmp_path / "repo"          # stands in for the workflow's checkout of main
    git("init", "-q", str(repo), cwd=tmp_path)
    git("remote", "add", "origin", str(remote), cwd=repo)

    # first refresh: no live branch yet
    assert fetch_previous(tmp_path / "prev0", repo_dir=repo) is False
    run_ingest(fixtures=DEMO, now=NOW, quiet=True)
    first = count_items()
    build_site(tmp_path / "out1", now=NOW)
    publish(tmp_path / "out1", str(remote), message="Refresh 1")

    # second refresh on a fresh machine: wipe the local data dir, restore from live, ingest again
    paths.db_path().unlink()
    assert fetch_previous(tmp_path / "prev1", repo_dir=repo) is True
    assert restore(tmp_path / "prev1")["db"] is True
    assert count_items() == first
    summary = run_ingest(fixtures=DEMO, now=NOW + timedelta(hours=6), quiet=True)
    assert summary["new"] == 0 and count_items() == first      # nothing lost, nothing duplicated
    build_site(tmp_path / "out2", now=NOW + timedelta(hours=6))
    publish(tmp_path / "out2", str(remote), message="Refresh 2")

    # live is still a single orphan commit, and it carries the DB privately (outside site/)
    log = git("log", "--oneline", "live", cwd=remote).strip().splitlines()
    assert log == [log[0]] and "Refresh 2" in log[0]
    tree = git("ls-tree", "-r", "--name-only", "live", cwd=remote).split()
    assert "state/wealthwire.db" in tree and "vercel.json" in tree
    assert not any(t.startswith("site/") and t.endswith((".db", ".sqlite")) for t in tree)
    # the previous-success marker travelled too (drives the Top Stories window)
    restore_dir = tmp_path / "prev2"
    fetch_previous(restore_dir, repo_dir=repo)
    con = sqlite3.connect(restore_dir / "state" / "wealthwire.db")
    assert con.execute("SELECT value FROM meta WHERE key='previous_success'").fetchone()[0] == "2026-09-26T00:00:00Z"
