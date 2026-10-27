"""Build frontend/us-states.json (state outlines as SVG path strings in the 975×610 Albers USA frame) from
us-atlas's states-albers-10m.json (ISC license; Census cartographic boundaries 2017, projected with
d3.geoAlbersUsa().scale(1300).translate([487.5, 305])).

    python scripts/build_us_states.py path/to/us-atlas/states-albers-10m.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "us-states.json"


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:          # delta-encoded, quantized
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring(arcs, idx: list[int]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in idx:
        pts = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
        out.extend(pts if not out else pts[1:])
    return out


def path(rings: list[list[tuple[float, float]]]) -> str:
    parts = []
    for r in rings:
        pts = []
        for x, y in r:
            p = (round(x, 1), round(y, 1))
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) >= 3:
            parts.append("M" + "L".join(f"{x:g} {y:g}" for x, y in pts) + "Z")
    return "".join(parts)


def main(src: str) -> int:
    topo = json.loads(Path(src).read_text())
    arcs = decode_arcs(topo)
    states = []
    for g in topo["objects"]["states"]["geometries"]:
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        rings = [ring(arcs, r) for poly in polys for r in poly]
        states.append({"id": g["id"], "name": g["properties"]["name"], "d": path(rings)})
    nation = topo["objects"]["nation"]["geometries"][0]
    npolys = nation["arcs"] if nation["type"] == "MultiPolygon" else [nation["arcs"]]
    out = {"source": "us-atlas 3.0.1 states-albers-10m (ISC, © Michael Bostock; U.S. Census Bureau cartographic boundaries 2017)",
           "projection": "d3.geoAlbersUsa().scale(1300).translate([487.5, 305])", "width": 975, "height": 610,
           "nation": path([ring(arcs, r) for poly in npolys for r in poly]),
           "states": sorted(states, key=lambda s: s["id"])}
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"{len(states)} states → {OUT.relative_to(OUT.parent.parent)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
