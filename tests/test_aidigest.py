"""§2 AI digest and §8 weekly recap: Claude's input, validation of its output, fallback, archive."""
import json
from datetime import timedelta

import pytest

from wealthwire import db, paths
from wealthwire.aidigest import (INPUT, OUTPUT, WEEKLY_INPUT, WEEKLY_OUTPUT, build_inputs, finalize,
                                 validate_digest, validate_weekly)
from wealthwire.contract import validate_data_dir
from wealthwire.sitebuild import FOOTER_NOTE, build_site

from .conftest import NOW

OPENER = "Deals and advisor moves led the day. Regulators also stayed busy with enforcement."
WEEKLY = "Several acquirers were active this week. Atlas Wealth Management led with 2 deals."


def good_output(inp: dict) -> dict:
    return {"opener": OPENER,
            "items": [{"cluster_id": c["id"], "summary": "The outlets report a development involving the firms named.",
                       "why_it_matters": "Advisors may see effects on recruiting and on competition for clients."}
                      for c in inp["clusters"]]}


@pytest.fixture
def prepared(ingested):
    conn = db.connect()
    result = build_inputs(conn, NOW)
    work = paths.work_dir()
    return conn, work, json.loads((work / INPUT).read_text()), result


def write(path, obj):
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")


def test_input_is_top_15_ranked_with_teasers(prepared):
    conn, work, inp, result = prepared
    assert result["clusters"] == len(inp["clusters"]) == 15
    counts = [len({o["name"] for o in c["outlets"]}) for c in inp["clusters"]]
    assert counts == sorted(counts, reverse=True)  # outlet count first
    c = inp["clusters"][0]
    assert set(c) == {"id", "headline", "category", "outlets", "firms", "aum", "teasers"}
    assert c["aum"] == "$1.2B AUM (from headline)"
    assert any(c["teasers"] for c in inp["clusters"])
    assert any("SEC-reported AUM (as of 2026-09-01)" in (c["aum"] or "") for c in inp["clusters"])
    # Friday (Pacific) → weekly input too
    assert result["weekly"] and (work / WEEKLY_INPUT).exists()


def test_stale_output_is_removed_when_input_is_rebuilt(prepared):
    conn, work, inp, _ = prepared
    write(work / OUTPUT, good_output(inp))
    build_inputs(conn, NOW)
    assert not (work / OUTPUT).exists()


def test_valid_output_is_archived_and_published(prepared, tmp_path):
    conn, work, inp, _ = prepared
    write(work / OUTPUT, good_output(inp))
    status = finalize(conn, NOW)
    assert status["digest"] == "ok: 15 stories"
    ddir = paths.digests_dir()
    for name in ("2026-09-25.json", "2026-09-25.md", "latest.json"):
        assert (ddir / name).exists()
    md = (ddir / "2026-09-25.md").read_text()
    assert "**Why it matters to advisors:**" in md and FOOTER_NOTE in md and OPENER in md
    conn.close()
    build_site(tmp_path / "out", NOW, write_state=False)
    data = tmp_path / "out" / "site" / "data"
    d = json.loads((data / "digest.json").read_text())
    assert d["ai"] is True and d["opener"] == OPENER and d["footer_note"] == FOOTER_NOTE
    assert [i["cluster_id"] for i in d["items"]] == [c["id"] for c in inp["clusters"]]
    assert all(i["summary"] and i["why_it_matters"] for i in d["items"])
    idx = json.loads((data / "digests" / "index.json").read_text())
    assert idx["digests"][0]["date"] == "2026-09-25"
    assert (data / "digests" / "2026-09-25.md").exists()
    assert validate_data_dir(data) == []
    # teasers went to Claude's input, but none reached the public site (privacy_check would have raised)
    site_text = "".join(p.read_text() for p in (tmp_path / "out" / "site").rglob("*.json"))
    assert not any(t in site_text for c in inp["clusters"] for t in c["teasers"] if len(t) >= 40)
    assert "_work" not in {p.name for p in (tmp_path / "out").rglob("*")}


