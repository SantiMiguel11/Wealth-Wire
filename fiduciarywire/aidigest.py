"""AI digest + weekly M&A recap (§2, §8): inputs for Claude, and validation of what Claude writes.

Flow in the refresh workflow:
  1. `digest-input`   → _work/digest_input.json (top 15 Top Stories clusters, with teasers) and, on Pacific
                        Fridays, _work/weekly_input.json (this week's M&A rows).
  2. anthropics/claude-code-action, following prompts/digest.md, writes _work/digest_output.json and
     _work/weekly_output.json. Tools limited to Read/Write; no web access.
  3. `digest-finalize` → validates the output. If it passes, it writes digests/YYYY-MM-DD.{json,md} and
                         digests/latest.json, plus weekly/YYYY-Www.json. If it fails, the site shows the plain
                         ranked list and the date of the last good digest.

_work/ holds publisher teasers, so it is never published or carried in state.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import db, paths
from .config import load_config
from .dates import from_iso, to_iso, utcnow

TOP_N = 15
INPUT, OUTPUT = "digest_input.json", "digest_output.json"
WEEKLY_INPUT, WEEKLY_OUTPUT = "weekly_input.json", "weekly_output.json"

EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF️‍]")
BANNED = ("fast-paced", "in today's", "game-changer", "game changer", "revolutioniz", "delve", "buckle up",
          "look no further", "ever-evolving", "ever-changing", "exciting", "!")
TEASER_RUN = 10  # this many consecutive words copied from a teaser = reproducing publisher text
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SENT_END = re.compile(r"(?<=[a-z0-9%)\]\"”’])[.?](?=\s+[A-Z“\"]|\s*$)")


# ------------------------------------------------------------------------------------------------
# formatting helpers
# ------------------------------------------------------------------------------------------------
def fmt_aum(v: float | None) -> str | None:
    if not v:
        return None
    for div, unit in ((1e12, "T"), (1e9, "B")):
        if v >= div:
            return "$" + f"{v / div:.2f}".rstrip("0").rstrip(".") + unit
    return f"${v / 1e6:.0f}M"


def aum_label(v: float | None, source: str | None, sec_date: str | None) -> str | None:
    s = fmt_aum(v)
    if not s:
        return None
    return f"{s} SEC-reported AUM (as of {sec_date})" if source == "sec" else f"{s} AUM (from headline)"


def local_now(now: datetime, cfg: dict | None = None) -> datetime:
    from zoneinfo import ZoneInfo

    return now.astimezone(ZoneInfo((cfg or load_config())["timezone"]))


def is_weekly_day(now: datetime, cfg: dict | None = None) -> bool:
    return local_now(now, cfg).weekday() == 4  # Friday, Pacific


# ------------------------------------------------------------------------------------------------
# inputs
# ------------------------------------------------------------------------------------------------
def _teasers(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    q = ",".join("?" * len(item_ids))
    return {r["id"]: r["description"].strip() for r in conn.execute(
        f"SELECT id, title, description FROM items WHERE id IN ({q}) AND description != ''", item_ids)
        if r["description"].strip() and r["description"].strip() not in r["title"]}


def _cluster_input(snap, c: dict, teasers: dict[int, str]) -> dict:
    items = [it for it in snap.items if it["cluster_id"] == c["id"]]
    return {
        "id": c["id"],
        "headline": c["headline"],
        "category": c["category"],
        "outlets": [{"name": it["source"], "headline": it["title"], "url": it["url"]} for it in items],
        "firms": [f["name"] for f in c["firms"]],
        "aum": aum_label(c["aum_usd"], c["aum_source"], c["sec_aum_as_of"]),
        "teasers": list(dict.fromkeys(teasers[it["id"]] for it in items if it["id"] in teasers)),
    }


def weekly_data(snap, now: datetime) -> dict:
    """This week's (Monday → today, Pacific) M&A recap numbers."""
    today = local_now(now, snap.cfg).date()
    start = today - timedelta(days=today.weekday())
    iso = today.isocalendar()
    deals = [d for d in snap.mna_json()["deals"]
             if start <= local_now(from_iso(d["date"]), snap.cfg).date() <= today]
    disclosed = [d["target_aum_usd"] for d in deals if d["target_aum_usd"] and d["target_aum_source"] == "headline"]
    counts: Counter = Counter()
    names: dict[str, dict] = {}
    for d in deals:
        a = d["acquirer"]
        if a["name"]:
            key = a["crd"] or a["name"].lower()
            counts[key] += 1
            names.setdefault(key, {"name": a["name"], "slug": a["slug"]})
    top = [{"name": names[k]["name"], "slug": names[k]["slug"], "deals": n}
           for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], names[kv[0]]["name"].lower()))][:5]
    return {"schema_version": 1, "generated_at": to_iso(now), "week": f"{iso[0]}-W{iso[1]:02d}",
            "start": start.isoformat(), "end": today.isoformat(), "deals": deals,
            "total_disclosed_aum_usd": sum(disclosed) if disclosed else None,
            "disclosed_aum_deals": len(disclosed), "top_acquirers": top, "paragraph": None, "ai": False}


