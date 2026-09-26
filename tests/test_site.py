import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_builder(monkeypatch):
    monkeypatch.setenv("WEALTHWIRE_NO_BACKGROUND", "1")
    spec = importlib.util.spec_from_file_location("build_preview", ROOT / "scripts" / "build_preview.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def embedded(html: str) -> dict:
    raw = re.search(r"window.__WW_DATA__ = (\{.*?\});</script>", html, re.S).group(1)
    return json.loads(raw.replace("<\\/", "</"))


def test_public_site_build(ingested, tmp_path, monkeypatch):
    out = tmp_path / "_live"
    load_builder(monkeypatch).build_site(out)
    html = (out / "site" / "index.html").read_text()
    data = embedded(html)
    # headlines + links only: no publisher descriptions anywhere in the page
    assert all(it["description"] == "" for c in data["clusters"] for it in c["items"])
    assert all(c["description"] == "" for c in data["clusters"])
    assert all(not s["descriptions"] for s in data["digest"]["top"])
    # excluded (paywalled) source is gone everywhere, and outlet counts follow
    assert "advisorhub" not in html.lower()
    team = next(c for c in data["clusters"] if "Harborview" in c["headline"] and "Breaks Away" in c["headline"])
    assert team["outlet_count"] == 2 and "AdvisorHub" not in team["headline"]
    # not indexed, read-only watchlist, digest tab in site mode
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert (out / "site" / "robots.txt").read_text().startswith("User-agent: *\nDisallow: /")
    assert data["readonly"] is True and data["digest"]["site_mode"] is True
    assert 'placeholder="Search headlines"' in html
    # Vercel serves only site/; the DB for the next run travels in state/
    vercel = json.loads((out / "vercel.json").read_text())
    assert vercel["outputDirectory"] == "site"
    assert (out / "state" / "wealthwire.db").exists() and not (out / "site" / "wealthwire.db").exists()
