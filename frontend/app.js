/* Wealth Wire frontend — vanilla JS, no build step.
   Reads ONLY the static files under /data/ described in DATA-CONTRACT.md. The URL is the source of truth
   for the current view and filters; the watchlist lives in this browser's localStorage. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const CAT_CLASS = {
  "M&A": "cat-mna", "People Moves": "cat-people", "Regulation": "cat-reg", "Wealthtech": "cat-tech",
  "Products & Funds": "cat-prod", "Markets": "cat-mkt", "Other": "cat-other",
};
const TABS = ["feed", "digest", "archive", "weekly", "mna", "sources"];
const REGIONS = { "Pacific Northwest": ["WA", "OR", "ID"] };
const PAGE = 50;
const PIN_DAYS = 7;
const WATCH_KEY = "ww-watchlist";

/* ---------- data layer: /data/*.json only ---------- */
const cache = new Map();
function data(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch("/data/" + path, { headers: { Accept: "application/json" } }).then(async (r) => {
      if (!r.ok) throw new Error(`Couldn't load ${path} (HTTP ${r.status})`);
      return r.json();
    }).catch((e) => { cache.delete(path); throw e.message ? e : new Error("Network error loading " + path); }));
  }
  return cache.get(path);
}
async function optional(path, fallback) { try { return await data(path); } catch (e) { return fallback; } }

/* ---------- helpers ---------- */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
const extLink = (href, text, cls) => el("a", { href: safeUrl(href), class: cls, target: "_blank", rel: "noopener noreferrer" }, text);
const catChip = (cat) => el("span", { class: "cat " + (CAT_CLASS[cat] || "cat-other") }, cat || "Other");
function firmLink(f, cls = "firm") {
  return f.slug ? el("a", { class: cls, href: "/firm/" + encodeURIComponent(f.slug), "data-nav": "" }, f.name)
    : el("span", { class: cls + " unverified", title: "Not found in SEC adviser data (unverified)" }, f.name);
}
function fmtAum(v) {
  if (!v) return "";
  for (const [n, s] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (v >= n) { const x = v / n; return "$" + (x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1).replace(/\.0$/, "") : x.toFixed(2).replace(/0$/, "").replace(/\.0$/, "")) + s; }
  }
  return "$" + Math.round(v);
}
const dFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const tFmt = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const fullFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const longDay = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? tFmt.format(d) : dFmt.format(d) + " " + tFmt.format(d);
}
const fmtDay = (iso) => (iso ? dFmt.format(new Date(iso)) : "");
const fmtDate = (ymd) => (ymd ? longDay.format(new Date(ymd + "T12:00:00Z")) : "");
function relAgo(iso) {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  if (mins < 48 * 60) return Math.round(mins / 60) + "h ago";
  return Math.round(mins / 1440) + "d ago";
}
function stateBox(kind, title, body, action) {
  return el("div", { class: "state " + (kind || ""), role: kind === "error" ? "alert" : null },
    el("h3", {}, title), body ? el("p", {}, body) : null, action || null);
}
function skeletons(n) {
  const frag = document.createDocumentFragment();
  for (let i = 0; i < n; i++) frag.append($("#tpl-skeleton").content.cloneNode(true));
  return frag;
}
function aumBlock(c) {
  if (!c.aum_usd) return null;
  const sec = c.aum_source === "sec";
  return el("div", { class: "aum" + (sec ? " aum-sec" : ""), title: sec ? `SEC-reported AUM (as of ${c.sec_aum_as_of || "latest SEC file"})` : "AUM stated in the headline or teaser" },
    fmtAum(c.aum_usd), el("small", {}, sec ? "SEC AUM" : "AUM"));
}

/* ---------- watchlist (localStorage; never leaves the browser) ---------- */
const Watch = {
  load() {
    try {
      const raw = JSON.parse(localStorage.getItem(WATCH_KEY) || "null");
      return Watch.clean(raw);
    } catch (e) { return []; }
  },
  clean(raw) {
    const list = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.firms) ? raw.firms : []);
    const out = [], seen = new Set();
    for (const f of list) {
      const name = String((f && (f.name || f)) || "").trim().replace(/\s+/g, " ").slice(0, 80);
      if (!name || seen.has(name.toLowerCase())) continue;
      seen.add(name.toLowerCase());
      const aliases = (Array.isArray(f.aliases) ? f.aliases : []).map((a) => String(a).trim()).filter(Boolean).slice(0, 20);
      out.push({ name, aliases });
    }
    return out;
  },
  save(list) {
    try { localStorage.setItem(WATCH_KEY, JSON.stringify({ version: 1, firms: list })); return true; } catch (e) { return false; }
  },
};
let WATCH = Watch.load();
let MATCHERS = [];

