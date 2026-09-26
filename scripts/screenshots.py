"""Playwright UI check: screenshots of every main view at desktop + mobile, light + dark.

Starts its own server on a fresh copy of the offline fixture data (DEMO), so it needs no network:
    python scripts/screenshots.py            # → screenshots/*.png, exits 1 on any console error / failed request

Use --base-url to point it at an already-running server instead.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "screenshots"
DEMO_HOME = ROOT / "demo"
VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844)}
THEMES = ("light", "dark")
SCENES = [
    # name, query string, optional action
    ("feed", "", None),
    ("feed-filtered", "?category=M%26A,People+Moves&source=Citywire+RIA", None),
    ("search", "?q=custody+rule", None),
    ("watchlist", "?watch=1", None),
    ("mna", "?tab=mna", None),
    ("mna-low", "?tab=mna&conf=low", None),
    ("digest", "?tab=digest", None),
    ("sources", "?tab=sources", None),
    ("empty", "?q=zzzznotaword", None),
]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def prepare_demo() -> dict:
    """Fresh demo data dir + config copy (watchlist edits in the UI must not touch the repo)."""
    if DEMO_HOME.exists():
        keep = DEMO_HOME / "digests"
        saved = {p.name: p.read_bytes() for p in keep.glob("*.md")} if keep.exists() else {}
        last = (keep / ".last_digest").read_bytes() if (keep / ".last_digest").exists() else None
        shutil.rmtree(DEMO_HOME)
    else:
        saved, last = {}, None
    cfg = DEMO_HOME / "config"
    cfg.mkdir(parents=True)
    for name in ("config.yaml", "sources.yaml", "watchlist.yaml", "categories.yaml", "firm_stoplist.yaml"):
        shutil.copy(ROOT / name, cfg / name)
    (DEMO_HOME / "digests").mkdir()
    for n, b in saved.items():
        (DEMO_HOME / "digests" / n).write_bytes(b)
    if last is not None:
        (DEMO_HOME / "digests" / ".last_digest").write_bytes(last)
    env = dict(os.environ, WEALTHWIRE_HOME=str(DEMO_HOME), WEALTHWIRE_CONFIG=str(cfg), WEALTHWIRE_NO_BACKGROUND="1")
    subprocess.run([sys.executable, "-m", "wealthwire", "ingest", "--fixtures", str(ROOT / "tests/fixtures/demo")],
                   cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    return env


def start_server(env: dict) -> tuple[subprocess.Popen, str]:
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "wealthwire", "serve", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc, base
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("server did not start")


def launch(p):
    """Default Playwright Chromium; fall back to an explicit binary (WW_CHROMIUM or a preinstalled one)."""
    exe = os.environ.get("WW_CHROMIUM")
    if not exe:
        try:
            return p.chromium.launch()
        except Exception:
            exe = next((c for c in ("/opt/pw-browsers/chromium/chrome-linux/chrome", "/opt/pw-browsers/chromium") if Path(c).is_file()), None)
            if not exe:
                raise
    return p.chromium.launch(executable_path=exe)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url")
    ap.add_argument("--only", help="comma-separated scene names")
    args = ap.parse_args()

    proc = None
    if args.base_url:
        base = args.base_url.rstrip("/")
    else:
        proc, base = start_server(prepare_demo())
    OUT.mkdir(exist_ok=True)
    problems: list[str] = []
    shots = 0
    scenes = [s for s in SCENES if not args.only or s[0] in args.only.split(",")]
    try:
        with sync_playwright() as p:
            browser = launch(p)
            for theme in THEMES:
                for vp_name, (w, h) in VIEWPORTS.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=theme, device_scale_factor=1)
                    page = ctx.new_page()
                    page.on("console", lambda m, t=theme, v=vp_name: m.type == "error" and problems.append(f"[{t}/{v}] console: {m.text}"))
                    page.on("pageerror", lambda e, t=theme, v=vp_name: problems.append(f"[{t}/{v}] pageerror: {e}"))
                    page.on("requestfailed", lambda r, t=theme, v=vp_name: problems.append(f"[{t}/{v}] requestfailed: {r.url} {r.failure}"))
                    page.on("response", lambda r, t=theme, v=vp_name: r.status >= 400 and problems.append(f"[{t}/{v}] HTTP {r.status}: {r.url}"))
                    for name, qs, _ in scenes:
                        page.goto(base + "/" + qs)
                        page.wait_for_load_state("networkidle")
                        page.wait_for_function("!document.querySelector('.skeleton')")
                        # horizontal overflow check
                        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                        if overflow > 0:
                            problems.append(f"[{theme}/{vp_name}] {name}: horizontal overflow {overflow}px")
                        page.screenshot(path=str(OUT / f"{name}-{vp_name}-{theme}.png"))
                        shots += 1
                    ctx.close()
            # error state: API forced to fail (deliberate, so not counted as a problem)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
            page = ctx.new_page()
            page.route("**/api/feed*", lambda route: route.fulfill(status=500, json={"detail": "database is locked"}))
            page.goto(base + "/")
            page.wait_for_selector(".state.error")
            page.screenshot(path=str(OUT / "error-desktop-light.png"))
            ctx.close()
            # interactions: filter/search state lives in the URL; watchlist add/remove from the UI
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
            page = ctx.new_page()
            page.on("console", lambda m: m.type == "error" and problems.append(f"[interact] console: {m.text}"))
            page.goto(base + "/")
            page.wait_for_selector(".card")
            page.fill("#q", "custody")
            page.wait_for_url("**q=custody**")
            page.wait_for_function("document.querySelectorAll('#feed-list .card').length === 3")  # porter stemming: custody ~ custodian
            page.click('#cat-chips button[data-cat="Regulation"]')
            page.wait_for_url("**category=Regulation**")
            page.go_back()
            page.wait_for_function("!location.search.includes('category')")
            page.select_option("#source", "Kitces")
            page.wait_for_url("**source=Kitces**")
            page.click("#clear")
            page.wait_for_function("location.search === ''")
            page.fill("#watch-name", "Harborview Wealth Partners")
            page.fill("#watch-aliases", "Harborview")
            page.click("#watch-add button")
            page.wait_for_selector("#watchlist li:has-text('Harborview Wealth Partners')")
            page.wait_for_selector("#pinned-list .card:has-text('Summit Ridge')")
            page.evaluate("scrollTo(0, 0)")
            page.screenshot(path=str(OUT / "watchlist-added-desktop-light.png"))
            page.click("#watchlist button[aria-label='Remove Harborview Wealth Partners']")
            page.wait_for_function("!document.querySelector('#watchlist').textContent.includes('Harborview')")
            page.wait_for_function("!document.querySelector('#pinned-list').textContent.includes('Summit Ridge')")
            ctx.close()
            # theme toggle persists in localStorage
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
            page = ctx.new_page()
            page.on("console", lambda m: m.type == "error" and problems.append(f"[toggle] console: {m.text}"))
            page.goto(base + "/")
            page.click("#theme-toggle")
            page.reload()
            if page.evaluate("document.documentElement.dataset.theme") != "dark":
                problems.append("theme toggle did not persist across reload")
            ctx.close()
            browser.close()
    finally:
        if proc:
            proc.terminate()
    print(f"{shots} screenshots → {OUT.relative_to(ROOT)}/")
    if problems:
        print(f"{len(problems)} problem(s):")
        for p_ in problems:
            print("  " + p_)
        return 1
    print("0 console errors, 0 failed requests, no horizontal overflow")
    (OUT / "playwright-report.json").write_text(json.dumps({"screenshots": shots, "problems": problems}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
