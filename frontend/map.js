/* Fiduciary Wire — RIA map. Loaded only when the Map tab opens (app.js injects it).
   Reads /us-states.json (state outlines, Albers USA, 975×610) and /data/riamap.json (one compact row per
   SEC-registered adviser); a click loads that firm's detail shard /data/riamap/details-NN.json.

   Drawing: state outlines are SVG; ~15k advisers are dots on one canvas, redrawn only when the view, filters or
   theme change. Animation lives on a second, small canvas: a one-time reveal, slow pulse rings on firms with a
   deal in the last two weeks, a breathing halo on the selected firm, and eased fly-to zooms. That loop runs at
   ~30 fps only while something animates, pauses when the tab is hidden or the map is off-screen, and is off for
   anyone who prefers reduced motion. */
"use strict";
(function () {
  const W = 975, H = 610, SHARD_DIGITS = 2;
  const MIN_K = 1, MAX_K = 48;
  const AUM_STEPS = [[0, "Any AUM"], [1e8, "$100M+"], [1e9, "$1B+"], [1e10, "$10B+"], [1e11, "$100B+"]];
  const FOCUS_VAR = ["--cat-people", "--cat-prod", "--cat-mna", "--cat-other"];
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");

  function mount(root, api) {
    const { el, put, fmtAum, fmtDate, ext, nav, plural } = api;
    const state = { firms: [], meta: null, view: { k: 1, x: 0, y: 0 }, filter: readFilter(), selected: null, hover: null,
      details: new Map(), intro: 0, introStart: 0, colors: [], ink: {}, raf: 0, visible: true, lastTick: 0, fly: null,
      busyUntil: 0 };
    const P = new URLSearchParams(location.search);

    /* ---------- layout ---------- */
    const search = el("input", { class: "input grow", type: "search", placeholder: "Find an adviser by name or city",
      "aria-label": "Find an adviser by name or city", autocomplete: "off" });
    const results = el("ul", { class: "map-results", role: "listbox", hidden: true });
    const aumSel = el("select", { class: "input", "aria-label": "Minimum AUM" },
      AUM_STEPS.map(([v, l]) => el("option", { value: String(v) }, l)));
    const svcSel = el("select", { class: "input", "aria-label": "Service offered" }, el("option", { value: "" }, "Any service"));
    const newsChk = el("label", { class: "check" }, el("input", { type: "checkbox" }), " In the news");
    const focusBar = el("div", { class: "cat-toggles map-focus", role: "group", "aria-label": "Client focus" });
    const svgNS = "http://www.w3.org/2000/svg";
    const svgEl = document.createElementNS(svgNS, "svg");
    svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svgEl.setAttribute("class", "map-svg");
    svgEl.setAttribute("aria-hidden", "true");
    const gStates = document.createElementNS(svgNS, "g");
    svgEl.append(gStates);
    const dots = el("canvas", { class: "map-dots", role: "img", "aria-label": "Map of SEC-registered investment advisers; use the search box or the list of largest advisers to select one." });
    const fx = el("canvas", { class: "map-fx", "aria-hidden": "true" });
    const tip = el("div", { class: "map-tip", role: "status", hidden: true });
    const zoomIn = el("button", { type: "button", class: "map-zbtn", "aria-label": "Zoom in" }, "+");
    const zoomOut = el("button", { type: "button", class: "map-zbtn", "aria-label": "Zoom out" }, "−");
    const zoomReset = el("button", { type: "button", class: "map-zbtn", "aria-label": "Show the whole country" }, "⤢");
    const stage = el("div", { class: "map-stage", tabindex: "0" }, svgEl, dots, fx, tip,
      el("div", { class: "map-zoom" }, zoomIn, zoomOut, zoomReset));
    const legend = el("div", { class: "map-legend" });
    const panel = el("aside", { class: "map-panel", "aria-live": "polite" });
    const stats = el("span", { class: "meta-line" }, "Loading advisers…");
    const shown = el("span", { class: "meta-line map-shown" });
    put(root,
      el("div", { class: "page-head" }, el("h1", { class: "page-title" }, "RIA map"), stats),
      el("div", { class: "filters map-filters" }, el("div", { class: "map-search" }, search, results), aumSel, svcSel, newsChk),
      focusBar,
      el("div", { class: "map-wrap" }, el("div", { class: "map-main" }, stage, el("div", { class: "map-under" }, legend, shown)), panel));

    /* ---------- data ---------- */
    Promise.all([fetch("/us-states.json").then((r) => { if (!r.ok) throw new Error(`Couldn't load the state outlines (HTTP ${r.status}).`); return r.json(); }),
      fetch("/data/riamap.json").then((r) => { if (!r.ok) throw new Error(`Couldn't load riamap.json (HTTP ${r.status}).`); return r.json(); })])
      .then(([shapes, m]) => {
        for (const s of shapes.states) {
          const p = document.createElementNS(svgNS, "path");
          p.setAttribute("d", s.d);
          p.setAttribute("class", "map-state");
          gStates.append(p);
        }
        state.meta = m;
        const f = m.fields;
        const ix = Object.fromEntries(f.map((k, i) => [k, i]));
        state.firms = m.firms.map((r, order) => ({ crd: r[ix.crd], name: r[ix.name], x: r[ix.x], y: r[ix.y], aum: r[ix.aum_usd],
          city: r[ix.city], st: r[ix.state], focus: r[ix.focus], svc: r[ix.services], flags: r[ix.flags], order,
          lname: (r[ix.name] + " " + (r[ix.city] || "")).toLowerCase(), reveal: hash(r[ix.crd]) }));
        state.byCrd = new Map(state.firms.map((x) => [x.crd, x]));
        buildGrid();
        put(svcSel, el("option", { value: "" }, "Any service"), m.services.map((s, i) => el("option", { value: String(i + 1) }, s)));
        put(focusBar, m.focus.map((label, i) => el("button", { type: "button", "data-focus": String(i), title: "Show or hide " + label },
          el("span", { class: "swatch", "data-f": String(i) }), label, el("span", { class: "n" }))));
        syncControls();
        renderStats();
        readColors();
        resize();
        const want = Number(P.get("firm"));
        if (want && state.byCrd.has(want)) select(state.byCrd.get(want), { fly: true, instant: true });
        else showOverview();
        startIntro();
      })
      .catch((e) => put(root, el("p", { class: "state error", role: "alert" }, e.message + " ",
        el("button", { type: "button", onclick: () => location.reload() }, "Retry"))));

    /* ---------- filters (kept in the URL) ---------- */
    function readFilter() {
      const p = new URLSearchParams(location.search);
      return { min: Number(p.get("min") || 0), svc: Number(p.get("svc") || 0), news: p.get("news") === "1",
        focus: (p.get("focus") || "").split(",").filter((x) => /^[0-3]$/.test(x)).map(Number) };
    }
    function writeFilter() {
      const p = new URLSearchParams();
      p.set("tab", "map");
      const f = state.filter;
      if (f.min) p.set("min", String(f.min));
      if (f.svc) p.set("svc", String(f.svc));
      if (f.news) p.set("news", "1");
      if (f.focus.length) p.set("focus", f.focus.join(","));
      if (state.selected) p.set("firm", String(state.selected.crd));
      history.replaceState(null, "", "/?" + p.toString());
    }
    function passes(fm) {
      const f = state.filter;
      if (f.min && fm.aum < f.min) return false;
      if (f.svc && !(fm.svc & (1 << (f.svc - 1)))) return false;
      if (f.news && !(fm.flags & 3)) return false;
      if (f.focus.length && !f.focus.includes(fm.focus)) return false;
      return true;
    }
    function syncControls() {
      aumSel.value = String(state.filter.min);
      svcSel.value = state.filter.svc ? String(state.filter.svc) : "";
      newsChk.querySelector("input").checked = state.filter.news;
      const counts = [0, 0, 0, 0];
      for (const fm of state.firms) counts[fm.focus]++;
      for (const b of focusBar.querySelectorAll("button")) {
        const i = Number(b.dataset.focus);
        b.setAttribute("aria-pressed", String(!state.filter.focus.length || state.filter.focus.includes(i)));
        b.querySelector(".n").textContent = counts[i].toLocaleString("en-US");
        b.hidden = !counts[i];
      }
    }
    function filtersChanged() {
      writeFilter();
      syncControls();
      if (state.selected && !passes(state.selected)) select(null);
      draw();
      updateShown();
    }
    aumSel.addEventListener("change", () => { state.filter.min = Number(aumSel.value); filtersChanged(); });
    svcSel.addEventListener("change", () => { state.filter.svc = Number(svcSel.value || 0); filtersChanged(); });
    newsChk.querySelector("input").addEventListener("change", (e) => { state.filter.news = e.target.checked; filtersChanged(); });
    focusBar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-focus]");
      if (!b) return;
      const i = Number(b.dataset.focus), cur = state.filter.focus.length ? state.filter.focus : [0, 1, 2, 3];
      let next = cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i];
      if (!next.length || next.length === 4) next = [];
      state.filter.focus = next.sort();
      filtersChanged();
    });

    /* ---------- search ---------- */
    let hits = [];
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      if (q.length < 2) { results.hidden = true; return; }
      hits = [];
      for (const fm of state.firms) { // largest first, so the first matches are the most notable
        if (fm.lname.includes(q)) { hits.push(fm); if (hits.length === 8) break; }
      }
      put(results, hits.length ? hits.map((fm, i) => el("li", { role: "option", id: "mr-" + i },
        el("button", { type: "button", onclick: () => { pick(fm); } }, el("span", {}, fm.name),
          el("span", { class: "muted" }, [fm.city, fm.st].filter(Boolean).join(", ") + " · " + fmtAum(fm.aum)))))
        : [el("li", { class: "none" }, "No adviser by that name.")]);
      results.hidden = false;
    });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && hits[0]) { e.preventDefault(); pick(hits[0]); }
      if (e.key === "Escape") { results.hidden = true; }
    });
    function pick(fm) {
      results.hidden = true;
      search.value = fm.name;
      if (!passes(fm)) { state.filter = { min: 0, svc: 0, news: false, focus: [] }; syncControls(); }
      select(fm, { fly: true });
      draw();
      updateShown();
    }

    /* ---------- geometry: map units ↔ screen ---------- */
    let cssW = 0, cssH = 0, base = 1, dpr = 1;
    function resize() {
      const r = stage.getBoundingClientRect();
      cssW = Math.max(1, r.width); cssH = Math.max(1, r.height);
      base = Math.min(cssW / W, cssH / H);
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      for (const c of [dots, fx]) { c.width = Math.round(cssW * dpr); c.height = Math.round(cssH * dpr); }
      clampView();
      applySvg();
      draw();
    }
    const offX = () => (cssW - W * base) / 2, offY = () => (cssH - H * base) / 2;
    const sx = (x) => offX() + (x * state.view.k + state.view.x) * base;
    const sy = (y) => offY() + (y * state.view.k + state.view.y) * base;
    const mx = (px) => ((px - offX()) / base - state.view.x) / state.view.k;
    const my = (py) => ((py - offY()) / base - state.view.y) / state.view.k;
    function clampView() {
      const v = state.view;
      v.k = Math.max(MIN_K, Math.min(MAX_K, v.k));
      const slackX = W * 0.35, slackY = H * 0.35;   // the map may move a bit past its edge, never off-screen
      v.x = Math.min(slackX, Math.max(W - W * v.k - slackX, v.x));
      v.y = Math.min(slackY, Math.max(H - H * v.k - slackY, v.y));
      if (v.k === 1) { v.x = 0; v.y = 0; }
    }
    function applySvg() {
      const v = state.view;
      gStates.setAttribute("transform", `translate(${v.x} ${v.y}) scale(${v.k})`);
      svgEl.style.setProperty("--stroke", String(0.75 / v.k));
      const s = svgEl.style;
      s.width = W * base + "px"; s.height = H * base + "px"; s.left = offX() + "px"; s.top = offY() + "px";
    }
    const radius = (fm) => Math.min(16, 1.3 + Math.sqrt(fm.aum / 1e9) * 1.55) * (0.85 + 0.15 * Math.sqrt(state.view.k));

    /* ---------- spatial grid for hover/click ---------- */
    const CELL = 6;
    let grid = new Map();
    function buildGrid() {
      grid = new Map();
      for (const fm of state.firms) {
        const key = Math.floor(fm.x / CELL) + "," + Math.floor(fm.y / CELL);
        if (!grid.has(key)) grid.set(key, []);
        grid.get(key).push(fm);
      }
    }
    function nearest(px, py) {
      const x = mx(px), y = my(py);
      const reach = 18 / (base * state.view.k);   // screen px → map units
      const c0 = Math.floor((x - reach) / CELL), c1 = Math.floor((x + reach) / CELL);
      const r0 = Math.floor((y - reach) / CELL), r1 = Math.floor((y + reach) / CELL);
      let best = null, bestD = Infinity;
      for (let c = c0; c <= c1; c++) for (let r = r0; r <= r1; r++) {
        for (const fm of grid.get(c + "," + r) || []) {
          if (!passes(fm)) continue;
          const dx = (sx(fm.x) - px), dy = (sy(fm.y) - py);
          const d = Math.hypot(dx, dy) - radius(fm);   // inside a big dot counts as close
          if (d < bestD || (d === bestD && fm.order > best.order)) { best = fm; bestD = d; }
        }
      }
      return bestD <= 7 ? best : null;
    }

    /* ---------- colors (theme-aware) ---------- */
    function readColors() {
      const cs = getComputedStyle(document.documentElement);
      state.colors = FOCUS_VAR.map((v) => cs.getPropertyValue(v).trim() || "#888");
      state.ink = { bg: cs.getPropertyValue("--bg").trim(), text: cs.getPropertyValue("--text").trim(),
        accent: cs.getPropertyValue("--accent").trim(), dark: document.documentElement.dataset.theme === "dark" };
      for (const s of focusBar.querySelectorAll(".swatch")) s.style.background = state.colors[Number(s.dataset.f)];
      renderLegend();
    }
    new MutationObserver(() => { readColors(); draw(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    /* ---------- drawing ---------- */
    let pending = false, settle = 0;
    function draw() {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; paint(); });
    }
    function busy() {   // while zooming or panning: a cheaper paint, then one full-quality paint once it stops
      state.busyUntil = performance.now() + 140;
      clearTimeout(settle);
      settle = setTimeout(draw, 160);
    }
    // The last full-quality frame and the view it was drawn at: while zooming or panning, that image is just
    // scaled and shifted (one draw call per frame); the dots are drawn again once the view is still.
    const snap = { canvas: document.createElement("canvas"), view: null, w: 0, h: 0 };
    function paint() {
      const ctx = dots.getContext("2d");
      const fast = performance.now() < state.busyUntil || !!state.fly;
      if (fast && snap.view && snap.w === dots.width && snap.h === dots.height && state.intro >= 1) {
        const s0 = snap.view, v = state.view, a = v.k / s0.k;
        // a map point at snapshot pixel p (CSS px) is now at a·p + b
        const bx = offX() + (v.x - s0.x * a) * base - offX() * a;
        const by = offY() + (v.y - s0.y * a) * base - offY() * a;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, dots.width, dots.height);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.drawImage(snap.canvas, bx, by, cssW * a, cssH * a);
        kick();
        return;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);
      if (!state.firms.length) return;
      const reveal = state.intro;   // 0…1 during the intro, then 1
      const alpha = state.ink.dark ? 0.78 : 0.72;
      const margin = 20;
      // one path per color (fewer state changes = faster), largest first so small dots stay on top
      for (let f = 0; f < 4; f++) {
        ctx.beginPath();
        let any = false;
        for (const fm of state.firms) {
          if (fm.focus !== f || !passes(fm)) continue;
          if (reveal < 1 && fm.reveal > reveal) continue;
          const x = sx(fm.x), y = sy(fm.y);
          if (x < -margin || y < -margin || x > cssW + margin || y > cssH + margin) continue;
          const r = radius(fm);
          if (r < 1.9) ctx.rect(x - r, y - r, 2 * r, 2 * r);   // at this size a square reads as a dot, and is far cheaper
          else { ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, Math.PI * 2); }
          any = true;
        }
        if (!any) continue;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = state.colors[f];
        ctx.fill();
        ctx.globalAlpha = state.ink.dark ? 0.35 : 0.55;
        ctx.lineWidth = 0.6;
        ctx.strokeStyle = state.ink.bg;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      // watchlist firms: a thin accent ring
      ctx.beginPath();
      for (const fm of state.firms) {
        if (!passes(fm) || !api.isWatched(fm.crd, fm.name)) continue;
        const r = radius(fm) + 2.2;
        ctx.moveTo(sx(fm.x) + r, sy(fm.y));
        ctx.arc(sx(fm.x), sy(fm.y), r, 0, Math.PI * 2);
      }
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = state.ink.accent;
      ctx.stroke();
      if (reveal >= 1) {   // keep this frame for scaling during the next zoom or pan
        if (snap.canvas.width !== dots.width || snap.canvas.height !== dots.height) {
          snap.canvas.width = dots.width; snap.canvas.height = dots.height;
        }
        const sc = snap.canvas.getContext("2d");
        sc.clearRect(0, 0, snap.canvas.width, snap.canvas.height);
        sc.drawImage(dots, 0, 0);
        snap.view = { ...state.view }; snap.w = dots.width; snap.h = dots.height;
      }
      kick();
    }

    /* ---------- the animation layer ---------- */
    function startIntro() {
      if (reduceMotion.matches) { state.intro = 1; draw(); return; }
      state.intro = 0.001;
      state.introStart = performance.now();
      kick();
    }
    function animating() {
      return state.visible && !document.hidden && (state.intro < 1 || state.fly || state.selected || state.hover ||
        (!reduceMotion.matches && pulseFirms().length));
    }
    let pulseCache = null;
    function pulseFirms() {   // firms with a deal in the last two weeks (few), visible on screen
      if (!pulseCache) pulseCache = state.firms.filter((fm) => fm.flags & 2);
      return pulseCache;
    }
    function kick() { if (!state.raf && animating()) state.raf = requestAnimationFrame(tick); }
    function tick(now) {
      state.raf = 0;
      if (!animating()) { clearFx(); return; }
      if (now - state.lastTick < 32) { state.raf = requestAnimationFrame(tick); return; }   // ~30 fps is plenty
      state.lastTick = now;
      if (state.intro < 1) {
        const t = Math.min(1, (now - state.introStart) / 1100);
        state.intro = t >= 1 ? 1 : 1 - Math.pow(1 - t, 3);
        paint();
      }
      if (state.fly) stepFly(now);
      paintFx(now);
      state.raf = requestAnimationFrame(tick);
    }
    function clearFx() {
      const c = fx.getContext("2d");
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.clearRect(0, 0, cssW, cssH);
    }
    function paintFx(now) {
      const c = fx.getContext("2d");
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.clearRect(0, 0, cssW, cssH);
      if (!reduceMotion.matches && state.intro >= 1) {
        for (const fm of pulseFirms()) {   // expanding, fading rings: a firm that just did a deal
          if (!passes(fm)) continue;
          const x = sx(fm.x), y = sy(fm.y);
          if (x < -40 || y < -40 || x > cssW + 40 || y > cssH + 40) continue;
          const phase = ((now / 2600) + (fm.reveal * 3)) % 1;
          const r = radius(fm) + 2 + phase * 16;
          c.beginPath();
          c.arc(x, y, r, 0, Math.PI * 2);
          c.globalAlpha = 0.55 * (1 - phase);
          c.lineWidth = 1.5;
          c.strokeStyle = state.colors[fm.focus];
          c.stroke();
        }
      }
      if (state.hover && state.hover !== state.selected) {
        const fm = state.hover, r = radius(fm) + 3;
        c.globalAlpha = 1;
        c.beginPath();
        c.arc(sx(fm.x), sy(fm.y), r, 0, Math.PI * 2);
        c.lineWidth = 1.5;
        c.strokeStyle = state.ink.text;
        c.stroke();
      }
      if (state.selected) {   // a slow breathing halo
        const fm = state.selected, x = sx(fm.x), y = sy(fm.y);
        const b = reduceMotion.matches ? 0.5 : (Math.sin(now / 520) + 1) / 2;
        const r = radius(fm);
        c.globalAlpha = 0.18 + 0.12 * b;
        c.fillStyle = state.ink.accent;
        c.beginPath();
        c.arc(x, y, r + 7 + 4 * b, 0, Math.PI * 2);
        c.fill();
        c.globalAlpha = 1;
        c.beginPath();
        c.arc(x, y, r + 2.5, 0, Math.PI * 2);
        c.lineWidth = 2;
        c.strokeStyle = state.ink.accent;
        c.stroke();
        c.beginPath();
        c.arc(x, y, Math.max(2, r * 0.45), 0, Math.PI * 2);
        c.fillStyle = state.ink.accent;
        c.fill();
      }
      c.globalAlpha = 1;
    }
    document.addEventListener("visibilitychange", kick);
    reduceMotion.addEventListener("change", () => { state.intro = 1; draw(); kick(); });
    const io = new IntersectionObserver((es) => { state.visible = es[0].isIntersecting; kick(); });
    io.observe(stage);

    /* ---------- zoom & pan ---------- */
    function zoomAt(px, py, factor) {
      const v = state.view, x = mx(px), y = my(py);
      v.k = Math.max(MIN_K, Math.min(MAX_K, v.k * factor));
      v.x = (px - offX()) / base - x * v.k;
      v.y = (py - offY()) / base - y * v.k;
      clampView();
      applySvg();
      busy();
      draw();
      debouncedOverview();
    }
    function flyTo(target, ms = 650) {
      if (reduceMotion.matches || ms === 0) { state.view = target; clampView(); applySvg(); draw(); debouncedOverview(); return; }
      state.fly = { from: { ...state.view }, to: target, t0: performance.now(), ms };
      kick();
    }
    function stepFly(now) {
      const f = state.fly, t = Math.min(1, (now - f.t0) / f.ms);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      // interpolate zoom geometrically so it feels even
      const k = f.from.k * Math.pow(f.to.k / f.from.k, e);
      const cx0 = (W / 2 - f.from.x) / f.from.k, cy0 = (H / 2 - f.from.y) / f.from.k;
      const cx1 = (W / 2 - f.to.x) / f.to.k, cy1 = (H / 2 - f.to.y) / f.to.k;
      const cx = cx0 + (cx1 - cx0) * e, cy = cy0 + (cy1 - cy0) * e;
      state.view = { k, x: W / 2 - cx * k, y: H / 2 - cy * k };
      if (t >= 1) { state.view = f.to; state.fly = null; debouncedOverview(); }
      clampView();
      applySvg();
      paint();
      if (!state.fly) draw();   // the landing frame in full quality
    }
    const viewCentered = (x, y, k) => ({ k, x: W / 2 - x * k, y: H / 2 - y * k });
    zoomIn.addEventListener("click", () => flyTo(scaleAround(1.8), 300));
    zoomOut.addEventListener("click", () => flyTo(scaleAround(1 / 1.8), 300));
    zoomReset.addEventListener("click", () => flyTo({ k: 1, x: 0, y: 0 }, 500));
    function scaleAround(f) {
      const v = state.view, cx = (W / 2 - v.x) / v.k, cy = (H / 2 - v.y) / v.k;
      return viewCentered(cx, cy, Math.max(MIN_K, Math.min(MAX_K, v.k * f)));
    }
    stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = stage.getBoundingClientRect();
      zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0018)));
    }, { passive: false });
    const pointers = new Map();
    let drag = null, moved = false, pinch = null;
    stage.addEventListener("pointerdown", (e) => {
      stage.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      moved = false;
      if (pointers.size === 1) drag = { x: e.clientX, y: e.clientY, vx: state.view.x, vy: state.view.y };
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), k: state.view.k };
        drag = null;
      }
    });
    stage.addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        const cx = (a.x + b.x) / 2 - r.left, cy = (a.y + b.y) / 2 - r.top;
        zoomAt(cx, cy, (pinch.k * d / pinch.d) / state.view.k);
        moved = true;
        return;
      }
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
        if (moved) {
          state.view.x = drag.vx + dx / base;
          state.view.y = drag.vy + dy / base;
          clampView();
          applySvg();
          busy();
          draw();
          hideTip();
          return;
        }
      }
      if (e.pointerType === "mouse") hoverAt(e.clientX - r.left, e.clientY - r.top);
    });
    const end = (e) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      if (!pointers.size) {
        if (!moved) {
          const r = stage.getBoundingClientRect();
          const fm = nearest(e.clientX - r.left, e.clientY - r.top);
          select(fm, { fly: false });
        } else debouncedOverview();
        drag = null;
      }
    };
    stage.addEventListener("pointerup", end);
    stage.addEventListener("pointercancel", (e) => { pointers.delete(e.pointerId); drag = null; pinch = null; });
    stage.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") { state.hover = null; hideTip(); kick(); } });
    stage.addEventListener("dblclick", (e) => {
      const r = stage.getBoundingClientRect();
      e.preventDefault();
      const x = mx(e.clientX - r.left), y = my(e.clientY - r.top);
      flyTo(viewCentered(x, y, Math.min(MAX_K, state.view.k * 2.2)), 380);
    });
    stage.addEventListener("keydown", (e) => {
      const step = 60 / (state.view.k * base);
      const v = { ...state.view };
      if (e.key === "+" || e.key === "=") flyTo(scaleAround(1.6), 220);
      else if (e.key === "-" || e.key === "_") flyTo(scaleAround(1 / 1.6), 220);
      else if (e.key === "ArrowLeft") { v.x += step * v.k; flyTo(v, 150); }
      else if (e.key === "ArrowRight") { v.x -= step * v.k; flyTo(v, 150); }
      else if (e.key === "ArrowUp") { v.y += step * v.k; flyTo(v, 150); }
      else if (e.key === "ArrowDown") { v.y -= step * v.k; flyTo(v, 150); }
      else if (e.key === "Escape") select(null);
      else return;
      e.preventDefault();
    });
    new ResizeObserver(() => resize()).observe(stage);

    /* ---------- hover tooltip ---------- */
    function hoverAt(px, py) {
      const fm = nearest(px, py);
      if (fm !== state.hover) { state.hover = fm; kick(); if (!fm) clearFxSoon(); }
      if (!fm) { hideTip(); stage.style.cursor = "grab"; return; }
      stage.style.cursor = "pointer";
      put(tip, el("strong", {}, fm.name), el("span", {}, [fm.city, fm.st].filter(Boolean).join(", ")),
        el("span", { class: "aum" }, fmtAum(fm.aum) + " AUM"));
      tip.hidden = false;
      const x = sx(fm.x), y = sy(fm.y), tw = tip.offsetWidth;
      tip.style.left = Math.max(6, Math.min(cssW - tw - 6, x - tw / 2)) + "px";
      tip.style.top = (y - radius(fm) - tip.offsetHeight - 10 < 4 ? y + radius(fm) + 10 : y - radius(fm) - tip.offsetHeight - 10) + "px";
    }
    function hideTip() { tip.hidden = true; }
    function clearFxSoon() { if (!animating()) clearFx(); }

    /* ---------- selection + details ---------- */
    function select(fm, { fly = false, instant = false } = {}) {
      state.selected = fm || null;
      writeFilter();
      if (!fm) { showOverview(); kick(); clearFxSoon(); return; }
      if (fly) {
        const k = Math.max(state.view.k, fm.aum > 5e10 ? 5 : 7);
        flyTo(viewCentered(fm.x, fm.y, k), instant ? 0 : 750);
      }
      kick();
      showDetails(fm);
    }
    function shardOf(crd) { return String(crd % state.meta.shards).padStart(SHARD_DIGITS, "0"); }
    function loadDetails(crd) {
      const n = shardOf(crd);
      if (!state.details.has(n)) {
        state.details.set(n, fetch(`/data/riamap/details-${n}.json`).then((r) => {
          if (!r.ok) throw new Error(`Couldn't load the adviser details (HTTP ${r.status}).`);
          return r.json();
        }).catch((e) => { state.details.delete(n); throw e; }));
      }
      return state.details.get(n).then((d) => d.firms[String(crd)] || null);
    }
    function showDetails(fm) {
      const head = [
        el("button", { type: "button", class: "textbtn map-close", onclick: () => select(null), "aria-label": "Close details" }, "✕ Close"),
        el("div", { class: "kicker", style: `color:${state.colors[fm.focus]}` }, state.meta.focus[fm.focus]),
        el("h2", { class: "map-name" }, fm.name),
        el("div", { class: "map-place" }, [fm.city, fm.st].filter(Boolean).join(", ")),
        el("div", { class: "map-aum" }, el("span", { class: "big" }, fmtAum(fm.aum)),
          el("span", { class: "meta-line" }, "Regulatory AUM · Form ADV, " + fmtDate(state.meta.sec_data_date))),
      ];
      put(panel, el("div", { class: "map-card" }, head, el("div", { class: "map-loading" }, "Loading the filing…")));
      panel.scrollTop = 0;
      loadDetails(fm.crd).then((d) => {
        if (state.selected !== fm) return;
        if (!d) { put(panel, el("div", { class: "map-card" }, head)); return; }
        const fact = (label, value, sub) => (value == null || value === "" ? null :
          el("div", {}, el("dt", {}, label), el("dd", { class: "v" }, value), sub ? el("dd", {}, sub) : null));
        const n = (v) => (v == null ? null : Number(v).toLocaleString("en-US"));
        const chips = (list) => (list && list.length ? el("div", { class: "map-chips" }, list.map((x) => el("span", { class: "firm-chip" }, x))) : null);
        const section = (title, body) => (body ? el("div", { class: "map-sec" }, el("div", { class: "section-head" }, el("span", {}, title)), body) : null);
        const since = d.registered ? d.registered.slice(0, 4) : null;
        put(panel, el("div", { class: "map-card is-open" }, head,
          d.legal_name && d.legal_name.toLowerCase() !== fm.name.toLowerCase() ? el("div", { class: "map-legal" }, "Legal name: " + d.legal_name) : null,
          el("dl", { class: "map-facts" },
            fact("Accounts", n(d.accounts), d.avg_account_usd ? "Avg " + fmtAum(d.avg_account_usd) : null),
            fact("Clients", n(d.clients)),
            fact("Employees", n(d.employees), d.advisory_staff != null ? n(d.advisory_staff) + " advisory" : null),
            fact("Offices", n(d.offices)),
            fact("Discretionary", d.discretionary_pct != null ? d.discretionary_pct + "%" : null, "of AUM"),
            fact("SEC-registered", since, d.adv_date ? "Last filing " + fmtDate(d.adv_date) : null)),
          section("Client mix by AUM", d.client_mix.length ? el("div", { class: "map-bars" }, d.client_mix.map(([label, pct]) =>
            el("div", { class: "bar" }, el("span", { class: "l" }, label), el("span", { class: "track" },
              el("span", { class: "fill", style: `--w:${pct}%; background:${state.colors[fm.focus]}` })), el("span", { class: "p" }, pct + "%")))) : null),
          section("Main practices", chips(d.services)),
          section("How it's paid", chips(d.compensation)),
          d.other_business.length ? section("Also registered as", chips(d.other_business)) : null,
          d.private_funds ? el("p", { class: "map-note" }, `Advises ${plural(d.private_funds, "private fund")}.`) : null,
          el("p", { class: "map-note" + (d.disclosures ? " warn" : "") }, d.disclosures
            ? "This adviser reports disciplinary disclosures on Form ADV. Details are on its SEC page."
            : "No disciplinary disclosures reported on Form ADV."),
          d.deals.length ? section("In the deal tracker", el("ul", { class: "map-deals" }, d.deals.map((x) =>
            el("li", {}, el("span", { class: "t" }, fmtDate(x.date.slice(0, 10))), " ", x.url ? ext(x.url, x.headline) : x.headline)))) : null,
          el("div", { class: "map-links" },
            d.website ? ext(d.website, "Website ↗") : null,
            ext(d.iapd_url, "SEC adviser page ↗"),
            d.slug ? nav(`/firm/${encodeURIComponent(d.slug)}`, "Fiduciary Wire coverage") : null,
            el("button", { type: "button", class: "textbtn", onclick: (e) => { api.addWatch(fm.name); e.target.textContent = "On your watchlist"; draw(); } },
              api.isWatched(fm.crd, fm.name) ? "On your watchlist" : "Add to watchlist"))));
      }).catch((e) => put(panel, el("div", { class: "map-card" }, head, el("p", { class: "state error" }, e.message))));
    }

    /* ---------- overview: legend + largest advisers in view ---------- */
    let ovTimer = 0;
    function debouncedOverview() { clearTimeout(ovTimer); ovTimer = setTimeout(() => { updateShown(); if (!state.selected) showOverview(); }, 160); }
    function inView() {
      const x0 = mx(0), x1 = mx(cssW), y0 = my(0), y1 = my(cssH);
      return state.firms.filter((fm) => passes(fm) && fm.x >= x0 && fm.x <= x1 && fm.y >= y0 && fm.y <= y1);
    }
    function updateShown() {
      if (!state.firms.length) return;
      const v = inView();
      const aum = v.reduce((s, fm) => s + fm.aum, 0);
      shown.textContent = `${v.length.toLocaleString("en-US")} advisers in view · ${fmtAum(aum)} AUM`;
    }
    function showOverview() {
      if (!state.firms.length) return;
      const top = inView().slice(0, 10);   // already largest first
      put(panel, el("div", { class: "map-card" },
        el("div", { class: "section-head" }, el("span", {}, state.view.k > 1.2 ? "Largest advisers in view" : "Largest advisers")),
        top.length ? el("ol", { class: "rank-list map-top" }, top.map((fm, i) => el("li", {},
          el("span", { class: "rank" }, String(i + 1).padStart(2, "0")),
          el("button", { type: "button", class: "name", onclick: () => select(fm, { fly: true }), title: fm.name },
            el("span", { class: "dot", style: `background:${state.colors[fm.focus]}` }), fm.name),
          el("span", { class: "n" }, fmtAum(fm.aum))))) : el("p", { class: "side-empty" }, "No advisers match these filters here."),
        el("p", { class: "map-hint" }, "Click a dot for the firm's filing: AUM, clients, practices and fees. Drag to pan, scroll or pinch to zoom.")));
      updateShown();
    }
    function renderLegend() {
      if (!state.meta) return;
      const sizes = [[1e8, "$100M"], [1e9, "$1B"], [1e10, "$10B"], [1e11, "$100B"]];
      put(legend,
        el("span", { class: "lg" }, sizes.map(([v, l]) => {
          const r = Math.min(16, 1.3 + Math.sqrt(v / 1e9) * 1.55);
          return el("span", { class: "lg-size" }, el("span", { class: "c", style: `width:${2 * r}px;height:${2 * r}px` }), l);
        })),
        el("span", { class: "lg" }, el("span", { class: "lg-ring" }), "Deal in the last two weeks"),
        el("span", { class: "lg" }, el("span", { class: "lg-ring watch" }), "On your watchlist"));
    }
    function renderStats() {
      const m = state.meta;
      stats.textContent = `${m.counts.mapped.toLocaleString("en-US")} SEC-registered advisers · ${fmtAum(m.total_aum_usd)} AUM · Form ADV data, ${fmtDate(m.sec_data_date)}`;
    }
  }

  function hash(n) { // stable 0…1 per firm: the order dots light up in, and the pulse phase
    let x = (Number(n) * 2654435761) >>> 0;
    x ^= x >>> 16; x = Math.imul(x, 2246822507) >>> 0; x ^= x >>> 13;
    return (x >>> 0) / 4294967296;
  }

  window.FWMap = { mount };
})();
