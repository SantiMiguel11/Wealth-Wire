"""RIA map: projection, ZIP geocoding, Form ADV profile parse, and the public map files."""
import json
import re
from pathlib import Path

import pytest

from fiduciarywire.geo import albers_usa, fan_out, parse_gazetteer
from fiduciarywire.riamap import F_PAGE, FIELDS, focus_of

STATES = json.loads((Path(__file__).resolve().parent.parent / "frontend" / "us-states.json").read_text())


def _rings(d):
    return [[tuple(map(float, p.split())) for p in r.split("L")] for r in re.findall(r"M([^Z]+)Z", d)]


def _inside(pt, rings):
    x, y = pt
    c = False
    for r in rings:
        for i in range(len(r)):
            (x1, y1), (x2, y2) = r[i], r[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                c = not c
    return c


@pytest.mark.parametrize("state,lon,lat", [
    ("Washington", -122.33, 47.61), ("New York", -74.0, 40.75), ("Florida", -80.19, 25.77), ("Texas", -97.74, 30.27),
    ("Illinois", -87.63, 41.88), ("Alaska", -149.9, 61.22), ("Hawaii", -157.86, 21.31), ("Maine", -70.26, 43.66),
    ("California", -118.24, 34.05), ("Colorado", -104.99, 39.74), ("Kansas", -94.67, 38.98), ("Vermont", -73.21, 44.48),
])
def test_projection_matches_the_state_outlines(state, lon, lat):
    """Our Albers USA puts each city inside its own state as drawn by us-atlas (projected by d3 the same way)."""
    shapes = {s["name"]: _rings(s["d"]) for s in STATES["states"]}
    pt = albers_usa(lon, lat)
    assert pt and _inside(pt, shapes[state])


def test_projection_has_no_inset_for_territories():
    assert albers_usa(-66.1, 18.4) is None            # Puerto Rico
    assert albers_usa(-0.12, 51.5) is None            # London


def test_fan_out_spreads_firms_sharing_a_zip_deterministically():
    pts = fan_out([("1", 10.0, 10.0), ("3", 10.0, 10.0), ("2", 10.0, 10.0), ("9", 50.0, 50.0)])
    assert pts["1"] == (10.0, 10.0) and pts["9"] == (50.0, 50.0)
    assert len({pts[k] for k in "123"}) == 3 and fan_out([("2", 10.0, 10.0), ("1", 10.0, 10.0), ("3", 10.0, 10.0)]) == {
        k: pts[k] for k in "123"}


def test_gazetteer_parse(tmp_path):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("2024_Gaz_zcta_national.txt", "GEOID\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG  \n"
                                                  "00601\t1\t0\t0\t0\t18.180555\t-66.749961  \n10022\t1\t0\t0\t0\t40.758\t-73.968\n")
    assert parse_gazetteer(buf.getvalue()) == [("00601", 18.180555, -66.749961), ("10022", 40.758, -73.968)]


@pytest.mark.parametrize("mix,focus", [
    ({"a": 1, "b": 5, "g": 2}, 0), ({"f": 9, "b": 1}, 1), ({"g": 5, "m": 3, "b": 2}, 2), ({}, 3), (None, 3)])
def test_focus_by_client_aum(mix, focus):
    assert focus_of(mix) == focus


def test_profile_parse_from_real_headers():
    """The real file's headers (probe of 2026-10-27): Y/N flags, numbers with commas and spaces, MM/DD/YYYY dates."""
    from datetime import date

    from fiduciarywire.sec import _rows_from_table

    hdr = ["Organization CRD#", "SEC#", "Primary Business Name", "Legal Name", "Main Office City", "Main Office State",
           "Main Office Country", "Main Office Postal Code", "SEC Status Effective Date", "Website Address", "3A", "5A",
           "5B(1)", "5C(1)", "5D(a)(3)", "5D(b)(3)", "5E(1)", "5F(2)(a)", "5F(2)(c)", "5F(2)(f)", "5G(1)", "5G(2)", "5G(3)",
           "6A(6)", "Count of Private Funds - 7B(1)", "11"]
    row = ["38", "801-57838", "AMERICAN INVESTORS CO", "L.S.Y., INC", "SAN RAMON", "CA", "United States", "94583-1234",
           "08/22/2000", "HTTPS://WWW.EXAMPLE.COM", "Corporation", "32", "32", " 18", "   163,209,871.00", "  434,165,916.00",
           "Y", "  628,902,725.00", "  630,665,806.00", "      1,554", "Y", "Y", "N", "Y", "  0", "N"]
    [r] = _rows_from_table([hdr, row], date(2026, 9, 1))
    assert (r["zip"], r["country"], r["aum_usd"]) == ("94583", "United States", 630665806.0)
    p = json.loads(r["profile"])
    assert p["registered"] == "2000-08-22" and p["website"] == "https://www.example.com" and p["employees"] == 32
    assert p["clients"] == 18 and p["accounts"] == 1554 and p["services"] == [1, 2] and p["compensation"] == [1]
    assert p["other_business"] == [6] and p["client_aum"] == {"a": 163209871.0, "b": 434165916.0} and p["disclosures"] is False


def test_withheld_main_office_falls_back_to_books_and_records():
    """Probe of 2026-10-27: for home-based advisers the SEC blanks every Main Office field (private residence flag)
    but still publishes where the books and records are kept. That ZIP places the firm, marked approximate;
    a firm with neither stays off the map."""
    from datetime import date

    from fiduciarywire.sec import _rows_from_table

    hdr = ["Organization CRD#", "SEC#", "Primary Business Name", "Legal Name", "Main Office City", "Main Office State",
           "Main Office Country", "Main Office Postal Code", "Main Office Private Residence Flag",
           "Location of Books and Records City", "Location of Books and Records State",
           "Location of Books and Records Country", "Location of Books and Records Postal Code", "5F(2)(c)"]
    rows = [hdr,
            ["45348", "801-108980", "SUPREME ALLIANCE LLC", "SUPREME ALLIANCE LLC", "", "", "", "", "Y",
             "CHARLOTTE", "NC", "United States", "28277", "35,314,242"],
            ["108583", "801-1", "VALLEY VIEW CONSULTING LLC", "VALLEY VIEW CONSULTING LLC", "", "", "", "", "Y",
             "", "", "", "", "16,400,000,000"],
            ["38", "801-57838", "AMERICAN INVESTORS CO", "L.S.Y., INC", "SAN RAMON", "CA", "United States", "94583", "N",
             "WALNUT CREEK", "CA", "United States", "94596", "1"]]
    a, b, c = _rows_from_table(rows, date(2026, 9, 1))
    assert (a["city"], a["state"], a["zip"], a["country"]) == ("CHARLOTTE", "NC", "28277", "United States")
    assert json.loads(a["profile"])["approx_location"] is True
    assert (b["city"], b["zip"], b["country"]) == (None, None, None) and "approx_location" not in json.loads(b["profile"])
    assert (c["city"], c["zip"]) == ("SAN RAMON", "94583") and "approx_location" not in json.loads(c["profile"])


def test_map_files(ingested):
    from fiduciarywire import db
    from fiduciarywire.sitebuild import collect

    from .conftest import NOW

    files = collect(db.connect(), NOW)
    m = files["riamap.json"]
    assert m["fields"] == FIELDS and m["width"] == 975
    assert m["counts"] == {"advisers": 621, "mapped": 620, "unmapped": 1,    # the London adviser has no US spot
                           "approximate": 0, "no_address": 0}
    rows = {r[1]: r for r in m["firms"]}
    hv = rows["Harborview Wealth Partners"]
    assert hv[5:7] == ["Seattle", "WA"] and hv[4] == 9.8e9 and hv[9] & F_PAGE     # in the news → has a firm page
    assert [r[4] for r in m["firms"]] == sorted((r[4] for r in m["firms"]), reverse=True)
    assert all(0 <= r[2] <= 975 and 0 <= r[3] <= 610 for r in m["firms"])
    # firms sharing a ZIP don't share a pixel
    assert len({(r[2], r[3]) for r in m["firms"]}) == len(m["firms"])
    d = files[f"riamap/details-{hv[0] % m['shards']:02d}.json"]["firms"][str(hv[0])]
    assert d["slug"] and d["iapd_url"].endswith(str(hv[0])) and d["deals"][0]["role"] == "acquirer"
    assert d["website"].startswith("https://") and d["client_mix"] and d["services"]
    # never a street address
    assert "street" not in json.dumps(files["riamap.json"]).lower()


def test_map_files_match_the_contract(ingested, tmp_path):
    from fiduciarywire.contract import validate_data_dir
    from fiduciarywire.sitebuild import build_site

    from .conftest import NOW

    build_site(tmp_path / "out", now=NOW, write_state=False)
    data = tmp_path / "out" / "site" / "data"
    assert (data / "riamap.json").exists() and len(list((data / "riamap").glob("details-*.json"))) == 32
    assert [p for p in validate_data_dir(data) if "riamap" in p] == []