def build_inputs(conn: sqlite3.Connection, now: datetime | None = None, work: Path | None = None,
                 weekly: bool | None = None) -> dict:
    from .sitebuild import Snapshot, window_ranked
    from .window import top_window

    now = now or utcnow()
    work = work or paths.work_dir()
    work.mkdir(parents=True, exist_ok=True)
    for name in (INPUT, OUTPUT, WEEKLY_INPUT, WEEKLY_OUTPUT):
        (work / name).unlink(missing_ok=True)  # never validate a stale output against a new input
    cfg = load_config()
    snap = Snapshot(conn, cfg, now)
    window_start = top_window(conn, now)
    top = window_ranked(snap, window_start)[:TOP_N]
    teasers = _teasers(conn, [i for c in top for i in c["item_ids"]])
    date = local_now(now, cfg).date().isoformat()
    doc = {"date": date, "generated_at": to_iso(now), "window_start": to_iso(window_start),
           "output_file": f"_work/{OUTPUT}", "clusters": [_cluster_input(snap, c, teasers) for c in top]}
    (work / INPUT).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    result = {"date": date, "clusters": len(top), "weekly": False}
    if weekly if weekly is not None else is_weekly_day(now, cfg):
        w = weekly_data(snap, now)
        wt = _teasers(conn, [i for d in w["deals"] for i in snap.by_id[d["cluster_id"]]["item_ids"]])
        winput = {"week": w["week"], "start": w["start"], "end": w["end"], "output_file": f"_work/{WEEKLY_OUTPUT}",
                  "deal_count": len(w["deals"]),
                  "total_disclosed_aum": fmt_aum(w["total_disclosed_aum_usd"]),
                  "disclosed_aum_deals": w["disclosed_aum_deals"],
                  "top_acquirers": [{"name": a["name"], "deals": a["deals"]} for a in w["top_acquirers"]],
                  "deals": [{"cluster_id": d["cluster_id"], "headline": d["headline"], "acquirer": d["acquirer"]["name"],
                             "target": d["target"]["name"],
                             "target_aum": aum_label(d["target_aum_usd"], d["target_aum_source"], snap.sec_date),
                             "deal_type": d["deal_type"], "confidence": d["confidence"],
                             "outlets": [s["name"] for s in d["sources"]],
                             "teasers": [wt[i] for i in snap.by_id[d["cluster_id"]]["item_ids"] if i in wt]}
                            for d in w["deals"]]}
        (work / WEEKLY_INPUT).write_text(json.dumps(winput, ensure_ascii=False, indent=1), encoding="utf-8")
        result.update(weekly=True, week=w["week"], deals=len(w["deals"]))
    return result


# ------------------------------------------------------------------------------------------------
# validation
# ------------------------------------------------------------------------------------------------
def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$%]+", (text or "").lower())