def _mutate(inp, how):
    out = good_output(inp)
    first = inp["clusters"][0]
    if how == "unknown id":
        out["items"][0]["cluster_id"] = 999999
    elif how == "missing cluster":
        out["items"].pop()
    elif how == "duplicate":
        out["items"][1]["cluster_id"] = first["id"]
    elif how == "emoji":
        out["items"][0]["summary"] = "Harborview buys Summit Ridge 🚀."
    elif how == "hype":
        out["opener"] = "In today's fast-paced world, deals keep coming. Advisors take note."
    elif how == "exclamation":
        out["items"][2]["why_it_matters"] = "This is big news for advisors!"
    elif how == "invented number":
        out["items"][0]["summary"] = "Harborview paid $7.3 billion for Summit Ridge."
    elif how == "copied teaser":
        teaser = next(t for c in inp["clusters"] for t in c["teasers"] if len(t.split()) >= 12)
        out["items"][0]["summary"] = teaser
    elif how == "one-sentence opener":
        out["opener"] = "Deals led the day."
    elif how == "empty summary":
        out["items"][0]["summary"] = "  "
    elif how == "not an object":
        return ["items"]
    return out


BAD = ["unknown id", "missing cluster", "duplicate", "emoji", "hype", "exclamation", "invented number",
       "copied teaser", "one-sentence opener", "empty summary", "not an object"]


@pytest.mark.parametrize("how", BAD)
def test_validation_rejects(prepared, how):
    _, _, inp, _ = prepared
    assert validate_digest(_mutate(inp, how), inp)


def test_validation_accepts_numbers_from_the_input(prepared):
    _, _, inp, _ = prepared
    out = good_output(inp)
    out["items"][0]["summary"] = "Harborview Wealth Partners agreed to buy Summit Ridge Advisors, which manages $1.2 billion."
    assert validate_digest(out, inp) == []


@pytest.mark.parametrize("how", ["invalid json", "invented number", "no output"])
def test_fallback_shows_plain_list_and_last_good_digest(prepared, tmp_path, how):
    conn, work, inp, _ = prepared
    # a good digest from yesterday is in the archive
    yesterday = NOW - timedelta(days=1)
    build_inputs(conn, yesterday)
    write(work / OUTPUT, good_output(json.loads((work / INPUT).read_text())))
    assert finalize(conn, yesterday)["digest"].startswith("ok")
    ddir = paths.digests_dir()
    assert (ddir / "2026-09-24.json").exists()

    build_inputs(conn, NOW)
    if how == "invalid json":
        write(work / OUTPUT, "{not json")
    elif how == "invented number":
        write(work / OUTPUT, _mutate(inp, "invented number"))
    status = finalize(conn, NOW)
    assert status["digest"].startswith("fallback")
    assert not (ddir / "2026-09-25.json").exists()
    conn.close()
    build_site(tmp_path / "out", NOW, write_state=False)
    data = tmp_path / "out" / "site" / "data"
    d = json.loads((data / "digest.json").read_text())
    assert d["ai"] is False and d["opener"] is None
    assert len(d["items"]) == 15 and all(i["summary"] is None for i in d["items"])
    assert d["last_good_digest"] == {"date": "2026-09-24", "path": "data/digests/2026-09-24.json"}
    assert validate_data_dir(data) == []


