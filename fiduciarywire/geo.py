"""Geocoding for the RIA map: Census ZIP centroids → map coordinates.

- ZIP centroids come from the Census Bureau's ZCTA gazetteer (public domain), downloaded once into the `zcta`
  table, which travels with the private state; it is refreshed when it is more than a year old.
- Every firm is placed at its main-office ZIP's centroid, never at a street address (many advisers work from
  home; the SEC file flags private residences). Firms sharing a ZIP are fanned out around it.
- Coordinates are projected with the same composite Albers USA projection d3 uses
  (d3.geoAlbersUsa().scale(1300).translate([487.5, 305])), so they line up with the state outlines in
  frontend/us-states.json (us-atlas, projected the same way) in a 975×610 frame.
"""
from __future__ import annotations

import io
import math
import sqlite3
import zipfile
from datetime import datetime, timedelta

from . import db
from .dates import from_iso, to_iso

ZCTA_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"
WIDTH, HEIGHT = 975, 610
_K, _TX, _TY = 1300.0, 487.5, 305.0
_R = math.pi / 180


class _ConicEqualArea:
    """d3.geoConicEqualArea with rotate([λ, 0]), center([cλ, cφ]), parallels, scale and translate."""

    def __init__(self, rotate: float, center: tuple[float, float], parallels: tuple[float, float], scale: float,
                 translate: tuple[float, float]):
        y0, y1 = parallels[0] * _R, parallels[1] * _R
        sy0 = math.sin(y0)
        self.n = (sy0 + math.sin(y1)) / 2
        self.c = 1 + sy0 * (2 * self.n - sy0)
        self.r0 = math.sqrt(self.c) / self.n
        self.dl = rotate * _R
        self.k = scale
        cx, cy = self._raw(center[0] * _R, center[1] * _R)
        self.dx = translate[0] - scale * cx
        self.dy = translate[1] + scale * cy

    def _raw(self, x: float, y: float) -> tuple[float, float]:
        r = math.sqrt(max(self.c - 2 * self.n * math.sin(y), 0)) / self.n
        return r * math.sin(x * self.n), self.r0 - r * math.cos(x * self.n)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        lam = lon * _R + self.dl
        lam = (lam + math.pi) % (2 * math.pi) - math.pi        # d3 wraps the rotated longitude to [-π, π]
        x, y = self._raw(lam, lat * _R)
        return self.dx + self.k * x, self.dy - self.k * y


_LOWER48 = _ConicEqualArea(96, (-0.6, 38.7), (29.5, 45.5), _K, (_TX, _TY))
_ALASKA = _ConicEqualArea(154, (-2, 58.5), (55, 65), _K * 0.35, (_TX - 0.307 * _K, _TY + 0.201 * _K))
_HAWAII = _ConicEqualArea(157, (-3, 19.9), (8, 18), _K, (_TX - 0.205 * _K, _TY + 0.212 * _K))
_EXTENTS = [  # d3's clip extents decide which inset a point belongs to
    (_LOWER48, (_TX - 0.455 * _K, _TY - 0.238 * _K, _TX + 0.455 * _K, _TY + 0.238 * _K)),
    (_ALASKA, (_TX - 0.425 * _K, _TY + 0.120 * _K, _TX - 0.214 * _K, _TY + 0.234 * _K)),
    (_HAWAII, (_TX - 0.214 * _K, _TY + 0.166 * _K, _TX - 0.115 * _K, _TY + 0.234 * _K)),
]


def albers_usa(lon: float, lat: float) -> tuple[float, float] | None:
    """Project a point like d3.geoAlbersUsa().scale(1300).translate([487.5, 305]); None outside the three insets
    (Puerto Rico, Guam and other territories have no inset)."""
    for proj, (x0, y0, x1, y1) in _EXTENTS:
        x, y = proj(lon, lat)
        if x0 <= x <= x1 and y0 <= y <= y1:
            return x, y
    return None