def _numbers(text: str) -> set[float]:
    out = set()
    for n in _NUM.findall(text or ""):
        try:
            out.add(float(n.replace(",", "")))
        except ValueError:
            pass
    return out


def sentences(text: str) -> int:
    return len(_SENT_END.findall(text.strip())) or 1


class Checker:
    """Rules shared by the digest and the weekly paragraph."""

    def __init__(self, blob: str, teasers: list[str], extra_numbers: set[float] = frozenset()):
        self.allowed = _numbers(blob) | set(extra_numbers)
        self.runs = set()
        for t in teasers:
            w = _words(t)
            for i in range(len(w) - TEASER_RUN + 1):
                self.runs.add(" ".join(w[i:i + TEASER_RUN]))

    def problems(self, label: str, text, max_chars: int, max_sentences: int, min_sentences: int = 1) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return [f"{label}: empty"]
        t = text.strip()
        out = []
        if len(t) > max_chars:
            out.append(f"{label}: longer than {max_chars} characters")
        n = sentences(t)
        if not (min_sentences <= n <= max_sentences):
            out.append(f"{label}: {n} sentences (expected {min_sentences}–{max_sentences})")
        if EMOJI.search(t):
            out.append(f"{label}: contains emoji")
        low = t.lower().replace("’", "'")
        for b in BANNED:
            if b in low:
                out.append(f"{label}: banned phrase {b!r}")
        for x in _numbers(t):
            if not any(abs(x - a) <= 0.051 or round(a) == x or round(a, 1) == x for a in self.allowed):
                out.append(f"{label}: number {x:g} is not in the input")
        w = _words(t)
        for i in range(len(w) - TEASER_RUN + 1):
            if " ".join(w[i:i + TEASER_RUN]) in self.runs:
                out.append(f"{label}: copies publisher teaser text")
                break
        return out


def validate_digest(output, inp: dict) -> list[str]:
    """[] if Claude's digest output is usable; otherwise the reasons it isn't."""
    if not isinstance(output, dict):
        return ["output is not a JSON object"]
    clusters = {c["id"]: c for c in inp["clusters"]}
    blob = json.dumps(inp, ensure_ascii=False)
    teasers = [t for c in inp["clusters"] for t in c["teasers"]]
    date_nums = {float(p) for p in inp["date"].split("-")}
    chk = Checker(blob, teasers, date_nums | {float(len(clusters))})  # AUM labels are in the blob
    problems = chk.problems("opener", output.get("opener"), 700, 4, 2)
    items = output.get("items")
    if not isinstance(items, list) or not items:
        return problems + ["items: missing or empty"]
    seen = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            problems.append(f"items[{i}]: not an object")
            continue
        cid = it.get("cluster_id")
        if cid not in clusters:
            problems.append(f"items[{i}]: unknown cluster_id {cid!r}")
            continue
        if cid in seen:
            problems.append(f"items[{i}]: duplicate cluster_id {cid}")
        seen.add(cid)
        problems += chk.problems(f"cluster {cid} summary", it.get("summary"), 400, 2)
        problems += chk.problems(f"cluster {cid} why_it_matters", it.get("why_it_matters"), 350, 2)
    missing = set(clusters) - seen
    if missing:
        problems.append(f"no summary for clusters {sorted(missing)}")
    return problems


def validate_weekly(output, winput: dict) -> list[str]:
    if not isinstance(output, dict):
        return ["output is not a JSON object"]
    blob = json.dumps(winput, ensure_ascii=False)
    teasers = [t for d in winput["deals"] for t in d["teasers"]]
    extra = {float(winput["deal_count"]), float(winput["disclosed_aum_deals"])}
    extra |= {float(p) for p in winput["start"].split("-") + winput["end"].split("-")}
    extra |= {float(a["deals"]) for a in winput["top_acquirers"]}
    return Checker(blob, teasers, extra).problems("paragraph", output.get("paragraph"), 1200, 6, 1)


