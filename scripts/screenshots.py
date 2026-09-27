"""Playwright UI check: screenshots of every main view at desktop + mobile, light + dark.

Starts its own server on a fresh copy of the offline fixture data (DEMO), with the clock pinned to the
fixtures' date and the demo digest from tests/fixtures/demo/*_output.json, so it needs no network:
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
DEMO_FIXTURES = ROOT / "tests" / "fixtures" / "demo"
VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844)}
THEMES = ("light", "dark")
SAMPLE_WATCHLIST = {"version": 1, "firms": [
    {"name": "Harborview Wealth Partners", "aliases": ["Harborview"]},
    {"name": "Crestline Wealth", "aliases": []},
]}
FIXED_NOW = "2026-09-25T18:00:00Z"
SCENES = [
    # name, path + query string ("{firm}" = a firm page slug)
    ("today", "/"),
    ("feed", "/?tab=feed"),
    ("feed-filtered", "/?tab=feed&category=M%26A,People+Moves&source=Citywire+RIA"),
    ("region", "/?tab=feed&region=Pacific+Northwest"),
    ("search", "/?tab=feed&q=custody+rule"),
    ("watchlist", "/?tab=feed&watch=1"),
    ("firm", "/firm/{firm}"),
    ("deals", "/?tab=mna"),
    ("deals-review", "/?tab=mna&conf=low"),
    ("archive", "/?tab=archive"),
    ("archive-day", "/?tab=today&date=2026-09-25"),
    ("weekly", "/?tab=weekly&week=2026-W39"),
    ("sources", "/?tab=sources"),
    ("empty", "/?tab=feed&q=zzzznotaword"),
]
TAP_CHECK = """() => {
  const bad = [];
  for (const e of document.querySelectorAll('.sections a, .textbtn, button, select, input:not([type=checkbox]):not([type=file]), .cat-toggles button, .footer-links a')) {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(e).visibility === 'hidden') continue;
    if (e.closest('.deals-table, [hidden]')) continue;
    if (r.height < 44) bad.push((e.id || e.className || e.tagName) + ' ' + Math.round(r.height) + 'px');
  }
  return bad.slice(0, 8);
}"""


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def prepare_demo() -> dict:
    """Fresh demo data dir: fixture ingest, then the demo digest through the real validate/archive step."""
    if DEMO_HOME.exists():
        shutil.rmtree(DEMO_HOME)
    cfg = DEMO_HOME / "config"
    cfg.mkdir(parents=True)
    for name in ("config.yaml", "sources.yaml", "categories.yaml", "firm_stoplist.yaml", "firm_aliases.yaml"):
        shutil.copy(ROOT / name, cfg / name)
    env = dict(os.environ, WEALTHWIRE_HOME=str(DEMO_HOME), WEALTHWIRE_CONFIG=str(cfg), WEALTHWIRE_NO_BACKGROUND="1",
               WEALTHWIRE_NOW=FIXED_NOW)
    run = lambda *a: subprocess.run([sys.executable, "-m", "wealthwire", *a], cwd=ROOT, env=env, check=True,  # noqa: E731
                                    stdout=subprocess.DEVNULL)
    run("ingest", "--fixtures", str(DEMO_FIXTURES))
    run("digest-input")
    for name in ("digest_output.json", "weekly_output.json"):
        shutil.copy(DEMO_FIXTURES / name, DEMO_HOME / "_work" / name)
    run("digest-finalize")
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


_FONT_CACHE: dict[str, tuple[int, dict, bytes]] = {}


def serve_fonts(ctx) -> None:
    """Google Fonts through Python (which trusts the sandbox's proxy CA), cached, so screenshots always get the
    real type instead of flaky browser-side proxy failures. Only used by this test script."""
    import httpx

    def handle(route):
        url = route.request.url
        if url not in _FONT_CACHE:
            try:
                r = httpx.get(url, headers={"User-Agent": route.request.headers.get("user-agent", "")}, timeout=20)
                _FONT_CACHE[url] = (r.status_code, {"content-type": r.headers.get("content-type", ""),
                                                    "access-control-allow-origin": "*"}, r.content)
            except httpx.HTTPError:
                return route.abort()
        status, headers, body = _FONT_CACHE[url]
        route.fulfill(status=status, headers=headers, body=body)

    ctx.route("https://fonts.googleapis.com/**", handle)
    ctx.route("https://fonts.gstatic.com/**", handle)


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
    seed = f"localStorage.setItem('ww-watchlist', {json.dumps(json.dumps(SAMPLE_WATCHLIST))})"
    try:
        with sync_playwright() as p:
            browser = launch(p)
            probe = browser.new_page()
            firms = probe.goto(base + "/data/firms/index.json").json()["firms"]
            firm = next(f["slug"] for f in firms if f["name"].startswith("Harborview"))
            probe.close()
            for theme in THEMES:
                for vp_name, (w, h) in VIEWPORTS.items():
                    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": w, "height": h}, color_scheme=theme, device_scale_factor=1)
                    serve_fonts(ctx)
                    ctx.add_init_script(seed)  # a sample watchlist, as if the visitor had added two firms
                    page = ctx.new_page()
                    page.on("console", lambda m, t=theme, v=vp_name: m.type == "error" and problems.append(f"[{t}/{v}] console: {m.text}"))
                    page.on("pageerror", lambda e, t=theme, v=vp_name: problems.append(f"[{t}/{v}] pageerror: {e}"))
                    page.on("requestfailed", lambda r, t=theme, v=vp_name: problems.append(f"[{t}/{v}] requestfailed: {r.url} {r.failure}"))
                    page.on("response", lambda r, t=theme, v=vp_name: r.status >= 400 and problems.append(f"[{t}/{v}] HTTP {r.status}: {r.url}"))
                    for name, path in scenes:
                        page.goto(base + path.format(firm=firm))
                        page.wait_for_load_state("networkidle")
                        page.wait_for_function("!document.querySelector('.skeleton')")
                        page.evaluate("document.fonts.ready")
                        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                        if overflow > 0:
                            problems.append(f"[{theme}/{vp_name}] {name}: horizontal overflow {overflow}px")
                        if vp_name == "mobile":
                            small = page.evaluate(TAP_CHECK)
                            if small:
                                problems.append(f"[{theme}/{vp_name}] {name}: tap targets under 44px: {small}")
                        page.screenshot(path=str(OUT / f"{name}-{vp_name}-{theme}.png"), full_page=vp_name == "desktop")
                        shots += 1
                    ctx.close()
            # error state: a data file forced to fail (deliberate, so not counted as a problem)
            ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}, color_scheme="light")
            serve_fonts(ctx)
            page = ctx.new_page()
            page.route("**/data/clusters.json", lambda route: route.fulfill(status=500, body="error"))
            page.goto(base + "/?tab=feed")
            page.wait_for_selector(".state.error")
            if "clusters.json" not in page.inner_text(".state.error"):
                problems.append("error state does not name the file that failed")
            page.screenshot(path=str(OUT / "error-desktop-light.png"))
            ctx.close()
            # interactions: URL-held filters; watchlist drawer (add/pin/export/remove/import, Esc, focus trap)
            for vp_name, (w, h) in VIEWPORTS.items():
                ctx = browser.new_context(ignore_https_errors=True, viewport={"width": w, "height": h}, color_scheme="light", accept_downloads=True)
                serve_fonts(ctx)
                page = ctx.new_page()
                page.on("console", lambda m: m.type == "error" and problems.append(f"[interact] console: {m.text}"))
                page.on("pageerror", lambda e: problems.append(f"[interact] pageerror: {e}"))
                page.goto(base + "/?tab=feed")
                page.wait_for_selector("#feed-list .row")
                if vp_name == "desktop":
                    page.fill("#q", "custody")
                    page.wait_for_url("**q=custody**")
                    page.wait_for_function("document.querySelectorAll('#feed-list .row').length >= 1")
                    page.click('#cats button[data-cat="Regulation"]')
                    page.wait_for_url("**category=Regulation**")
                    page.go_back()
                    page.wait_for_function("!location.search.includes('category')")
                    page.select_option("#region", "Pacific Northwest")
                    page.wait_for_url("**region=Pacific**")
                    page.fill("#q", "zzzznotaword")
                    page.wait_for_selector(".state button:has-text('Clear filters')")
                    page.click(".state button:has-text('Clear filters')")
                    page.wait_for_function("location.search === '?tab=feed'")
                    page.keyboard.press("/")
                    if page.evaluate("document.activeElement.id") != "q":
                        problems.append("'/' shortcut did not focus the search box")
                    page.goto(base + "/?tab=mna")
                    page.click("th button:has-text('Headline AUM')")
                    page.wait_for_url("**sort=h**")
                    if page.get_attribute("th[aria-sort]", "aria-sort") != "descending":
                        problems.append("deals sort did not set aria-sort")
                page.goto(base + "/")
                page.wait_for_selector(".story")
                page.click("#watch-open")
                page.wait_for_selector("#drawer:not([hidden])")
                page.fill("#watch-name", "Harborview Wealth Partners")
                page.fill("#watch-aliases", "Harborview")
                page.click("#watch-add button[type=submit]")
                page.wait_for_selector("#watchlist li:has-text('Harborview Wealth Partners')")
                for _ in range(12):  # focus stays inside the drawer
                    page.keyboard.press("Tab")
                if not page.evaluate("document.getElementById('drawer').contains(document.activeElement)"):
                    problems.append(f"[{vp_name}] focus escaped the watchlist drawer")
                page.screenshot(path=str(OUT / f"drawer-{vp_name}-light.png"))
                page.keyboard.press("Escape")
                page.wait_for_selector("#drawer", state="hidden")
                page.wait_for_selector(".section-head:has-text('From your watchlist')")
                page.wait_for_selector(".story.is-watch:has-text('Summit Ridge')")
                page.evaluate("scrollTo(0, 0)")
                page.screenshot(path=str(OUT / f"watchlist-added-{vp_name}-light.png"))
                page.click("#watch-open")
                with page.expect_download() as dl:
                    page.click("#watch-export")
                exported = json.loads(Path(dl.value.path()).read_text())
                if [f["name"] for f in exported.get("firms", [])] != ["Harborview Wealth Partners"]:
                    problems.append(f"watchlist export unexpected: {exported}")
                page.click("#watchlist button[aria-label='Remove Harborview Wealth Partners']")
                page.wait_for_function("!document.querySelector('#watchlist').textContent.includes('Harborview')")
                imp = OUT / "_import.json"
                imp.write_text(json.dumps(SAMPLE_WATCHLIST))
                page.set_input_files("#watch-import", str(imp))
                imp.unlink()
                page.wait_for_selector("#watchlist li:has-text('Crestline Wealth')")
                if page.evaluate("JSON.parse(localStorage.getItem('ww-watchlist')).firms.length") != 2:
                    problems.append("imported watchlist not stored under ww-watchlist")
                ctx.close()
            # theme toggle persists in localStorage
            ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}, color_scheme="light")
            serve_fonts(ctx)
            page = ctx.new_page()
            page.on("console", lambda m: m.type == "error" and problems.append(f"[toggle] console: {m.text}"))
            page.goto(base + "/")
            page.evaluate("localStorage.setItem('ww-theme', 'dark')")   # the old key is honored once, then migrated
            page.reload()
            if page.evaluate("document.documentElement.dataset.theme + localStorage.getItem('fd-theme')") != "darkdark":
                problems.append("old ww-theme choice was not migrated to fd-theme")
            page.click("#theme-toggle")
            page.reload()
            if page.evaluate("document.documentElement.dataset.theme") != "light" or page.text_content("#theme-toggle") != "Dark mode":
                problems.append("theme toggle did not persist across reload")
            ctx.close()
            browser.close()
    finally:
        if proc:
            proc.terminate()
    print(f"{shots} screenshots → {OUT.relative_to(ROOT)}/")
    (OUT / "playwright-report.json").write_text(json.dumps({"screenshots": shots, "problems": problems}, indent=2))
    if problems:
        print(f"{len(problems)} problem(s):")
        for p_ in problems:
            print("  " + p_)
        return 1
    print("0 console errors, 0 failed requests, no horizontal overflow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
