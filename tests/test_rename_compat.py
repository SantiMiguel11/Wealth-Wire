"""The rename to Fiduciary Wire must not strand data written under the project's earlier name (Wealth Wire)."""
import sqlite3

from fiduciarywire import db, paths, state


def test_old_env_var_names_still_work(tmp_path, monkeypatch):
    for k in ("FIDUCIARYWIRE_HOME", "FIDUCIARYWIRE_NOW"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WEALTHWIRE_HOME", str(tmp_path))
    monkeypatch.setenv("WEALTHWIRE_NOW", "2026-09-25T18:00:00Z")
    from fiduciarywire.dates import utcnow

    assert paths.data_home() == tmp_path
    assert utcnow().isoformat() == "2026-09-25T18:00:00+00:00"
    monkeypatch.setenv("FIDUCIARYWIRE_HOME", str(tmp_path / "new"))   # the new name wins when both are set
    assert paths.data_home() == tmp_path / "new"


def test_local_database_under_old_name_is_adopted(home):
    legacy = paths.db_path().with_name("wealthwire.db")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(legacy)
    con.execute("CREATE TABLE marker(x)")
    con.execute("INSERT INTO marker VALUES ('kept')")
    con.commit()
    con.close()
    conn = db.connect()
    assert conn.execute("SELECT x FROM marker").fetchone()[0] == "kept"
    assert paths.db_path().name == "fiduciarywire.db" and not legacy.exists()


def test_restore_reads_a_pre_rename_live_commit(home, tmp_path):
    prev = tmp_path / "prev" / "state"
    prev.mkdir(parents=True)
    con = sqlite3.connect(prev / "wealthwire.db")
    con.execute("CREATE TABLE marker(x)")
    con.commit()
    con.close()
    r = state.restore(tmp_path / "prev")
    assert r["db"] is True and r["db_file"] == "wealthwire.db"
    assert paths.db_path().exists()


def test_new_state_is_written_under_the_new_name(ingested, tmp_path):
    out = state.save(tmp_path / "out")
    assert (out / "fiduciarywire.db").exists() and not (out / "wealthwire.db").exists()


OLD_NAMES = __import__("re").compile(r"fiduciary[ _-]?duty|wealth[ _-]?wire", __import__("re").I)


def test_public_site_carries_only_the_new_name(ingested, tmp_path):
    from fiduciarywire.sitebuild import build_site

    from .conftest import NOW

    build_site(tmp_path / "out", NOW, write_state=False)
    site = tmp_path / "out" / "site"
    index = (site / "index.html").read_text()
    assert "<title>Fiduciary Wire</title>" in index and ">Fiduciary Wire</a>" in index
    assert "Daily news for wealth management and RIAs" in index
    assert '<meta property="og:site_name" content="Fiduciary Wire">' in index
    assert '<meta name="robots" content="noindex, nofollow">' in index
    for p in [*site.rglob("*.html"), *site.rglob("*.js"), *site.rglob("*.css"), *site.rglob("*.json"), *site.rglob("*.svg"),
              tmp_path / "out" / "README.md"]:
        text = p.read_text(errors="ignore")
        # the only permitted mention: the one-time migration of pre-rename storage keys in app.js
        if p.name == "app.js":
            text = text.replace('(Wealth Wire → "ww-", Fiduciary Duty → "fd-")', "")
        assert not OLD_NAMES.search(text), (p.name, OLD_NAMES.search(text).group(0))


def test_user_agent_email_and_digest_text_use_the_new_name(home):
    from fiduciarywire import alert
    from fiduciarywire.aidigest import render_markdown
    from fiduciarywire.config import load_config

    cfg = load_config()
    assert cfg["user_agent"] == f"FiduciaryWire/0.1 (personal news reader; {cfg['contact_email']})"
    subject, text, html = alert.compose([{"headline": "H", "firms": ["F"], "sources": [{"name": "O", "url": "https://e.com"}]}],
                                        "https://fiduciarywire.com")
    assert subject.startswith("Fiduciary Wire: ") and alert.DEFAULT_FROM.startswith("Fiduciary Wire <")
    assert "Open Fiduciary Wire" in text + html
    md = render_markdown({"date": "2026-09-25", "opener": "O.", "items": []}, None)
    assert md.startswith("# Fiduciary Wire digest: 2026-09-25")
    prompt = (paths.ROOT / "prompts" / "digest.md").read_text()
    assert "You write the Fiduciary Wire digest" in prompt and not OLD_NAMES.search(prompt)
