"""§9 data contract + frontend isolation."""
import json
import re
from pathlib import Path

import pytest

from fiduciarywire import paths
from fiduciarywire.contract import RULES, schema_for, validate_data_dir
from fiduciarywire.sitebuild import build_site

from .conftest import NOW

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {"meta.json", "stories.json", "clusters.json", "digest.json", "digests/index.json", "mna.json",
            "weekly/index.json", "firms/index.json", "trending.json", "sources.json"}


@pytest.fixture
def built(ingested, tmp_path):
    out = tmp_path / "out"
    build_site(out, now=NOW)
    return out


def test_all_contract_files_emitted(built):
    data = built / "site" / "data"
    rels = {p.relative_to(data).as_posix() for p in data.rglob("*.json")}
    assert EXPECTED <= rels


def test_generated_json_matches_schemas(built):
    assert validate_data_dir(built / "site" / "data") == []


def test_every_schema_is_valid_and_used():
    import jsonschema

    names = {name for _, name in RULES}
    for p in (ROOT / "schemas").glob("*.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(p.read_text()))
        assert p.name in names, f"{p.name} is not mapped to any data file"
    assert schema_for("firms/some-firm-123.json") == "firm.schema.json"
    assert schema_for("digests/2026-09-25.json") == "digest.schema.json"
    assert schema_for("weekly/2026-W39.json") == "weekly.schema.json"


def test_schema_rejects_drift(built):
    """An unknown field or a wrong type must fail validation (the contract is strict)."""
    data = built / "site" / "data"
    meta = json.loads((data / "meta.json").read_text())
    meta["surprise"] = 1
    (data / "meta.json").write_text(json.dumps(meta))
    assert any("meta.json" in p for p in validate_data_dir(data))


def test_frontend_reads_only_static_data():
    js = (ROOT / "frontend" / "app.js").read_text()
    fetches = re.findall(r"fetch\(([^,)]+)", js)
    assert fetches == ['"/data/" + path'], fetches
    assert "/api/" not in js
    # nothing in the frontend folder refers to the pipeline
    for p in (ROOT / "frontend").iterdir():
        assert "fiduciarywire" not in p.read_text(errors="ignore").lower().replace("fiduciary wire", "")


def test_vercel_config(built):
    v = json.loads((built / "vercel.json").read_text())
    assert v["outputDirectory"] == "site"
    assert {"source": "/firm/:slug", "destination": "/index.html"} in v["rewrites"]
    assert any(h["key"] == "X-Robots-Tag" and "noindex" in h["value"] for rule in v["headers"] for h in rule["headers"])
    assert (built / "site" / "robots.txt").read_text() == "User-agent: *\nDisallow: /\n"
    assert '<meta name="robots" content="noindex, nofollow">' in (built / "site" / "index.html").read_text()


def test_local_server_serves_site_and_firm_fallback(built):
    from fastapi.testclient import TestClient

    from fiduciarywire.server import create_app

    import os
    os.environ["FIDUCIARYWIRE_NO_BACKGROUND"] = "1"
    with TestClient(create_app(built / "site")) as c:
        assert c.get("/").status_code == 200
        assert c.get("/data/meta.json").json()["schema_version"] == 1
        r = c.get("/firm/anything-123")
        assert r.status_code == 200 and "<title>Fiduciary Wire</title>" in r.text
        assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_frontend_script_parses():
    """A syntax error in app.js blanks the whole site; catch it without a browser."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "--check", str(paths.FRONTEND_DIR / "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