def test_weekly_recap_with_and_without_claude(prepared, tmp_path):
    conn, work, inp, _ = prepared
    winput = json.loads((work / WEEKLY_INPUT).read_text())
    assert winput["week"] == "2026-W39" and winput["start"] == "2026-09-21" and winput["end"] == "2026-09-25"
    assert winput["top_acquirers"][0] == {"name": "Atlas Wealth Management", "deals": 2}
    assert winput["total_disclosed_aum"] == "$2.95B" and winput["disclosed_aum_deals"] == 3

    # no Claude output → numbers-only recap
    status = finalize(conn, NOW)
    assert status["weekly"].startswith("fallback")
    w = json.loads((paths.weekly_dir() / "2026-W39.json").read_text())
    assert w["ai"] is False and w["paragraph"] is None
    assert w["total_disclosed_aum_usd"] == pytest.approx(2.95e9)
    assert w["deals"] and all(d["target_aum_source"] in ("headline", "sec", None) for d in w["deals"])

    # Claude output → paragraph
    write(work / WEEKLY_OUTPUT, {"paragraph": WEEKLY})
    assert finalize(conn, NOW)["weekly"].startswith("ok")
    assert json.loads((paths.weekly_dir() / "2026-W39.json").read_text())["paragraph"] == WEEKLY

    # a later Friday run where Claude fails keeps the earlier paragraph if the deals are unchanged
    (work / WEEKLY_OUTPUT).unlink()
    assert "kept earlier paragraph" in finalize(conn, NOW + timedelta(hours=5))["weekly"]
    conn.close()
    build_site(tmp_path / "out", NOW, write_state=False)
    data = tmp_path / "out" / "site" / "data"
    assert json.loads((data / "weekly" / "2026-W39.json").read_text())["ai"] is True
    assert json.loads((data / "digests" / "index.json").read_text())["weekly"][0]["week"] == "2026-W39"
    assert validate_data_dir(data) == []


@pytest.mark.parametrize("paragraph", ["A record week 🎉.", "Deals totaled $9.9B this week. Big moves.", "", None])
def test_weekly_validation_rejects(prepared, paragraph):
    _, work, _, _ = prepared
    assert validate_weekly({"paragraph": paragraph}, json.loads((work / WEEKLY_INPUT).read_text()))


def test_no_weekly_input_on_other_days(ingested):
    conn = db.connect()
    r = build_inputs(conn, NOW - timedelta(days=1))  # Thursday
    assert r["weekly"] is False and not (paths.work_dir() / WEEKLY_INPUT).exists()
    assert finalize(conn, NOW - timedelta(days=1))["weekly"] is None


def test_cli_commands_never_fail(ingested, capsys):
    from wealthwire.__main__ import main

    assert main(["digest-input"]) == 0
    assert main(["digest-finalize"]) == 0
    out = capsys.readouterr().out
    assert "digest input: " in out and "digest: " in out


def test_prompt_file_states_the_rules():
    text = (paths.ROOT / "prompts" / "digest.md").read_text()
    for rule in ("Do not fetch", "Every number you write must appear in the input", "No hype, no emoji",
                 "In today's fast-paced", "_work/digest_output.json", "_work/weekly_output.json", "why_it_matters"):
        assert rule in text


def test_workflow_runs_claude_safely():
    import yaml

    wf = yaml.safe_load((paths.ROOT / ".github/workflows/refresh-site.yml").read_text())
    steps = wf["jobs"]["refresh"]["steps"]
    names = [s.get("name", "") for s in steps]
    claude = next(s for s in steps if s.get("uses", "").startswith("anthropics/claude-code-action@"))
    assert claude["continue-on-error"] is True
    assert "HAS_CLAUDE == 'true'" in claude["if"]
    assert '--allowedTools "Read,Write"' in claude["with"]["claude_args"]
    assert "WebFetch" in claude["with"]["claude_args"].split("--disallowedTools")[1]
    assert "CLAUDE_CODE_OAUTH_TOKEN" in claude["with"]["claude_code_oauth_token"]
    assert "ANTHROPIC_API_KEY" in claude["with"]["anthropic_api_key"]
    order = [names.index(n) for n in names if n.startswith(("Prepare the digest", "Write the digest", "Validate the digest", "Build site"))]
    assert order == sorted(order) and len(order) == 4
    alert = next(s for s in steps if s.get("run", "").strip() == "python -m wealthwire alert")
    assert alert["continue-on-error"] is True
    assert steps.index(alert) > names.index("Publish to the live branch (single orphan commit)")


def test_demo_digest_fixture_still_validates(prepared):
    """The screenshot demo feeds tests/fixtures/demo/*_output.json through the real validator."""
    from .conftest import DEMO

    _, work, inp, _ = prepared
    assert validate_digest(json.loads((DEMO / "digest_output.json").read_text()), inp) == []
    winput = json.loads((work / WEEKLY_INPUT).read_text())
    assert validate_weekly(json.loads((DEMO / "weekly_output.json").read_text()), winput) == []