const norm = (s) => s.toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function compileWatch(firmIndex) {
  MATCHERS = WATCH.map((f) => {
    const terms = [f.name, ...f.aliases].map((t) => t.trim()).filter((t) => t.replace(/\s/g, "").length >= 3);
    // SEC names: firms whose name or legal name starts with one of the terms (whole words)
    const crds = new Set();
    for (const firm of firmIndex) {
      const names = [firm.name, firm.legal_name].filter(Boolean).map(norm);
      if (terms.some((t) => names.some((n) => n === norm(t) || n.startsWith(norm(t) + " ")))) {
        crds.add(firm.crd);
        for (const n of [firm.name, firm.legal_name]) if (n && !terms.includes(n)) terms.push(n);
      }
    }
    const re = terms.length ? new RegExp("(?<![\\w&-])(?:" + terms.sort((a, b) => b.length - a.length)
      .map((t) => escRe(t).replace(/\s+/g, "\\s+")).join("|") + ")(?![\\w&]|-\\w)", "i") : null;
    return { name: f.name, re, crds };
  });
}
function watchHits(c) {
  const hits = [];
  for (const m of MATCHERS) {
    if ((m.re && m.re.test(c.headline)) || c.firms.some((f) => f.crd && m.crds.has(f.crd))
      || (m.re && c.firms.some((f) => m.re.test(f.name)))) hits.push(m.name);
  }
  return hits;
}

/* ---------- URL state ---------- */
function readState() {
  const p = new URLSearchParams(location.search);
  const firm = location.pathname.match(/^\/firm\/([^/]+)\/?$/);
  return {
    tab: firm ? "firm" : (TABS.includes(p.get("tab")) ? p.get("tab") : "feed"),
    slug: firm ? decodeURIComponent(firm[1]) : "",
    q: p.get("q") || "", source: p.get("source") || "",
    category: (p.get("category") || "").split(",").filter(Boolean),
    region: p.get("region") || "", from: p.get("from") || "", to: p.get("to") || "",
    watch: p.get("watch") === "1", conf: p.get("conf") || "",
    date: p.get("date") || "", week: p.get("week") || "",
  };
}
function writeState(patch, replace = false) {
  const s = { ...readState(), ...patch };
  const p = new URLSearchParams();
  if (s.tab !== "feed") p.set("tab", s.tab);
  if (s.tab === "feed") {
    if (s.q) p.set("q", s.q);
    if (s.source) p.set("source", s.source);
    if (s.category.length) p.set("category", s.category.join(","));
    if (s.region) p.set("region", s.region);
    if (s.from) p.set("from", s.from);
    if (s.to) p.set("to", s.to);
    if (s.watch) p.set("watch", "1");
  }
  if (s.tab === "mna" && s.conf) p.set("conf", s.conf);
  if (s.tab === "digest" && s.date) p.set("date", s.date);
  if (s.tab === "weekly" && s.week) p.set("week", s.week);
  const url = "/" + (p.toString() ? "?" + p : "");
  if (url !== location.pathname + location.search) history[replace ? "replaceState" : "pushState"](null, "", url);
  route();
}
function go(url) { history.pushState(null, "", url); route(); }

/* ---------- boot data ---------- */
let META = null, CLUSTERS = [], FIRMS = [];
async function loadCore() {
  const [meta, clusters, firms] = await Promise.all([data("meta.json"), data("clusters.json"), optional("firms/index.json", { firms: [] })]);
  META = meta; CLUSTERS = clusters.clusters; FIRMS = firms.firms;
  compileWatch(FIRMS);
  $("#demo-chip").hidden = !META.demo;
  $("#ingest-status").textContent = `updated ${relAgo(META.last_refresh)} · ${META.sources_ok}/${META.sources_total} sources · ${META.counts.stories} stories`;
  if (META.last_refresh) $("#ingest-status").title = "Last refresh: " + fullFmt.format(new Date(META.last_refresh));
  $("#footer-note").textContent = META.footer_note || $("#footer-note").textContent;
  $("#footer-refresh").textContent = META.last_refresh ? " · refreshed " + fullFmt.format(new Date(META.last_refresh)) : "";
  $("#source").replaceChildren(el("option", { value: "" }, "All sources"),
    ...META.sources.map((s) => el("option", { value: s.name }, s.name + (s.ok ? "" : " (failed)"))));
  const states = [...new Set(CLUSTERS.flatMap((c) => c.states))].sort();
  $("#region").replaceChildren(el("option", { value: "" }, "All regions"),
    ...Object.keys(REGIONS).map((r) => el("option", { value: r }, r)),
    ...(states.length ? [el("option", { disabled: true }, "── States ──")] : []),
    ...states.map((s) => el("option", { value: s }, s)));
  $("#cat-chips").replaceChildren(...META.categories.map((c) =>
    el("button", { type: "button", class: CAT_CLASS[c] || "cat-other", "data-cat": c, "aria-pressed": "false" }, c)));
}