# ------------------------------------------------------------------------------------------------
# finalize
# ------------------------------------------------------------------------------------------------
def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def render_markdown(d: dict, sec_date: str | None) -> str:
    from .sitebuild import FOOTER_NOTE

    lines = [f"# Fiduciary Wire digest: {d['date']}", "", f"**Today in wealth management.** {d['opener']}", ""]
    for n, it in enumerate(d["items"], 1):
        meta = [it["category"], f"{it['outlet_count']} outlet{'s' if it['outlet_count'] != 1 else ''}"]
        a = aum_label(it["aum_usd"], it["aum_source"], sec_date)
        if a:
            meta.append(a)
        lines += [f"## {n}. {it['headline']}", " · ".join(meta),
                  "Sources: " + " · ".join(f"[{s['name']}]({s['url']})" for s in it["sources"]), "",
                  it["summary"], "", f"**Why it matters to advisors:** {it['why_it_matters']}", ""]
    lines += ["---", f"_{FOOTER_NOTE}_", ""]
    return "\n".join(lines)


def finalize(conn: sqlite3.Connection, now: datetime | None = None, work: Path | None = None) -> dict:
    """Validate Claude's output and archive it. Never raises: returns a status dict."""
    from .sitebuild import Snapshot, public_item

    now = now or utcnow()
    work = work or paths.work_dir()
    status: dict = {"digest": "no input", "weekly": None}
    inp = _read(work / INPUT)
    cfg = load_config()
    snap = Snapshot(conn, cfg, now)
    if inp is not None:
        out_path = work / OUTPUT
        if not inp["clusters"]:
            status["digest"] = "no new stories in the Top Stories window"
        elif not out_path.exists():
            status["digest"] = "fallback: Claude did not run or wrote no output"
        else:
            out = _read(out_path)
            problems = ["output is not valid JSON"] if out is None else validate_digest(out, inp)
            if problems:
                status["digest"] = "fallback: " + "; ".join(problems[:5])
            else:
                by_id = {it["cluster_id"]: it for it in out["items"]}
                items = []
                for c in inp["clusters"]:
                    cl = snap.by_id.get(c["id"])
                    if cl:
                        items.append(public_item(cl) | {"summary": by_id[c["id"]]["summary"].strip(),
                                                        "why_it_matters": by_id[c["id"]]["why_it_matters"].strip()})
                d = {"schema_version": 1, "date": inp["date"], "generated_at": to_iso(now), "ai": True,
                     "opener": out["opener"].strip(), "items": items, "more": []}
                ddir = paths.digests_dir()
                ddir.mkdir(parents=True, exist_ok=True)
                text = json.dumps(d, ensure_ascii=False, indent=1) + "\n"
                (ddir / f"{inp['date']}.json").write_text(text, encoding="utf-8")
                (ddir / "latest.json").write_text(text, encoding="utf-8")
                (ddir / f"{inp['date']}.md").write_text(render_markdown(d, snap.sec_date), encoding="utf-8")
                status["digest"] = f"ok: {len(items)} stories"
    winput = _read(work / WEEKLY_INPUT)
    if winput is not None:
        w = weekly_data(snap, now)
        wdir = paths.weekly_dir()
        wdir.mkdir(parents=True, exist_ok=True)
        target = wdir / f"{w['week']}.json"
        wout = _read(work / WEEKLY_OUTPUT)
        problems = ["Claude did not run or wrote no output"] if wout is None else validate_weekly(wout, winput)
        if not problems:
            w.update(paragraph=wout["paragraph"].strip(), ai=True)
            status["weekly"] = f"ok: {w['week']}, {len(w['deals'])} deals"
        else:
            prev = _read(target)
            same = prev and prev.get("ai") and sorted(d["cluster_id"] for d in prev["deals"]) == sorted(
                d["cluster_id"] for d in w["deals"])
            if same:  # an earlier Friday run already wrote a good paragraph for exactly these deals
                w.update(paragraph=prev["paragraph"], ai=True)
            status["weekly"] = f"fallback{' (kept earlier paragraph)' if same else ''}: " + "; ".join(problems[:5])
        target.write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    db.set_meta(conn, "digest_status", json.dumps(status))
    conn.commit()
    return status