# ------------------------------------------------------------------------------------------------
# ZIP centroids
# ------------------------------------------------------------------------------------------------
def parse_gazetteer(content: bytes) -> list[tuple[str, float, float]]:
    """Census ZCTA gazetteer zip → [(zip, lat, lon)]. Tab-separated: GEOID … INTPTLAT INTPTLONG."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        lines = zf.read(name).decode("utf-8", errors="replace").splitlines()
    head = [h.strip().upper() for h in lines[0].split("\t")]
    gi, la, lo = head.index("GEOID"), head.index("INTPTLAT"), head.index("INTPTLONG")
    out = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) <= max(gi, la, lo) or not parts[gi].isdigit():
            continue
        try:
            out.append((parts[gi].zfill(5), float(parts[la]), float(parts[lo])))
        except ValueError:
            continue
    return out


def maybe_update_zcta(conn: sqlite3.Connection, fetcher, now: datetime, url: str = ZCTA_URL, min_rows: int = 1000) -> dict:
    """Load the ZIP centroid table when it is empty or over a year old. Never raises."""
    count = conn.execute("SELECT COUNT(*) FROM zcta").fetchone()[0]
    loaded = db.get_meta(conn, "zcta_loaded_at")
    if count and loaded and now - from_iso(loaded) < timedelta(days=365):
        return {"status": "cached", "zips": count}
    try:
        allowed, why = fetcher.robots.check(url)
        if not allowed:
            return {"status": "failed", "reason": f"{url}: {why}", "zips": count}
        res = fetcher.get(url)
        if not res.ok:
            return {"status": "failed", "reason": f"{url}: {res.describe_failure()}", "zips": count}
        rows = parse_gazetteer(res.content)
        if len(rows) < min_rows:
            return {"status": "failed", "reason": f"{url}: only {len(rows)} ZIPs parsed", "zips": count}
        conn.execute("DELETE FROM zcta")
        conn.executemany("INSERT OR REPLACE INTO zcta(zip, lat, lon) VALUES (?,?,?)", rows)
        db.set_meta(conn, "zcta_loaded_at", to_iso(now))
        conn.commit()
        return {"status": "updated", "zips": len(rows)}
    except Exception as exc:  # the map is optional; never break a refresh over it
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}", "zips": count}


def zip_points(conn: sqlite3.Connection) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    """{zip5: (lat, lon)} and a ZIP3 fallback {zip3: mean (lat, lon)} for ZIPs the gazetteer lacks
    (PO-box-only and new ZIPs have no ZCTA)."""
    exact = {z: (la, lo) for z, la, lo in conn.execute("SELECT zip, lat, lon FROM zcta")}
    acc: dict[str, list[float]] = {}
    for z, (la, lo) in exact.items():
        a = acc.setdefault(z[:3], [0.0, 0.0, 0.0])
        a[0] += la
        a[1] += lo
        a[2] += 1
    return exact, {k: (a[0] / a[2], a[1] / a[2]) for k, a in acc.items()}


GOLDEN = math.pi * (3 - math.sqrt(5))


def fan_out(points: list[tuple[str, float, float]], spacing: float = 0.55) -> dict[str, tuple[float, float]]:
    """Firms at the same spot → a sunflower around it (deterministic: ordered by key), so each stays clickable
    when zoomed in. `points` = [(key, x, y)] in map units; spacing in map units."""
    groups: dict[tuple[float, float], list[str]] = {}
    for key, x, y in points:
        groups.setdefault((round(x, 2), round(y, 2)), []).append(key)
    out: dict[str, tuple[float, float]] = {}
    for (x, y), keys in groups.items():
        for i, key in enumerate(sorted(keys)):
            if i == 0:
                out[key] = (x, y)
                continue
            r = spacing * math.sqrt(i)
            out[key] = (x + r * math.cos(i * GOLDEN), y + r * math.sin(i * GOLDEN))
    return out