/* ---------- routing ---------- */
async function route() {
  const s = readState();
  for (const t of [...TABS, "firm"]) $("#view-" + t).hidden = t !== s.tab;
  for (const a of document.querySelectorAll(".tabs a")) {
    const on = a.dataset.tab === s.tab || (a.dataset.tab === "archive" && s.tab === "weekly");
    a.setAttribute("aria-selected", String(on));
  }
  document.title = ({ feed: "Wealth Wire", digest: "Digest", archive: "Archive", weekly: "Weekly M&A recap", mna: "M&A", sources: "Sources", firm: "Firm" }[s.tab] || "Wealth Wire") + (s.tab === "feed" ? "" : " · Wealth Wire");
  window.scrollTo(0, 0);
  if (!META) {
    try { await loadCore(); } catch (e) {
      $("#view-" + s.tab).replaceChildren(stateBox("error", "Couldn't load Wealth Wire data", e.message,
        el("button", { class: "btn", type: "button", onclick: () => location.reload() }, "Retry")));
      return;
    }
    renderSidebar();
  }
  ({ feed: renderFeed, digest: renderDigest, archive: renderArchive, weekly: renderWeekly, mna: renderMna, sources: renderSources, firm: renderFirm })[s.tab](s);
}

/* ---------- feed ---------- */
function filterClusters(s, { ignoreWatch = false } = {}) {
  const terms = (s.q.toLowerCase().match(/[\w$&.'-]+/g) || []).map((t) => t.replace(/^[.'-]+|[.'-]+$/g, "")).filter(Boolean);
  const from = s.from ? new Date(s.from + "T00:00:00").toISOString() : null;
  const to = s.to ? (() => { const d = new Date(s.to + "T00:00:00"); d.setDate(d.getDate() + 1); return d.toISOString(); })() : null;
  const states = s.region ? (REGIONS[s.region] || [s.region]) : null;
  return CLUSTERS.filter((c) => {
    if (s.category.length && !s.category.includes(c.category)) return false;
    if (s.source && !c.sources.some((x) => x.name === s.source)) return false;
    if (states && !c.states.some((st) => states.includes(st))) return false;
    if (from && c.last_published < from) return false;
    if (to && c.first_published >= to) return false;
    if (terms.length) {
      const words = (c.headline + " " + c.firms.map((f) => f.name).join(" ")).toLowerCase().match(/[\w$&.'-]+/g) || [];
      if (!terms.every((t) => words.some((w) => w.startsWith(t)))) return false;
    }
    if (s.watch && !ignoreWatch && !watchHits(c).length) return false;
    return true;
  });
}
function highlight(text, q) {
  const terms = (q || "").split(/\s+/).map((t) => t.replace(/[^\w$.&'-]/g, "")).filter((t) => t.length > 1);
  if (!terms.length) return [text];
  const re = new RegExp("(" + terms.map(escRe).join("|") + ")", "ig");
  return text.split(re).map((part, i) => (i % 2 ? el("mark", {}, part) : part));
}
function card(c, s = {}) {
  const hits = watchHits(c);
  const multi = c.outlet_count > 1;
  return el("article", { class: "card" + (hits.length ? " is-watch" : ""), "data-cluster": c.id },
    el("div", { class: "card-meta" },
      el("time", { class: "card-time", datetime: c.last_published, title: "First reported " + fullFmt.format(new Date(c.first_published)) }, fmtTime(c.first_published)),
      catChip(c.category),
      hits.length ? el("span", { class: "chip chip-watch", title: "Watchlist: " + hits.join(", ") }, "★ " + hits.join(", ")) : null,
      c.press_release ? el("span", { class: "chip chip-pr", title: "Includes a press release" }, "PRESS RELEASE") : null,
      el("span", { class: "card-outlets" + (multi ? " multi" : "") }, multi ? `${c.outlet_count} outlets` : "")),
    el("div", { class: "card-main" },
      el("div", { class: "card-body" },
        el("h3", { class: "card-title" }, el("a", { href: safeUrl(c.url), target: "_blank", rel: "noopener noreferrer" }, ...highlight(c.headline, s.q))),
        el("div", { class: "card-foot" },
          ...c.sources.map((x) => el("a", { class: "src", href: safeUrl(x.url), target: "_blank", rel: "noopener noreferrer", title: `${x.name} · ${fullFmt.format(new Date(x.published_at))}` },
            x.name, multi ? el("span", { class: "src-time" }, fmtTime(x.published_at)) : null)),
          c.firms.length ? el("span", { class: "foot-sep" }) : null,
          ...c.firms.slice(0, 5).map((f) => firmLink(f)))),
      aumBlock(c)));
}
function describeFilters(s) {
  const b = [];
  if (s.q) b.push(`“${s.q}”`);
  if (s.source) b.push(s.source);
  if (s.category.length) b.push(s.category.join(" + "));
  if (s.region) b.push(s.region);
  if (s.from || s.to) b.push(`${s.from || "…"} → ${s.to || "…"}`);
  if (s.watch) b.push("watchlist");
  return b.join(" · ");
}
let feedShown = PAGE;
function renderFeed(s, more = false) {
  syncFilterInputs(s);
  if (!more) feedShown = PAGE;
  let list = filterClusters(s);
  let pinned = [];
  if (!s.watch && MATCHERS.length) {
    const cutoff = new Date(new Date(META.last_refresh || Date.now()).getTime() - PIN_DAYS * 864e5).toISOString();
    pinned = list.filter((c) => c.last_published >= cutoff && watchHits(c).length).slice(0, 10);
    const ids = new Set(pinned.map((c) => c.id));
    list = list.filter((c) => !ids.has(c.id));
  }
  $("#pinned").hidden = !pinned.length;
  $("#pinned-count").textContent = pinned.length ? String(pinned.length) : "";
  $("#pinned-list").replaceChildren(...pinned.map((c) => card(c, s)));
  $("#feed-list").replaceChildren(...list.slice(0, feedShown).map((c) => card(c, s)));
  $("#more").hidden = feedShown >= list.length;
  const f = describeFilters(s);
  $("#feed-summary").replaceChildren(el("b", {}, String(list.length)), ` ${list.length === 1 ? "story" : "stories"}`,
    pinned.length ? ` · ${pinned.length} pinned` : "", f ? ` · ${f}` : "");
  const err = $("#feed-error");
  err.replaceChildren();
  if (!list.length && !pinned.length) {
    err.append(CLUSTERS.length
      ? stateBox("", f ? "No stories match these filters" : "No stories", f ? "Try a broader search, another source, category or region, or a wider date range." : "",
        f ? el("button", { class: "btn", type: "button", onclick: clearFilters }, "Clear filters") : null)
      : stateBox("", "No stories yet", "The next refresh will fill this in."));
  }
}
function syncFilterInputs(s) {
  if (document.activeElement !== $("#q")) $("#q").value = s.q;
  $("#source").value = s.source; $("#region").value = s.region;
  $("#from").value = s.from; $("#to").value = s.to; $("#watch").checked = s.watch;
  for (const b of $("#cat-chips").children) b.setAttribute("aria-pressed", String(s.category.includes(b.dataset.cat)));
}
function clearFilters() { writeState({ q: "", source: "", category: [], region: "", from: "", to: "", watch: false }); }

/* ---------- sidebar ---------- */
async function renderSidebar() {
  renderWatchlist();
  const box = $("#trending");
  try {
    const t = await data("trending.json");
    if (!t.firms.length) { box.replaceChildren(el("li", { class: "muted" }, "No firm mentions in the last 7 days.")); return; }
    const max = t.firms[0].stories;
    box.replaceChildren(...t.firms.map((f) => el("li", {},
      el("div", { style: "flex:1;min-width:0" }, firmLink(f, "trend-name"),
        el("span", { class: "bar", style: `width:${Math.max(8, Math.round(100 * f.stories / max))}%` })),
      el("span", { class: "n", title: `${f.stories} ${f.stories === 1 ? "story" : "stories"}` }, f.stories))));
  } catch (e) { box.replaceChildren(el("li", { class: "form-msg err" }, e.message)); }
}
function renderWatchlist() {
  const box = $("#watchlist");
  if (!WATCH.length) { box.replaceChildren(el("li", { class: "muted" }, "No firms yet — add one below or import a JSON file.")); return; }
  const cutoff = new Date(new Date((META && META.last_refresh) || Date.now()).getTime() - PIN_DAYS * 864e5).toISOString();
  box.replaceChildren(...WATCH.map((f, i) => {
    const m = MATCHERS[i];
    const n = CLUSTERS.filter((c) => c.last_published >= cutoff && watchHits(c).includes(f.name)).length;
    return el("li", {},
      el("span", { class: "w-name" }, f.name, f.aliases.length ? el("span", { class: "w-alias" }, "aka " + f.aliases.join(", ")) : null,
        m && m.crds.size ? el("span", { class: "w-alias" }, `matches ${m.crds.size} SEC-registered firm${m.crds.size > 1 ? "s" : ""}`) : null),
      el("span", { class: "w-count", title: "Stories in the last 7 days" }, n || ""),
      el("button", { type: "button", "aria-label": "Remove " + f.name, title: "Remove " + f.name, onclick: () => setWatch(WATCH.filter((x) => x !== f), `Removed ${f.name}.`) }, "×"));
  }));
}
function setWatch(list, msg, isErr = false) {
  WATCH = Watch.clean(list);
  const ok = Watch.save(WATCH);
  compileWatch(FIRMS);
  const m = $("#watch-msg");
  m.className = "form-msg" + (isErr || !ok ? " err" : "");
  m.textContent = ok ? msg : "Couldn't save (browser storage unavailable); changes last until you reload.";
  renderWatchlist();
  route();
}

/* ---------- digest ---------- */
function digestItem(it, i, ai) {
  const c = CLUSTERS.find((x) => x.id === it.cluster_id);
  const hits = c ? watchHits(c) : [];
  return el("li", { class: hits.length ? "is-watch" : "" },
    el("div", { class: "t" }, extLink(it.url, it.headline)),
    el("div", { class: "d-meta" }, catChip(it.category), " ",
      el("span", { class: "mono muted" }, `${it.outlet_count} outlet${it.outlet_count > 1 ? "s" : ""}`),
      it.aum_usd ? el("span", { class: "aum-cell", title: it.aum_source === "sec" ? "SEC-reported AUM" : "AUM from the headline" }, " " + fmtAum(it.aum_usd) + (it.aum_source === "sec" ? " SEC" : "")) : null,
      hits.length ? el("span", { class: "chip chip-watch" }, "★ " + hits.join(", ")) : null),
    ai && it.summary ? el("p", { class: "d-sum" }, it.summary) : null,
    ai && it.why_it_matters ? el("p", { class: "d-why" }, el("b", {}, "Why it matters to advisors: "), it.why_it_matters) : null,
    el("div", { class: "srcs" }, ...it.sources.map((x) => extLink(x.url, x.name, "src")),
      ...(it.firms || []).filter((f) => f.slug).map((f) => firmLink(f))));
}
function watchFirst(items) {
  // stable re-rank: watchlist hits first, keep the server's order otherwise
  return items.map((it, i) => ({ it, i, w: (() => { const c = CLUSTERS.find((x) => x.id === it.cluster_id); return c && watchHits(c).length ? 1 : 0; })() }))
    .sort((a, b) => b.w - a.w || a.i - b.i).map((x) => x.it);
}
async function renderDigest(s) {
  const box = $("#digest");
  box.replaceChildren(stateBox("", "Loading digest…"));
  let d;
  try { d = s.date ? await data(`digests/${s.date}.json`) : await data("digest.json"); } catch (e) {
    box.replaceChildren(stateBox("error", "Couldn't load the digest", e.message)); return;
  }
  const items = watchFirst(d.items);
  const archived = !!s.date;
  box.replaceChildren(el("article", { class: "digest" },
    el("div", { class: "digest-head digest-head-slim" }, el("span", { class: "digest-label" }, d.ai ? "Morning digest" : "Top stories"),
      el("span", { class: "digest-date" }, fmtDate(d.date)),
      archived ? el("a", { class: "digest-file", href: "/?tab=archive", "data-nav": "" }, "← All digests") : null),
    d.ai && d.opener ? el("div", { class: "digest-opener" }, el("h2", {}, "Today in wealth management"), el("p", {}, d.opener)) : null,
    !d.ai ? el("p", { class: "note" }, "No AI-written digest for this refresh — stories are ranked by how many outlets covered them, then recency.",
      d.last_good_digest ? [" Last written digest: ", el("a", { href: `/?tab=digest&date=${d.last_good_digest.date}`, "data-nav": "" }, fmtDate(d.last_good_digest.date)), "."] : null) : null,
    MATCHERS.length ? el("p", { class: "note" }, "Watchlist stories are listed first.") : null,
    items.length ? el("ol", { class: "fallback-list digest-list" }, ...items.map((it, i) => digestItem(it, i, d.ai))) : stateBox("", "No new stories", "Nothing new since the previous refresh."),
    (d.more || []).length ? [el("h2", { class: "section-h", style: "margin-top:20px" }, "More stories"),
      el("ol", { class: "fallback-list" }, ...watchFirst(d.more).map((it, i) => digestItem(it, i, false)))] : null,
    el("p", { class: "note digest-foot" }, META.footer_note)));
}

/* ---------- archive + weekly ---------- */
async function renderArchive() {
  const box = $("#archive");
  box.replaceChildren(stateBox("", "Loading archive…"));
  let idx;
  try { idx = await data("digests/index.json"); } catch (e) { box.replaceChildren(stateBox("error", "Couldn't load the archive", e.message)); return; }
  box.replaceChildren(el("article", { class: "digest" },
    el("div", { class: "digest-head" }, el("h1", {}, "Archive")),
    el("h2", { class: "section-h" }, "Weekly M&A recaps"),
    idx.weekly.length ? el("ul", { class: "archive-list" }, ...idx.weekly.map((w) => el("li", {},
      el("a", { href: `/?tab=weekly&week=${w.week}`, "data-nav": "" }, `Week of ${fmtDate(w.start)}`),
      el("span", { class: "mono muted" }, ` ${w.deal_count} deal${w.deal_count === 1 ? "" : "s"}`)))) : el("p", { class: "muted" }, "No weekly recaps yet (they're written on Fridays)."),
    el("h2", { class: "section-h", style: "margin-top:18px" }, "Daily digests"),
    idx.digests.length ? el("ul", { class: "archive-list" }, ...idx.digests.map((d) => el("li", {},
      el("a", { href: `/?tab=digest&date=${d.date}`, "data-nav": "" }, fmtDate(d.date)),
      el("span", { class: "mono muted" }, ` ${d.item_count} stories`)))) : el("p", { class: "muted" }, "No AI digests have been written yet.")));
}
async function renderWeekly(s) {
  const box = $("#weekly");
  box.replaceChildren(stateBox("", "Loading recap…"));
  let w;
  try {
    const idx = await data("weekly/index.json");
    const week = s.week || (idx.weekly[0] && idx.weekly[0].week);
    if (!week) { box.replaceChildren(stateBox("", "No weekly recap yet", "Recaps are generated on Friday refreshes.")); return; }
    w = await data(`weekly/${week}.json`);
  } catch (e) { box.replaceChildren(stateBox("error", "Couldn't load the recap", e.message)); return; }
  box.replaceChildren(el("article", { class: "digest" },
    el("div", { class: "digest-head digest-head-slim" }, el("span", { class: "digest-label" }, "Weekly M&A recap"),
      el("span", { class: "digest-date" }, `${fmtDate(w.start)} – ${fmtDate(w.end)}`),
      el("a", { class: "digest-file", href: "/?tab=archive", "data-nav": "" }, "← Archive")),
    el("div", { class: "stat-row" },
      el("div", { class: "stat" }, el("b", {}, w.deals.length), el("span", {}, "deals")),
      el("div", { class: "stat" }, el("b", {}, w.total_disclosed_aum_usd ? fmtAum(w.total_disclosed_aum_usd) : "—"), el("span", {}, "disclosed AUM")),
      el("div", { class: "stat" }, el("b", {}, w.top_acquirers[0] ? w.top_acquirers[0].name : "—"), el("span", {}, "most active acquirer"))),
    w.paragraph ? el("p", { class: "digest-opener-p" }, w.paragraph) : el("p", { class: "note" }, "No AI-written summary this week — the numbers below are computed from the M&A tracker."),
    w.top_acquirers.length ? el("p", { class: "note" }, "Most active acquirers: ", w.top_acquirers.map((a) => `${a.name} (${a.deals})`).join(", ")) : null,
    mnaTable(w.deals)));
}

/* ---------- M&A ---------- */
function mnaTable(rows) {
  if (!rows.length) return stateBox("", "No deals", "Deals appear when headlines are categorized as M&A.");
  const blank = (why) => el("span", { class: "blank", title: why }, "—");
  const party = (p) => (p && p.name ? (p.slug ? firmLink(p, "party-link") : p.name) : blank("could not be determined unambiguously"));
  return el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Date", "Acquirer", "Target", "Target AUM", "Type", "Sources", "Confidence"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...rows.map((r) => el("tr", { class: r.confidence === "low" ? "is-low" : "" },
      el("td", { class: "date", "data-label": "Date" }, fmtDay(r.date)),
      el("td", { class: "party", "data-label": r.deal_type === "merger" ? "Party A" : "Acquirer" }, el("div", {}, party(r.acquirer), el("span", { class: "headline" }, r.headline))),
      el("td", { class: "party", "data-label": r.deal_type === "merger" ? "Party B" : "Target" }, party(r.target)),
      el("td", { class: "num", "data-label": "Target AUM" }, r.target_aum_usd
        ? el("span", { class: "aum-cell", title: r.target_aum_source === "sec" ? "SEC-reported AUM" : "From the headline" }, fmtAum(r.target_aum_usd), r.target_aum_source === "sec" ? el("small", { class: "sec-tag" }, " SEC") : null)
        : blank("not stated or ambiguous")),
      el("td", { "data-label": "Type" }, el("span", { class: "deal-type" }, r.deal_type || "—")),
      el("td", { "data-label": "Sources" }, el("div", { class: "srcs" }, ...r.sources.map((x) => extLink(x.url, x.name, "src")))),
      el("td", { "data-label": "Confidence" }, el("div", {},
        el("span", { class: "conf conf-" + r.confidence }, r.confidence === "low" ? "⚠ LOW" : "HIGH"),
        r.press_release ? el("span", { class: "conf-note" }, "press release") : null,
        r.confidence === "low" && r.note ? el("span", { class: "conf-note" }, r.note) : null))))))));
}
async function renderMna(s) {
  for (const a of document.querySelectorAll(".seg a")) a.setAttribute("aria-current", String(a.dataset.conf === s.conf));
  const wrap = $("#mna-wrap");
  try {
    const m = await data("mna.json");
    const rows = s.conf ? m.deals.filter((r) => r.confidence === s.conf) : m.deals;
    wrap.replaceChildren(rows.length ? mnaTable(rows) : stateBox("", s.conf ? `No ${s.conf}-confidence deals` : "No deals yet", "Deals appear when headlines are categorized as M&A."));
  } catch (e) { wrap.replaceChildren(stateBox("error", "Couldn't load the M&A tracker", e.message)); }
}

/* ---------- sources ---------- */
async function renderSources() {
  const wrap = $("#sources-wrap");
  try {
    const { sources } = await data("sources.json");
    wrap.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, ...["Source", "Method", "URL used", "Items", "New", "Dropped", "Notes / failure reason"].map((h) => el("th", {}, h)))),
      el("tbody", {}, ...sources.map((s) => el("tr", { class: s.ok ? "" : "is-low" },
        el("td", { class: "party", "data-label": "Source" }, el("span", {}, el("span", { class: "ok-dot " + (s.ok ? "ok" : "fail") }), s.name)),
        el("td", { "data-label": "Method" }, s.method),
        el("td", { class: "url", "data-label": "URL used" }, s.url_used ? extLink(s.url_used, s.url_used) : "—"),
        el("td", { class: "num", "data-label": "Items" }, s.items_last_run),
        el("td", { class: "num", "data-label": "New" }, s.new_last_run),
        el("td", { class: "num", "data-label": "Dropped" }, s.dropped_last_run || (s.kind === "wire" ? 0 : "—")),
        el("td", { class: "reason", "data-label": s.ok ? "Notes" : "Reason" }, s.reason || (s.ok ? null : "not run yet")))))));
  } catch (e) { wrap.replaceChildren(stateBox("error", "Couldn't load sources", e.message)); }
}

