"""§8 watchlist email: gating on secrets, matching new stories, and never persisting the secret watchlist."""
import json
import os
import uuid
from pathlib import Path

import pytest

from wealthwire import db, paths
from wealthwire.alert import REQUIRED, compose, run_alert

from .conftest import ROOT

HARBORVIEW = json.dumps({"version": 1, "firms": [{"name": "Harborview Wealth Partners", "aliases": ["Harborview"]}]})


class Outbox:
    def __init__(self, ok=True):
        self.sent, self.ok = [], ok

    def __call__(self, key, payload):
        self.sent.append((key, payload))
        return self.ok, "HTTP 200" if self.ok else "HTTP 422"


def env(**overrides):
    base = {"WATCHLIST_JSON": HARBORVIEW, "RESEND_API_KEY": "re_test", "ALERT_EMAIL": "me@example.com"}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


@pytest.mark.parametrize("missing", REQUIRED)
def test_skips_with_notice_when_a_secret_is_missing(ingested, capsys, missing):
    box = Outbox()
    r = run_alert(db.connect(), env(**{missing: None}), send=box)
    assert r["status"] == "skipped" and r["missing"] == [missing]
    assert box.sent == []
    assert f"::notice::Watchlist email skipped: {missing} not set" in capsys.readouterr().out


def test_blank_secret_counts_as_missing(ingested):
    assert run_alert(db.connect(), env(ALERT_EMAIL="  "), send=Outbox())["status"] == "skipped"


def test_invalid_watchlist_json_is_a_warning_not_a_failure(ingested, capsys):
    box = Outbox()
    assert run_alert(db.connect(), env(WATCHLIST_JSON="{nope"), send=box)["status"] == "invalid watchlist"
    assert box.sent == [] and "::warning::" in capsys.readouterr().out


def test_no_email_when_nothing_matches(ingested):
    box = Outbox()
    wl = json.dumps({"firms": [{"name": "Nonexistent Quuxbridge Advisors"}]})
    assert run_alert(db.connect(), env(WATCHLIST_JSON=wl), send=box)["status"] == "no matches"
    assert box.sent == []


def test_one_email_listing_new_matches(ingested, capsys):
    box = Outbox()
    r = run_alert(db.connect(), env(ALERT_EMAIL="me@example.com, you@example.com", SITE_URL="https://ww.example"), send=box)
    assert r["status"] == "sent" and r["stories"] >= 2
    assert len(box.sent) == 1
    key, payload = box.sent[0]
    assert key == "re_test"
    assert payload["to"] == ["me@example.com", "you@example.com"]
    assert payload["from"] == "Wealth Wire <onboarding@resend.dev>"
    assert payload["subject"] == f"Wealth Wire: {r['stories']} new stories on your watchlist"
    assert "Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors" in payload["text"]
    assert "https://ww.example" in payload["html"]
    # one entry per cluster, even when several outlets carried the story
    assert payload["text"].count("Summit Ridge Advisors\n") == 1
    out = capsys.readouterr().out
    assert "Watchlist email sent" in out and "Harborview" not in out and "me@example.com" not in out


def test_only_stories_from_this_refresh(ingested):
    conn = db.connect()
    db.set_meta(conn, "last_ingest", "2099-01-01T00:00:00Z")  # nothing was fetched at/after this
    conn.commit()
    assert run_alert(conn, env(), send=Outbox())["status"] == "no matches"


def test_send_failure_does_not_raise(ingested, capsys):
    r = run_alert(db.connect(), env(), send=Outbox(ok=False))
    assert r["status"] == "send failed" and "::warning::" in capsys.readouterr().out


def test_compose_escapes_html():
    subject, text, body = compose([{"headline": "A <b> & B", "firms": ["X&Y"], "sources": [
        {"name": "Out<let>", "url": "https://e.com/?a=1&b='2'"}]}])
    assert subject == "Wealth Wire: 1 new story on your watchlist"
    assert "<b> &" not in body and "&lt;b&gt; &amp; B" in body and "Out&lt;let&gt;" in body


def test_cli_without_secrets_exits_cleanly(ingested, monkeypatch, capsys):
    from wealthwire.__main__ import main

    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    assert main(["alert"]) == 0
    assert "Watchlist email skipped" in capsys.readouterr().out


def _files(*roots: Path):
    skip = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache"}
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for f in filenames:
                yield Path(dirpath) / f


def test_secret_watchlist_is_never_written_anywhere(home, tmp_path, monkeypatch, capsys):
    """Run a whole refresh with the watchlist secret set; its contents must not appear in any file."""
    from wealthwire.__main__ import main
    from wealthwire.aidigest import build_inputs, finalize
    from wealthwire.ingest import run_ingest
    from wealthwire.sitebuild import build_site

    from .conftest import DEMO, NOW

    sentinel = f"Sentinel{uuid.uuid4().hex}"
    secret = json.dumps({"firms": [{"name": sentinel, "aliases": ["Harborview", f"{sentinel}Alias"]}]})
    for k, v in env(WATCHLIST_JSON=secret).items():
        monkeypatch.setenv(k, v)
    box = Outbox()
    monkeypatch.setattr("wealthwire.alert.send_resend", box)

    run_ingest(fixtures=DEMO, now=NOW, quiet=True)
    conn = db.connect()
    build_inputs(conn, NOW)
    finalize(conn, NOW)
    conn.close()
    out = tmp_path / "out"
    build_site(out, NOW, write_state=True)
    assert main(["alert"]) == 0
    assert box.sent and sentinel in box.sent[0][1]["text"]  # it was really used...

    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err  # ...but never logged
    needle = sentinel.encode()
    leaks = [p for p in _files(tmp_path, ROOT) if p.is_file() and needle in p.read_bytes()]
    assert leaks == []
    assert (out / "state" / "wealthwire.db").exists() and paths.db_path().exists()  # the scan covered them
