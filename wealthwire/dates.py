"""Date parsing for feeds and listing pages. Everything is stored as ISO-8601 UTC ('...Z')."""
from __future__ import annotations

import calendar
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_tz, mktime_tz
from zoneinfo import ZoneInfo

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(ISO_FMT)


def from_iso(value: str) -> datetime:
    return datetime.strptime(value, ISO_FMT).replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def from_struct(st: time.struct_time | None) -> datetime | None:
    """feedparser's *_parsed values are already normalized to UTC."""
    if not st:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
    except (OverflowError, ValueError):
        return None


_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
_HUMAN = re.compile(rf"\b({_MONTHS})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
_NUMERIC = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def parse_date(value: str | None, local_tz: str = "America/Los_Angeles") -> datetime | None:
    """Parse RFC-822, ISO-8601 and common human formats. Naive values are read in `local_tz`."""
    if not value:
        return None
    value = value.strip()
    tz = ZoneInfo(local_tz)
    # RFC 822 / 2822
    parsed = parsedate_tz(value)
    if parsed and parsed[9] is not None:
        return datetime.fromtimestamp(mktime_tz(parsed), tz=timezone.utc)
    # ISO 8601
    iso = value.replace("Z", "+00:00").replace("z", "+00:00")
    if re.match(r"^\d{4}-\d{2}-\d{2}", iso):
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    if parsed:  # RFC-like without zone
        dt = datetime(*parsed[:6], tzinfo=tz)
        return dt.astimezone(timezone.utc)
    m = _HUMAN.search(value)
    if m:
        mon = m.group(1)[:3].lower()
        month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(mon) + 1
        try:
            dt = datetime(int(m.group(3)), month, int(m.group(2)), tzinfo=tz)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    m = _NUMERIC.search(value)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=tz)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def sane_published(dt: datetime | None, fetched: datetime) -> tuple[datetime, bool]:
    """Return (published, estimated). Missing or >1 day in the future → fetched time, estimated."""
    if dt is None:
        return fetched, True
    if dt > fetched + timedelta(days=1):
        return fetched, True
    return dt, False