/* ---------- firm page ---------- */
async function renderFirm(s) {
  const box = $("#firm");
  box.replaceChildren(stateBox("", "Loading firm…"));
  let f;
  try { f = await data(`firms/${encodeURIComponent(s.slug)}.json`); } catch (e) {
    box.replaceChildren(stateBox("error", "Firm not found", "No stories mention this firm, or the link is out of date.", el("a", { class: "btn", href: "/", "data-nav": "" }, "Back to the feed"))); return;
  }
  document.title = f.name + " · Wealth Wire";
  const clusters = f.stories.map((st) => CLUSTERS.find((c) => c.id === st.cluster_id)).filter(Boolean);
  box.replaceChildren(el("article", { class: "firm-page" },
    el("div", { class: "view-head" }, el("h1", { class: "view-title" }, f.name)),
    el("dl", { class: "firm-facts" },
      el("dt", {}, "Legal name"), el("dd", {}, f.legal_name),
      el("dt", {}, "Headquarters"), el("dd", {}, [f.city, f.state].filter(Boolean).join(", ") || "—"),
      el("dt", {}, "SEC-reported AUM"), el("dd", {}, f.sec_aum_usd ? el("span", { class: "aum-cell" }, fmtAum(f.sec_aum_usd)) : "—", el("span", { class: "muted" }, ` (as of ${f.sec_aum_as_of})`)),
      el("dt", {}, "CRD"), el("dd", { class: "mono" }, extLink(f.iapd_url, f.crd), el("span", { class: "muted" }, " · SEC# " + (f.sec_number || "—")))),
    el("h2", { class: "section-h" }, `Stories (${f.stories.length})`),
    clusters.length ? el("div", { class: "cards" }, ...clusters.map((c) => card(c))) : el("ul", { class: "archive-list" }, ...f.stories.map((st) => el("li", {}, extLink(st.url, st.headline)))),
    el("h2", { class: "section-h", style: "margin-top:18px" }, `M&A (${f.deals.length})`),
    f.deals.length ? mnaTable(f.deals) : el("p", { class: "muted" }, "No deals involving this firm in the tracker.")));
}

