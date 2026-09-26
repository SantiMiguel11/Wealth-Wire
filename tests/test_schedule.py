"""§1: refresh schedule (UTC crons → Pacific local times) and the Top Stories window."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from wealthwire import db
from wealthwire.dates import to_iso
from wealthwire.window import rank_clusters, top_window

ROOT = Path(__file__).resolve().parent.parent
PT = ZoneInfo("America/Los_Angeles")


def _expand(field: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in field.split(","):
        if part == "*":
            out |= set(range(lo, hi + 1))
        elif "-" in part:
            a, b = map(int, part.split("-"))
            out |= set(range(a, b + 1))
        else:
            out.add(int(part))
    return out


def cron_fires(expr: str, t: datetime) -> bool:
    minute, hour, dom, month, dow = expr.split()
    cron_dow = (t.weekday() + 1) % 7  # cron: 0 = Sunday
    return (t.minute in _expand(minute, 0, 59) and t.hour in _expand(hour, 0, 23) and t.day in _expand(dom, 1, 31)
            and t.month in _expand(month, 1, 12) and cron_dow in _expand(dow, 0, 6))


def local_runs(week_start_utc: datetime) -> set[tuple[str, int]]:
    wf = yaml.safe_load((ROOT / ".github/workflows/refresh-site.yml").read_text())
    crons = [c["cron"] for c in wf[True]["schedule"]]  # PyYAML parses the `on:` key as True
    runs = set()
    t = week_start_utc
    while t < week_start_utc + timedelta(days=7):
        if any(cron_fires(c, t) for c in crons):
            local = t.astimezone(PT)
            runs.add((local.strftime("%a"), local.hour))
        t += timedelta(minutes=1)
    return runs


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def test_schedule_in_daylight_time():
    runs = local_runs(datetime(2026, 7, 6, tzinfo=timezone.utc))  # a July week (PDT)
    expected = {(d, h) for d in WEEKDAYS for h in (6, 12, 17)} | {("Sat", 8), ("Sun", 8)}
    assert runs == expected


def test_schedule_drifts_one_hour_earlier_in_standard_time():
    runs = local_runs(datetime(2026, 1, 5, tzinfo=timezone.utc))  # a January week (PST)
    expected = {(d, h) for d in WEEKDAYS for h in (5, 11, 16)} | {("Sat", 7), ("Sun", 7)}
    assert runs == expected


def test_workflow_has_dispatch_and_concurrency():
    wf = yaml.safe_load((ROOT / ".github/workflows/refresh-site.yml").read_text())
    assert "workflow_dispatch" in wf[True]
    assert wf["concurrency"]["group"] and wf["concurrency"]["cancel-in-progress"] is False


def test_window_minimum_24h(home):
    conn = db.connect()
    now = datetime(2026, 9, 28, 13, 7, tzinfo=timezone.utc)  # Monday 6:07 PDT
    assert top_window(conn, now) == now - timedelta(hours=24)                      # no previous refresh
    db.set_meta(conn, "previous_success", to_iso(now - timedelta(hours=6)))        # weekday: 6h ago
    assert top_window(conn, now) == now - timedelta(hours=24)                      # still at least 24h
    db.set_meta(conn, "previous_success", to_iso(now - timedelta(hours=53)))       # a missed/failed run
    assert top_window(conn, now) == now - timedelta(hours=53)                      # covers the gap


def test_rank_by_outlets_then_recency():
    cs = [{"id": 1, "outlet_count": 1, "last_published": "2026-09-26T10:00:00Z"},
          {"id": 2, "outlet_count": 3, "last_published": "2026-09-25T10:00:00Z"},
          {"id": 3, "outlet_count": 1, "last_published": "2026-09-26T12:00:00Z"}]
    assert [c["id"] for c in rank_clusters(cs)] == [2, 3, 1]


def test_top_stories_only_new_since_window(ingested):
    from wealthwire.sitebuild import collect

    from .conftest import NOW

    conn = db.connect()
    # everything in the fixture DB was first seen at NOW
    db.set_meta(conn, "previous_success", to_iso(NOW + timedelta(hours=1)))
    conn.commit()
    soon = collect(conn, NOW + timedelta(hours=2))["digest.json"]
    assert soon["items"], "the 24h minimum still covers stories first seen 2h ago"
    later = collect(conn, NOW + timedelta(hours=26))["digest.json"]   # window starts at the previous refresh (NOW+1h)
    assert later["items"] == [] and later["ai"] is False
    first = collect(conn, NOW + timedelta(minutes=1))
    assert first["digest.json"]["items"], "a run right after ingestion sees the new stories"
    outlets = [i["outlet_count"] for i in first["digest.json"]["items"]]
    assert outlets == sorted(outlets, reverse=True)
