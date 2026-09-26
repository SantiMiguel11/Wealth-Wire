"""Carrying data between refreshes through the `live` branch (§7).

The `live` branch is a single orphan commit, force-pushed on every refresh:

    live/
      vercel.json        Vercel config (serve site/ only)
      site/              the public website — the only thing Vercel deploys
      state/             private carry-over: wealthwire.db, digests/*.md|json, weekly/*.json, SOURCES.md

`fetch_previous` pulls that tree down, `restore` copies state/ into the data dir, the refresh runs,
`save` writes state/ back into the output tree and `publish` force-pushes it as a new orphan commit.
Because the DB inside the commit carries the data forward, git history never grows.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

from . import db, paths

STATE_DIRNAME = "state"


def _git(*args: str, cwd: Path | None = None, check: bool = True, capture: bool = False):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=capture)


def fetch_previous(dest: Path, repo_dir: Path = Path("."), remote: str = "origin", branch: str = "live") -> bool:
    """Extract the tree of `remote/branch` into dest. Returns False when the branch doesn't exist yet."""
    res = _git("fetch", "--depth=1", remote, branch, cwd=repo_dir, check=False, capture=True)
    if res.returncode != 0:
        print(f"no previous {branch} branch ({res.stderr.decode(errors='replace').strip()[:200]}); starting fresh")
        return False
    archive = _git("archive", "--format=tar", "FETCH_HEAD", cwd=repo_dir, capture=True)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(dest, filter="data")
    return True


def restore(prev: Path) -> dict:
    """Copy the previous refresh's private state into the data dir."""
    state = prev / STATE_DIRNAME
    restored = {"db": False, "digests": 0, "weekly": 0}
    if not state.is_dir():
        return restored
    if (state / "wealthwire.db").exists():
        paths.db_path().parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(state / "wealthwire.db", paths.db_path())
        restored["db"] = True
    for sub, target in (("digests", paths.digests_dir()), ("weekly", paths.weekly_dir())):
        if (state / sub).is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for f in (state / sub).iterdir():
                if f.is_file():
                    shutil.copy(f, target / f.name)
                    restored[sub] += 1
    return restored


def save(out: Path) -> Path:
    """Write the private state into out/state (consistent DB copy + archives)."""
    state = out / STATE_DIRNAME
    if state.exists():
        shutil.rmtree(state)
    state.mkdir(parents=True)
    db.backup_to(state / "wealthwire.db")
    for sub, source in (("digests", paths.digests_dir()), ("weekly", paths.weekly_dir())):
        if source.is_dir():
            (state / sub).mkdir(exist_ok=True)
            for f in source.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    shutil.copy(f, state / sub / f.name)
    for f in (paths.sources_md_path(), paths.firm_eval_path()):
        if f.exists():
            shutil.copy(f, state / f.name)
    return state


def publish(out: Path, remote_url: str, branch: str = "live", message: str = "Refresh") -> None:
    """Commit `out` as a single orphan commit and force-push it to `branch`."""
    if (out / ".git").exists():
        shutil.rmtree(out / ".git")
    _git("init", "-q", "-b", branch, cwd=out)
    _git("add", "-A", cwd=out)
    _git(
        "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-q", "-m", message, cwd=out,
    )
    _git("push", "-q", "-f", remote_url, f"HEAD:{branch}", cwd=out)