/* ---------- theme ---------- */
function initTheme() {
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("ww-theme", next); } catch (e) { /* private mode */ }
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    let saved = null;
    try { saved = localStorage.getItem("ww-theme"); } catch (err) {}
    if (!saved) document.documentElement.dataset.theme = e.matches ? "dark" : "light";
  });
}

/* ---------- wiring ---------- */
function init() {
  initTheme();
  let t = null;
  $("#q").addEventListener("input", (e) => { clearTimeout(t); const v = e.target.value.trim(); t = setTimeout(() => writeState({ q: v }, true), 200); });
  $("#filters").addEventListener("submit", (e) => { e.preventDefault(); writeState({ q: $("#q").value.trim() }); });
  $("#source").addEventListener("change", (e) => writeState({ source: e.target.value }));
  $("#region").addEventListener("change", (e) => writeState({ region: e.target.value }));
  $("#from").addEventListener("change", (e) => writeState({ from: e.target.value }));
  $("#to").addEventListener("change", (e) => writeState({ to: e.target.value }));
  $("#watch").addEventListener("change", (e) => writeState({ watch: e.target.checked }));
  $("#clear").addEventListener("click", clearFilters);
  $("#cat-chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-cat]");
    if (!b) return;
    const cur = readState().category, cat = b.dataset.cat;
    writeState({ category: cur.includes(cat) ? cur.filter((c) => c !== cat) : [...cur, cat] });
  });
  $("#more").addEventListener("click", () => { feedShown += PAGE; renderFeed(readState(), true); });
  $("#watch-add").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("#watch-name").value.trim();
    const aliases = $("#watch-aliases").value.split(",").map((a) => a.trim()).filter(Boolean);
    if (name.replace(/\s/g, "").length < 3 && !aliases.some((a) => a.replace(/\s/g, "").length >= 3)) {
      setWatch(WATCH, "Use at least 3 characters — shorter names are never matched.", true); return;
    }
    if (WATCH.some((f) => f.name.toLowerCase() === name.toLowerCase())) { setWatch(WATCH, `${name} is already on the watchlist.`, true); return; }
    $("#watch-name").value = ""; $("#watch-aliases").value = "";
    setWatch([...WATCH, { name, aliases }], `Added ${name}.`);
  });
  $("#watch-export").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify({ version: 1, firms: WATCH }, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob), download: "wealth-wire-watchlist.json" });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  $("#watch-import").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try {
      const list = Watch.clean(JSON.parse(await file.text()));
      if (!list.length) throw new Error("no firms found in that file");
      setWatch(list, `Imported ${list.length} firm${list.length > 1 ? "s" : ""}.`);
    } catch (err) { setWatch(WATCH, "Import failed: " + err.message, true); }
  });
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-tab], a[data-conf], a[data-nav]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    if (a.dataset.tab) writeState({ tab: a.dataset.tab });
    else if (a.dataset.conf !== undefined) writeState({ tab: "mna", conf: a.dataset.conf });
    else go(a.getAttribute("href"));
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault();
      if (readState().tab !== "feed") writeState({ tab: "feed" });
      $("#q").focus();
    }
  });
  window.addEventListener("popstate", route);
  route();
}
init();
