/* Fiduciary Wire frontend — vanilla JS, no build step.
   Reads ONLY the static files under /data/ described in DATA-CONTRACT.md. The URL is the source of truth for
   the current view and filters; the watchlist lives in this browser's localStorage. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const TZ = "America/Los_Angeles";
const TABS = ["today", "feed", "mna", "archive", "weekly", "sources", "map"];
const TAB_ALIASES = { digest: "today", deals: "mna" };
// Industry → tag color (meta.json lists the industries; unknown ones fall back to the neutral color)
const CAT_CLASS = {
  "Investment Banking": "cat-mna", "Wealth Management & RIAs": "cat-people", "Banking": "cat-mkt", "Insurance": "cat-reg",
  "Fintech & Payments": "cat-tech", "Private Equity & Asset Management": "cat-prod", "Healthcare & Life Sciences": "cat-reg",
  "Technology": "cat-tech", "Energy & Utilities": "cat-mna", "Industrials": "cat-mkt", "Consumer & Retail": "cat-prod",
  "Real Estate": "cat-people", "Media & Telecom": "cat-tech", "Business Services": "cat-mkt", "Other": "cat-other",
};
// Short labels for tight spots (chips, table cells)
const IND_SHORT = {
  "Wealth Management & RIAs": "Wealth & RIAs", "Private Equity & Asset Management": "PE & Asset Mgmt",
  "Healthcare & Life Sciences": "Healthcare", "Fintech & Payments": "Fintech", "Energy & Utilities": "Energy",
  "Consumer & Retail": "Consumer", "Media & Telecom": "Media & Telecom",
};
const STAGE = { announced: "Announced", completed: "Completed", rumored: "Rumored", bid: "Bid", terminated: "Called off" };
const REGIONS = { "Pacific Northwest": ["WA", "OR", "ID"] };
const STATE_NAMES = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware",
  DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota",
  MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey",
  NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon",
  PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah",
  VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming", PR: "Puerto Rico",
};
const SHORT_OUTLET = {
  "Citywire RIA": "Citywire", "Financial Advisor Magazine": "FA Magazine", "SEC Press Releases": "SEC", "FINRA News": "FINRA",
};
const DEAL_TYPE = { acquisition: "Acquisition", stake: "Minority", merger: "Merger", recapitalization: "Recap" };
const DEAL_VERB = { acquisition: "acquires", stake: "invests in", merger: "merges with", recapitalization: "recapitalizes" };
const SHOW_INDUSTRIES = ["today", "feed", "mna"];
const PAGE = 50;
const WATCH_KEY = "fw-watchlist";
const THEME_KEY = "fw-theme";
// Keys used under the project's earlier names (Wealth Wire → "ww-", Fiduciary Duty → "fd-"). Each is copied to
// the new key once, only if the new key is empty, and then removed, so existing watchlists and themes survive.
const LEGACY_KEYS = { [WATCH_KEY]: ["ww-watchlist"], [THEME_KEY]: ["fd-theme", "ww-theme"] };
function migrateStorage() {
  try {
    for (const [key, olds] of Object.entries(LEGACY_KEYS)) {
      for (const old of olds) {
        const v = localStorage.getItem(old);
        if (v !== null && localStorage.getItem(key) === null) localStorage.setItem(key, v);
        localStorage.removeItem(old);
      }
    }
  } catch (e) { /* storage blocked: nothing to migrate */ }
}
migrateStorage();

/* ---------- data layer: /data/*.json only ---------- */
const cache = new Map();
function data(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch("/data/" + path, { headers: { Accept: "application/json" } }).then(async (r) => {
      if (!r.ok) throw new Error(`Couldn't load ${path} (HTTP ${r.status}).`);
      return r.json();
    }).catch((e) => { cache.delete(path); throw /^Couldn't load/.test(e.message) ? e : new Error(`Couldn't load ${path} (network error).`); }));
  }
  return cache.get(path);
}
async function optional(path, fallback) { try { return await data(path); } catch (e) { return fallback; } }

/* ---------- DOM helpers ---------- */
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (k === "class") n.className = v;
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  const add = (c) => {
    if (c == null || c === false) return;
    if (Array.isArray(c)) c.forEach(add);
    else n.append(c instanceof Node ? c : String(c));
  };
  kids.forEach(add);
  return n;
}
const put = (node, ...kids) => node.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const ext = (href, text, cls) => el("a", { href: safeUrl(href), class: cls, target: "_blank", rel: "noopener" }, text);
const nav = (href, text, cls, extra) => el("a", { href, class: cls, "data-nav": "", ...(extra || {}) }, text);
const pad2 = (n) => String(n).padStart(2, "0");
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;

/* ---------- formatting (Pacific time) ---------- */
const dtf = (opts) => new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts });
const F = {
  key: dtf({ year: "numeric", month: "2-digit", day: "2-digit" }),
  time: dtf({ hour: "numeric", minute: "2-digit" }),
  wday: dtf({ weekday: "short" }),
  long: dtf({ weekday: "long", month: "long", day: "numeric", year: "numeric" }),
  dayHead: dtf({ weekday: "long", month: "long", day: "numeric" }),
  md: dtf({ month: "short", day: "numeric" }),
};
const U = { // dates given as YYYY-MM-DD are calendar dates; format them in UTC so they never shift a day
  long: new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "long", month: "long", day: "numeric", year: "numeric" }),
  mdy: new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" }),
  md: new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" }),
  mdLong: new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "long", day: "numeric" }),
  wday: new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "long" }),
  wdayShort: new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "short" }),
};
function dayKey(ts) { // Pacific calendar date of a timestamp → "YYYY-MM-DD"
  const p = Object.fromEntries(F.key.formatToParts(new Date(ts)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}`;
}
const dateOnly = (d) => new Date(d + "T00:00:00Z");
const fmtDate = (d, f = U.mdy) => (d ? f.format(dateOnly(d)) : "");
const fmtTime = (ts) => F.time.format(new Date(ts));
function addDays(d, n) { const x = dateOnly(d); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); }
function mondayOf(d) { const x = dateOnly(d); const wd = (x.getUTCDay() + 6) % 7; return addDays(d, -wd); }
const todayKey = () => dayKey(Date.now());
const refreshKey = () => (META && META.last_refresh ? dayKey(META.last_refresh) : todayKey()); // "this week" = up to the last refresh
function fmtAum(v) {
  if (v == null || !isFinite(v) || v <= 0) return "—";
  const trim = (x) => x.toFixed(2).replace(/\.?0+$/, "");
  if (v >= 1e12) return "$" + trim(v / 1e12) + "T";
  if (v >= 1e9) return "$" + (v >= 1e11 ? Math.round(v / 1e9) : trim(v / 1e9)) + "B";
  return "$" + Math.round(v / 1e6) + "M";
}
const short = (name) => SHORT_OUTLET[name] || name;

/* ---------- small components ---------- */
function catTag(c) { return el("span", { class: "cat " + (CAT_CLASS[c] || "cat-other"), title: c || "Other" }, IND_SHORT[c] || c || "Other"); }
const industriesOf = (c) => (c && c.industries && c.industries.length ? c.industries : [c && c.category ? c.category : "Other"]);
function indTags(c) { return industriesOf(c).slice(0, 2).map(catTag); }
function dealLine(d, { price = true } = {}) { // "Completed · $2.1B" — stage always, stated price when there is one
  if (!d) return null;
  return el("span", { class: "deal-line" },
    el("span", { class: "stage stage-" + (d.stage || "announced") }, STAGE[d.stage] || "Announced"),
    price && d.value_usd ? el("span", { class: "price", title: "Stated deal value" }, fmtAum(d.value_usd)) : null);
}
const matchesIndustry = (c, sel) => !sel.length || industriesOf(c).some((i) => sel.includes(i));
function aumFig(v, source, asOf, compact) {
  if (!v) return null;
  if (source === "sec") {
    const label = `SEC-reported AUM (as of ${asOf ? fmtDate(asOf) : "the latest SEC file"})`;
    return el("span", { class: "aum aum-sec", title: label },
      fmtAum(v), " ", el("span", { class: "aum-note" }, compact ? "SEC" + (asOf ? " · " + fmtDate(asOf, U.md) : "") : label));
  }
  return el("span", { class: "aum", title: "AUM stated in the headline" }, fmtAum(v), compact ? null : [" ", el("span", { class: "aum-note" }, "AUM")]);
}
function outletList(sources, { prefix = true, shortNames = false } = {}) {
  const list = (sources || []).filter((s) => s && s.name);
  if (!list.length) return null;
  return el("span", { class: "outlets" }, prefix ? "Via" : null,
    list.map((s, i) => [ext(s.url, shortNames ? short(s.name) : s.name), i < list.length - 1 ? "·" : null]));
}
function firmChips(firms) {
  const list = (firms || []).filter((f) => f && f.name);
  if (!list.length) return null;
  return el("span", { class: "firm-chips" }, list.map((f) => (f.slug
    ? nav(`/firm/${encodeURIComponent(f.slug)}`, f.name, "firm-chip")
    : el("span", { class: "firm-chip" }, f.name))));
}
function sectionHead(label, right) { return el("div", { class: "section-head" }, el("span", {}, label), right || null); }
function skeletons(n = 4) { return Array.from({ length: n }, () => el("div", { class: "skeleton", "aria-hidden": "true" }, el("span"), el("span"), el("span"))); }
function errorState(err, retry) {
  return el("p", { class: "state error", role: "alert" }, err.message + " ",
    el("button", { type: "button", onclick: retry || (() => location.reload()) }, "Retry"));
}
function emptyState(text, withClear) {
  return el("p", { class: "state" }, text + (withClear ? " " : ""), withClear ? el("button", { type: "button", onclick: clearFilters }, "Clear filters") : null);
}

/* ---------- watchlist (localStorage; never leaves the browser) ---------- */
const Watch = {
  load() {
    try { return Watch.clean(JSON.parse(localStorage.getItem(WATCH_KEY) || "null")); } catch (e) { return []; }
  },
  clean(raw) {
    const list = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.firms) ? raw.firms : []);
    const out = [], seen = new Set();
    for (const f of list) {
      const name = String((f && (f.name || f)) || "").trim().replace(/\s+/g, " ").slice(0, 80);
      if (!name || seen.has(name.toLowerCase())) continue;
      seen.add(name.toLowerCase());
      const aliases = (f && Array.isArray(f.aliases) ? f.aliases : []).map((a) => String(a).trim()).filter(Boolean).slice(0, 20);
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
function compileWatch() {
  MATCHERS = WATCH.map((f) => {
    const terms = [f.name, ...f.aliases].map((t) => t.trim()).filter((t) => t.replace(/\s/g, "").length >= 3);
    const crds = new Set();
    for (const firm of FIRMS) { // SEC names whose name or legal name starts with a watchlist term (whole words)
      const names = [firm.name, firm.legal_name].filter(Boolean).map(norm);
      if (terms.some((t) => names.some((n) => n === norm(t) || n.startsWith(norm(t) + " ")))) {
        crds.add(firm.crd);
        for (const n of [firm.name, firm.legal_name]) if (n && !terms.includes(n)) terms.push(n);
      }
    }
    const re = terms.length ? new RegExp("(?<![\\w&-])(?:" + terms.slice().sort((a, b) => b.length - a.length)
      .map((t) => escRe(t).replace(/\s+/g, "\\s+")).join("|") + ")(?![\\w&]|-\\w)", "i") : null;
    return { name: f.name, re, crds };
  });
}
function watchHits(c) {
  if (!c) return [];
  const firms = c.firms || [];
  const hits = [];
  for (const m of MATCHERS) {
    if ((m.re && m.re.test(c.headline || "")) || firms.some((f) => f.crd && m.crds.has(f.crd))
      || (m.re && firms.some((f) => m.re.test(f.name || "")))) hits.push(m.name);
  }
  return hits;
}
const itemHits = (it) => watchHits(CL_BY_ID.get(it.cluster_id) || { headline: it.headline, firms: it.firms });

/* ---------- state ---------- */
let META = null, CLUSTERS = [], FIRMS = [], FIRM_BY_SLUG = new Map(), CL_BY_ID = new Map(), SEC_DATE = null;
let feedShown = PAGE;
let prevUrl = null;

function readState() {
  const p = new URLSearchParams(location.search);
  const firm = location.pathname.match(/^\/firm\/([^/]+)\/?$/);
  let tab = p.get("tab") || "today";
  tab = TAB_ALIASES[tab] || tab;
  if (!TABS.includes(tab)) tab = "today";
  return {
    tab: firm ? "firm" : tab, slug: firm ? decodeURIComponent(firm[1]) : "",
    q: p.get("q") || "", source: p.get("source") || "",
    industry: (p.get("industry") || p.get("category") || "").split(",").filter(Boolean),   // "category" = links from before
    region: p.get("region") || "", when: p.get("when") || "", from: p.get("from") || "", to: p.get("to") || "",
    watch: p.get("watch") === "1", conf: p.get("conf") || "", sort: p.get("sort") || "date", dir: p.get("dir") === "asc" ? 1 : -1,
    date: p.get("date") || "", week: p.get("week") || "",
  };
}
function stateUrl(s) {
  const p = new URLSearchParams();
  if (s.tab !== "today") p.set("tab", s.tab);
  if (SHOW_INDUSTRIES.includes(s.tab) && s.industry.length) p.set("industry", s.industry.join(","));
  if (s.tab === "feed") {
    if (s.q) p.set("q", s.q);
    if (s.source) p.set("source", s.source);
    if (s.region) p.set("region", s.region);
    if (s.when) p.set("when", s.when);
    if (s.when === "range" && s.from) p.set("from", s.from);
    if (s.when === "range" && s.to) p.set("to", s.to);
    if (s.watch) p.set("watch", "1");
  }
  if (s.tab === "mna") {
    if (s.conf) p.set("conf", s.conf);
    if (s.sort !== "date") p.set("sort", s.sort);
    if (s.dir === 1) p.set("dir", "asc");
  }
  if (s.tab === "today" && s.date) p.set("date", s.date);
  if (s.tab === "weekly" && s.week) p.set("week", s.week);
  const qs = p.toString();
  return "/" + (qs ? "?" + qs : "");
}
function writeState(patch, replace = false) {
  const s = { ...readState(), ...patch };
  if (s.tab === "firm") s.tab = "today";
  const url = stateUrl(s);
  if (url !== location.pathname + location.search) {
    if (!replace) prevUrl = location.pathname + location.search;
    history[replace ? "replaceState" : "pushState"](null, "", url);
  }
  route();
}
function go(href) {
  if (href === location.pathname + location.search) return;
  prevUrl = location.pathname + location.search;
  history.pushState(null, "", href);
  route();
}
function clearFilters() { feedShown = PAGE; writeState({ tab: "feed", q: "", source: "", industry: [], region: "", when: "", from: "", to: "", watch: false }); }

/* ---------- core data + chrome ---------- */
async function loadCore() {
  const [meta, clusters, firms] = await Promise.all([data("meta.json"), data("clusters.json"), optional("firms/index.json", { firms: [] })]);
  META = meta;
  CLUSTERS = (clusters && clusters.clusters) || [];
  CL_BY_ID = new Map(CLUSTERS.map((c) => [c.id, c]));
  FIRMS = (firms && firms.firms) || [];
  FIRM_BY_SLUG = new Map(FIRMS.map((f) => [f.slug, f]));
  SEC_DATE = (meta.sec && meta.sec.data_date) || (firms && firms.sec_data_date) || null;
  compileWatch();
  renderChrome();
  fillFeedControls();
  fillIndustryBar();
}
function fillIndustryBar() { // one chip per industry that has deals, with its count
  const counts = new Map();
  for (const c of CLUSTERS) for (const i of industriesOf(c)) counts.set(i, (counts.get(i) || 0) + 1);
  const names = ((META && (META.industries || META.categories)) || Object.keys(CAT_CLASS)).filter((i) => counts.get(i));
  put($("#ind-bar"), el("button", { type: "button", class: "all", "data-ind": "" }, "All industries"),
    names.map((i) => el("button", { type: "button", class: CAT_CLASS[i] || "cat-other", "data-ind": i, title: i },
      IND_SHORT[i] || i, el("span", { class: "n" }, String(counts.get(i))))));
}
function syncIndustryBar(s) {
  // the section tabs keep the industry selection when you move between Today, Feed and Deals
  const blank = { q: "", source: "", region: "", when: "", from: "", to: "", watch: false, conf: "", sort: "date", dir: -1, date: "", week: "" };
  for (const a of document.querySelectorAll(".sections a[data-tab]")) {
    if (SHOW_INDUSTRIES.includes(a.dataset.tab)) a.setAttribute("href", stateUrl({ ...blank, tab: a.dataset.tab, industry: s.industry }));
  }
  const bar = $("#ind-bar");
  bar.hidden = !SHOW_INDUSTRIES.includes(s.tab) || !!(s.tab === "today" && s.date);
  for (const b of bar.querySelectorAll("button")) {
    const i = b.dataset.ind;
    b.setAttribute("aria-pressed", String(i ? s.industry.includes(i) : !s.industry.length));
  }
}
function renderChrome() {
  $("#today-date").textContent = F.long.format(new Date());
  if (META && META.last_refresh) {
    const t = new Date(META.last_refresh);
    const sameDay = dayKey(t) === todayKey();
    $("#updated").textContent = "Updated " + (sameDay ? "" : F.md.format(t) + ", ") + fmtTime(t) + " PT";
  }
  $("#demo-note").hidden = !(META && META.demo);
  $("#footer-note").textContent = (META && META.footer_note) || $("#footer-note").textContent;
  $("#watch-open").textContent = `Watchlist (${WATCH.length})`;
  themeLabel();
}

async function route() {
  const s = readState();
  for (const t of [...TABS, "firm"]) $("#view-" + t).hidden = t !== s.tab;
  const current = s.tab === "weekly" || (s.tab === "today" && s.date) ? "archive" : s.tab;
  for (const a of document.querySelectorAll(".sections a")) a.setAttribute("aria-selected", String(a.dataset.tab === current));
  const TITLES = { feed: "Feed", mna: "Deals", archive: "Archive", weekly: "Weekly M&A recap", sources: "Sources", map: "RIA map" };
  document.title = (TITLES[s.tab] ? TITLES[s.tab] + " · " : "") + "Fiduciary Wire";
  if (!META) {
    const view = $("#view-" + s.tab);
    const target = s.tab === "feed" ? $("#feed-list") : view;
    put(target, ...skeletons(5));
    try { await loadCore(); } catch (e) { put(target, errorState(e, () => location.reload())); return; }
  }
  syncIndustryBar(s);
  ({ today: renderToday, feed: renderFeed, mna: renderDeals, archive: renderArchive, weekly: renderWeekly, sources: renderSources,
    firm: renderFirm, map: renderMap })[s.tab](s);
}

/* ---------- side column ---------- */
async function trendingBlock() {
  const t = await optional("trending.json", { firms: [], days: 7 });
  const list = (t.firms || []).slice(0, 10);
  return [
    sectionHead("Active advisers", el("span", { class: "muted", style: "font-weight:500" }, `Deals, ${t.days || 7} days`)),
    list.length ? el("ol", { class: "rank-list" }, list.map((f, i) => el("li", {},
      el("span", { class: "rank" }, pad2(i + 1)),
      f.slug ? nav(`/firm/${encodeURIComponent(f.slug)}`, f.name, "name") : el("span", { class: "name" }, f.name),
      el("span", { class: "n" }, f.stories)))) : el("p", { class: "side-empty" }, "No SEC-registered advisers in this week's deals yet."),
  ];
}
function industriesBlock(s) { // deals per industry over the last seven days; each links to that filter
  const since = addDays(refreshKey(), -7);
  const counts = new Map();
  for (const c of CLUSTERS) if (dayKey(c.last_published) >= since) for (const i of industriesOf(c)) counts.set(i, (counts.get(i) || 0) + 1);
  const ranked = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return [
    sectionHead("Deals by industry", el("span", { class: "muted", style: "font-weight:500" }, "7 days")),
    ranked.length ? el("ol", { class: "rank-list" }, ranked.map(([i, n]) => el("li", {},
      el("span", { class: "rank cat " + (CAT_CLASS[i] || "cat-other") }, "●"),
      nav(`/?tab=feed&industry=${encodeURIComponent(i)}`, i, "name", { "aria-current": String(s.industry.includes(i)) }),
      el("span", { class: "n" }, n)))) : el("p", { class: "side-empty" }, "No deals in the last seven days."),
  ];
}
async function dealsThisWeekBlock(s) {
  const m = await optional("mna.json", { deals: [] });
  const since = addDays(refreshKey(), -7);
  const rows = (m.deals || []).filter((d) => dayKey(d.date) >= since && (d.value_usd || headlineAum(d)) && matchesIndustry(d, s.industry))
    .sort((a, b) => (b.value_usd || 0) - (a.value_usd || 0)).slice(0, 6);
  return [
    sectionHead("Largest deals this week", nav("/?tab=mna", "All deals", "textbtn")),
    rows.length ? rows.map((d) => nav("/?tab=mna", [
      el("span", {}, d.acquirer.name || "Not named", " ", el("span", { class: "muted" }, "/"), " ", d.target.name || "Not named"),
      d.value_usd ? el("span", { class: "aum price" }, fmtAum(d.value_usd)) : el("span", { class: "aum", title: "Target AUM" }, fmtAum(headlineAum(d)) + " AUM"),
    ], "side-deal")) : el("p", { class: "side-empty" }, "No deals with a stated price or AUM in the last seven days."),
  ];
}

/* ---------- Today ---------- */
function stamp(ts, dayOf) {
  if (!ts) return "";
  const k = dayKey(ts);
  return (k === dayOf ? "" : F.wday.format(new Date(ts)) + " ") + fmtTime(ts);
}
function storyItem(it, n, ai, dayOf) {
  const c = CL_BY_ID.get(it.cluster_id);
  const hits = itemHits(it);
  const firms = (c && c.firms && c.firms.length ? c.firms : it.firms) || [];
  return el("article", { class: "story" + (hits.length ? " is-watch" : "") },
    el("div", { class: "story-n", "aria-hidden": "true" }, pad2(n)),
    el("div", { class: "story-body" },
      el("div", { class: "story-kicker" },
        hits.length ? el("span", { class: "watch-mark" }, "Watchlist · " + hits.join(", ")) : null,
        indTags(c || it), dealLine((c && c.deal) || it.deal),
        c ? el("time", { class: "stamp", datetime: c.first_published }, stamp(c.first_published, dayOf)) : null,
        it.aum_usd ? el("span", { class: "aum-wrap" }, aumFig(it.aum_usd, it.aum_source, (c && c.sec_aum_as_of) || SEC_DATE)) : null),
      el("h3", {}, ext(it.url, it.headline)),
      ai && it.summary ? el("p", { class: "sum" }, it.summary) : null,
      ai && it.why_it_matters ? el("p", { class: "why" }, el("em", {}, "Why it matters:"), " ", it.why_it_matters) : null,
      el("div", { class: "story-foot" }, outletList(it.sources), firmChips(firms))));
}
async function renderToday(s) {
  const box = $("#view-today");
  put(box, el("div", { class: "cols" }, el("div", { class: "col-main" }, skeletons(4))));
  let d;
  try { d = s.date ? await data(`digests/${s.date}.json`) : await data("digest.json"); } catch (e) {
    put(box, errorState(e, () => renderToday(s))); return;
  }
  const sel = s.date ? [] : s.industry;
  const inSel = (it) => matchesIndustry(CL_BY_ID.get(it.cluster_id) || it, sel);
  const all = d.items || [];
  const items = all.filter(inSel);
  const watched = [], rest = [];
  for (const it of items) (itemHits(it).length ? watched : rest).push(it);
  const ai = !!d.ai;
  const main = el("div", { class: "col-main" });
  main.append(el("div", { class: "kicker" }, s.date ? "Digest · " + fmtDate(d.date, U.long) : "Today in deals"));
  if (ai && d.opener && !sel.length) main.append(el("p", { class: "opener" }, d.opener));
  else if (!ai) {
    const last = d.last_good_digest;
    main.append(el("p", { class: "note", style: "margin:10px 0 12px" },
      "The day's summaries aren't available, so the deals below are ranked by how many outlets covered them.",
      last && last.date !== d.date ? [" ", nav(`/?tab=today&date=${last.date}`, `Read the last written digest (${fmtDate(last.date, U.long)})`), "."] : null));
  }
  main.append(el("div", { class: "meta-line digest-meta" },
    sel.length ? `${plural(items.length, "deal")} in ${sel.map((i) => IND_SHORT[i] || i).join(", ")} · of ${all.length} today`
      : `${plural(items.length, "deal")} · ${watched.length} from your watchlist · About two minutes`));
  let n = 0;
  if (watched.length) {
    main.append(sectionHead("From your watchlist", el("button", { class: "textbtn", type: "button", onclick: openDrawer }, "Edit")));
    watched.forEach((it) => main.append(storyItem(it, ++n, ai, d.date)));
    main.append(el("div", { class: "section-gap" }));
  }
  main.append(sectionHead("Top deals"));
  if (!rest.length && !watched.length) main.append(sel.length
    ? el("p", { class: "state" }, "No deals in these industries in today's digest. ", nav(stateUrl({ ...s, tab: "feed" }), "See all of them in the Feed"))
    : el("p", { class: "state" }, "No new deals since the previous refresh."));
  rest.forEach((it) => main.append(storyItem(it, ++n, ai, d.date)));
  const more = (d.more || []).filter(inSel);
  if (more.length) {
    main.append(el("div", { class: "section-gap" }), sectionHead("More deals"));
    more.forEach((it) => main.append(feedRow(CL_BY_ID.get(it.cluster_id) || itemAsCluster(it))));
  }
  const friday = await fridayLine(d.date);
  if (friday) main.append(friday);
  const side = el("aside", { class: "col-side", "aria-label": "Deals by industry and largest deals" });
  put(box, el("div", { class: "cols" }, main, side));
  put(side, industriesBlock(s), await dealsThisWeekBlock(s), await trendingBlock());
}
function itemAsCluster(it) {
  return { id: it.cluster_id, headline: it.headline, url: it.url, category: it.category, industries: it.industries, deal: it.deal,
    sources: it.sources || [], firms: it.firms || [], aum_usd: it.aum_usd, aum_source: it.aum_source, sec_aum_as_of: SEC_DATE, last_published: null };
}
async function fridayLine(date) {
  if (!date || U.wday.format(dateOnly(date)) !== "Friday") return null;
  const idx = await optional("weekly/index.json", { weekly: [] });
  const w = (idx.weekly || []).find((x) => x.start <= date && date <= x.end);
  if (!w) return null;
  const rec = await optional(`weekly/${w.week}.json`, null);
  const n = rec ? rec.deals.length : w.deal_count;
  const total = rec && rec.total_disclosed_value_usd ? `, ${fmtAum(rec.total_disclosed_value_usd)} in disclosed prices` : "";
  return el("p", { class: "note friday" }, `It's Friday, so the weekly M&A recap is out: ${plural(n, "deal")}${total}. `,
    nav(`/?tab=weekly&week=${w.week}`, "Read the recap"));
}

/* ---------- Feed ---------- */
function fillFeedControls() {
  const src = $("#source");
  const names = [...new Set(CLUSTERS.flatMap((c) => c.sources.map((x) => x.name)))].sort((a, b) => a.localeCompare(b));
  put(src, el("option", { value: "" }, "All outlets"), names.map((n) => el("option", { value: n }, n)));
  const states = [...new Set(CLUSTERS.flatMap((c) => c.states || []))].sort((a, b) => (STATE_NAMES[a] || a).localeCompare(STATE_NAMES[b] || b));
  put($("#region"), el("option", { value: "" }, "All regions"), el("option", { value: "Pacific Northwest" }, "Pacific Northwest"),
    states.map((st) => el("option", { value: st }, STATE_NAMES[st] || st)));
}
function whenCutoff(when) {
  const t = todayKey();
  if (when === "today") return t;
  if (when === "3d") return addDays(t, -2);
  if (when === "week") return mondayOf(t);
  return null;
}
function filterClusters(s) {
  const terms = (s.q.toLowerCase().match(/[\w$&.'-]+/g) || []).map((t) => t.replace(/^[.'-]+|[.'-]+$/g, "")).filter(Boolean);
  const states = s.region ? (REGIONS[s.region] || [s.region]) : null;
  const cutoff = whenCutoff(s.when);
  const from = s.when === "range" && s.from ? s.from : null;
  const to = s.when === "range" && s.to ? s.to : null;
  return CLUSTERS.filter((c) => {
    if (!matchesIndustry(c, s.industry)) return false;
    if (s.source && !c.sources.some((x) => x.name === s.source)) return false;
    if (states && !(c.states || []).some((st) => states.includes(st))) return false;
    const day = dayKey(c.last_published);
    if (cutoff && day < cutoff) return false;
    if (from && day < from) return false;
    if (to && dayKey(c.first_published) > to) return false;
    if (terms.length) {
      const words = [c.headline, ...c.firms.map((f) => f.name), ...c.sources.map((x) => x.name), ...industriesOf(c),
        ...(c.deal ? [c.deal.acquirer, c.deal.target] : [])].filter(Boolean).join(" ").toLowerCase().match(/[\w$&.'-]+/g) || [];
      if (!terms.every((t) => words.some((w) => w.startsWith(t)))) return false;
    }
    if (s.watch && !watchHits(c).length) return false;
    return true;
  });
}
function highlight(text, q) {
  const terms = (q || "").split(/\s+/).map((t) => t.replace(/[^\w$.&'-]/g, "")).filter((t) => t.length > 1);
  if (!terms.length) return [text];
  const re = new RegExp("(" + terms.map(escRe).join("|") + ")", "ig");
  return text.split(re).map((part, i) => (i % 2 ? el("mark", {}, part) : part));
}
function feedRow(c, { q = "", timeLabel } = {}) {
  const hits = watchHits(c);
  const t = timeLabel !== undefined ? timeLabel : (c.last_published ? fmtTime(c.last_published) : "");
  const price = c.deal && c.deal.value_usd;
  return el("div", { class: "row" + (hits.length ? " is-watch" : "") },
    el("span", { class: "t" }, c.last_published ? el("time", { datetime: c.last_published }, t) : t),
    el("div", { class: "row-main" },
      el("a", { class: "row-h", href: safeUrl(c.url), target: "_blank", rel: "noopener" }, ...highlight(c.headline, q)),
      el("div", { class: "row-meta" },
        hits.length ? el("span", { class: "watch-mark", title: "Watchlist: " + hits.join(", ") }, "Watchlist") : null,
        indTags(c), dealLine(c.deal, { price: false }), outletList(c.sources, { prefix: false, shortNames: true }), firmChips(c.firms))),
    price ? el("span", { class: "aum price", title: "Stated deal value" }, fmtAum(price), el("span", { class: "aum-note" }, " price"))
      : c.aum_usd ? aumFig(c.aum_usd, c.aum_source, c.sec_aum_as_of || SEC_DATE, true) : el("span"));
}
function syncFeedControls(s) {
  if (document.activeElement !== $("#q")) $("#q").value = s.q;
  $("#source").value = s.source;
  $("#region").value = s.region;
  $("#when").value = s.when;
  $("#range").hidden = s.when !== "range";
  $("#from").value = s.from; $("#to").value = s.to;
  $("#watch").checked = s.watch;
}
async function renderFeed(s, append = false) {
  syncFeedControls(s);
  const list = filterClusters(s);
  const outlets = new Set(list.flatMap((c) => c.sources.map((x) => x.name))).size;
  $("#feed-count").textContent = `${plural(list.length, "deal")} · ${plural(outlets, "outlet")} · Newest first`;
  const box = $("#feed-list");
  if (!append) feedShown = PAGE;
  if (!list.length) {
    const filtered = s.q || s.source || s.industry.length || s.region || s.when || s.watch;
    put(box, emptyState(CLUSTERS.length ? (filtered ? "No deals match these filters." : "No deals yet.") : "No deals yet. The next refresh will fill this in.", !!filtered));
  } else {
    const frag = [];
    let day = null;
    for (const c of list.slice(0, feedShown)) {
      const k = dayKey(c.last_published);
      if (k !== day) { day = k; frag.push(el("div", { class: "day-head" }, F.dayHead.format(new Date(c.last_published)))); }
      frag.push(feedRow(c, { q: s.q }));
    }
    put(box, ...frag);
  }
  $("#more").hidden = feedShown >= list.length;
  put($("#feed-side"), industriesBlock(s), ...(await trendingBlock()));
}

/* ---------- Deals ---------- */
const headlineAum = (d) => (d.target_aum_source === "headline" ? d.target_aum_usd : null);
function secAum(d, asOfDefault) {
  if (d.target_aum_source === "sec" && d.target_aum_usd) return { v: d.target_aum_usd, asOf: asOfDefault };
  const f = d.target && d.target.slug ? FIRM_BY_SLUG.get(d.target.slug) : null;
  return f && f.sec_aum_usd ? { v: f.sec_aum_usd, asOf: asOfDefault } : { v: null, asOf: null };
}
function party(p) {
  if (!p || !p.name) return el("span", { class: "party none" }, "Not named");
  return p.slug ? nav(`/firm/${encodeURIComponent(p.slug)}`, p.name, "party") : el("span", { class: "party" }, p.name);
}
// Target AUM: the figure stated in coverage, else the target's SEC-reported (Form ADV) AUM
const targetAum = (d) => (headlineAum(d) ? { v: headlineAum(d), sec: false } : d._sec.v ? { v: d._sec.v, sec: true, asOf: d._sec.asOf } : { v: null });
const SORTS = {
  date: (d) => d.date, acq: (d) => (d.acquirer.name || "~").toLowerCase(), tgt: (d) => (d.target.name || "~").toLowerCase(),
  ind: (d) => industriesOf(d)[0], type: (d) => DEAL_TYPE[d.deal_type] || "~", stage: (d) => STAGE[d.stage] || "~",
  p: (d) => d.value_usd ?? -1, a: (d) => targetAum(d).v ?? -1,
};
const NUMERIC_SORT = ["date", "p", "a"];
function aumCell(d) {
  const t = targetAum(d);
  if (!t.v) return el("span", { class: "aum muted" }, "—");
  return t.sec ? el("span", { class: "aum aum-sec", title: `SEC-reported AUM (as of ${fmtDate(t.asOf)})` }, fmtAum(t.v), el("span", { class: "asof" }, "SEC " + fmtDate(t.asOf, U.md)))
    : el("span", { class: "aum", title: "AUM stated in coverage" }, fmtAum(t.v));
}
function sortDeals(rows, key, dir) {
  const f = SORTS[key] || SORTS.date;
  return rows.slice().sort((a, b) => { const x = f(a), y = f(b); return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir; });
}
function dealsBlock(rows, asOf, sort, onSort) {
  rows = rows.map((d) => ({ ...d, _sec: secAum(d, asOf) }));
  const sorted = sortDeals(rows, sort.key, sort.dir);
  const cols = [["Date", "date"], ["Acquirer", "acq"], ["Target", "tgt"], ["Industry", "ind"], ["Type", "type"], ["Stage", "stage"],
    ["Price", "p", "r"], ["Target AUM", "a", "r"], ["Sources", null]];
  const table = el("table", { class: "deals-table" },
    el("thead", {}, el("tr", {}, cols.map(([label, key, align]) => {
      const active = key && sort.key === key;
      return el("th", { class: align || null, scope: "col", "aria-sort": active ? (sort.dir < 0 ? "descending" : "ascending") : null },
        key ? el("button", { type: "button", onclick: () => onSort(key, active ? -sort.dir : (NUMERIC_SORT.includes(key) ? -1 : 1)) },
          label, " ", el("span", { class: "arrow", "aria-hidden": "true" }, active ? (sort.dir < 0 ? "↓" : "↑") : "")) : label);
    }))),
    el("tbody", {}, sorted.map((d) => el("tr", { class: d.confidence === "low" ? "is-low" : null },
      el("td", { class: "date" }, F.md.format(new Date(d.date))),
      el("td", {}, party(d.acquirer)),
      el("td", {}, party(d.target), d.confidence === "low" ? el("div", { class: "review" }, "Needs review: " + (d.note || "the parser couldn't read this headline unambiguously.")) : null),
      el("td", { class: "ind" }, indTags(d)),
      el("td", { class: "deal-type" }, DEAL_TYPE[d.deal_type] || "—"),
      el("td", {}, dealLine({ stage: d.stage }, { price: false })),
      el("td", { class: "r" }, el("span", { class: "aum price" }, fmtAum(d.value_usd))),
      el("td", { class: "r" }, aumCell(d)),
      el("td", { class: "deal-srcs" }, outletList(d.sources, { prefix: false, shortNames: true }))))));
  const sortSel = el("select", { class: "input", "aria-label": "Sort deals by", onchange: (e) => onSort(e.target.value, NUMERIC_SORT.includes(e.target.value) ? -1 : 1) },
    [["date", "Newest"], ["p", "Price"], ["a", "Target AUM"], ["ind", "Industry"], ["acq", "Acquirer"], ["tgt", "Target"]].map(([v, l]) => el("option", { value: v, selected: sort.key === v }, l)));
  const cards = el("div", { class: "deal-cards" }, sorted.map((d) => el("div", { class: "deal-card" + (d.confidence === "low" ? " is-low" : "") },
    el("div", { class: "dc-top" }, F.md.format(new Date(d.date)), " · ", DEAL_TYPE[d.deal_type] || "Deal", " · ", indTags(d)),
    el("div", { class: "dc-line" }, party(d.acquirer), " ", el("span", { class: "verb" }, DEAL_VERB[d.deal_type] || "and"), " ", party(d.target)),
    el("dl", {},
      el("dt", {}, "Stage"), el("dd", {}, dealLine({ stage: d.stage }, { price: false })),
      el("dt", {}, "Price"), el("dd", {}, el("span", { class: "aum price" }, fmtAum(d.value_usd))),
      el("dt", {}, "Target AUM"), el("dd", {}, aumCell(d)),
      el("dt", {}, "Sources"), el("dd", {}, (d.sources || []).map((x) => short(x.name)).join(", "))),
    d.confidence === "low" ? el("div", { class: "review" }, "Needs review: " + (d.note || "")) : null)));
  return [el("div", { class: "sort-bar" }, el("span", {}, "Sort by"), sortSel), table, cards];
}
async function renderDeals(s) {
  const box = $("#view-mna");
  put(box, ...skeletons(5));
  let m;
  try { m = await data("mna.json"); } catch (e) { put(box, errorState(e, () => renderDeals(s))); return; }
  const rows = (m.deals || []).filter((d) => (!s.conf || d.confidence === s.conf) && matchesIndustry(d, s.industry));
  const keep = (conf) => stateUrl({ ...s, tab: "mna", conf });
  const seg = el("div", { class: "seg", role: "group", "aria-label": "Confidence" },
    [["All", ""], ["Confirmed", "high"], ["Needs review", "low"]].map(([l, v]) => nav(keep(v), l, null, { "aria-current": String(s.conf === v) })));
  put(box,
    el("div", { class: "page-head" }, el("h1", { class: "page-title" }, "Deals"), seg),
    el("p", { class: "prose", style: "margin:0 0 18px" }, "Mergers, acquisitions and stakes across industries, one row per deal. ",
      el("em", {}, "Price"), " is the deal value stated in coverage. ", el("em", {}, "Target AUM"),
      " applies to wealth and asset-management deals: the figure stated in coverage, or the target's SEC-reported AUM from Form ADV. ",
      "Rows the parser couldn't read unambiguously are marked for review and left blank rather than guessed."),
    s.industry.length ? el("p", { class: "meta-line", style: "margin:-8px 0 14px" }, `${plural(rows.length, "deal")} in ${s.industry.join(", ")}`) : null,
    rows.length ? el("div", {}, dealsBlock(rows, m.sec_aum_as_of || SEC_DATE, { key: s.sort, dir: s.dir },
      (key, dir) => writeState({ tab: "mna", sort: key, dir }, true)))
      : el("p", { class: "state" }, s.conf || s.industry.length ? "No deals match these filters. " : "No deals yet. ",
        s.conf || s.industry.length ? nav("/?tab=mna", "Show all deals") : null));
}

/* ---------- RIA map (frontend/map.js, loaded on first visit) ---------- */
let mapScript = null;
function renderMap() {
  const box = $("#view-map");
  if (box.dataset.mounted) return;   // the map keeps its own state (view, selection, filters in the URL)
  put(box, ...skeletons(3));
  mapScript = mapScript || new Promise((resolve, reject) => {
    const s = el("script", { src: "/map.js", async: true });
    s.onload = resolve;
    s.onerror = () => reject(new Error("Couldn't load the map (network error)."));
    document.head.append(s);
  });
  mapScript.then(() => {
    box.dataset.mounted = "1";
    window.FWMap.mount(box, {
      el, put, fmtAum, ext, nav, plural, fmtDate: (d) => fmtDate(d),
      isWatched: (crd, name) => MATCHERS.some((m) => m.crds.has(String(crd)) || (m.re && m.re.test(name))),
      addWatch: (name) => { if (!WATCH.some((w) => norm(w.name) === norm(name))) setWatch([...WATCH, { name, aliases: [] }], `Added ${name}.`); },
    });
  }).catch((e) => { mapScript = null; put(box, errorState(e, renderMap)); });
}

/* ---------- Firm page ---------- */
function firmWatched(f) {
  return MATCHERS.some((m) => m.crds.has(f.crd)) || WATCH.some((w) => norm(w.name) === norm(f.name));
}
async function renderFirm(s) {
  const box = $("#view-firm");
  put(box, ...skeletons(3));
  let f;
  try { f = await data(`firms/${encodeURIComponent(s.slug)}.json`); } catch (e) {
    put(box, el("div", { class: "firm" }, backLink(),
      el("p", { class: "state error", role: "alert" }, /HTTP 404/.test(e.message) ? "There's no firm page at this address. " : e.message + " ",
        el("button", { type: "button", onclick: () => renderFirm(s) }, "Retry"))));
    return;
  }
  document.title = f.name + " · Fiduciary Wire";
  const place = [f.city, f.state ? (STATE_NAMES[f.state] || f.state) : null].filter(Boolean).join(", ");
  const watched = firmWatched(f);
  const deals = f.deals || [];
  const stories = (f.stories || []).slice().sort((a, b) => (b.last_published || "").localeCompare(a.last_published || ""));
  put(box, el("div", { class: "firm" },
    backLink(),
    el("div", { class: "firm-head" },
      el("h1", { class: "firm-name" }, f.name),
      el("button", { class: "btn", type: "button", onclick: () => toggleFirmWatch(f) }, watched ? "On your watchlist · Remove" : "Add to watchlist")),
    el("div", { class: "firm-place" }, place ? place + " · Registered investment adviser" : "Registered investment adviser"),
    f.legal_name && norm(f.legal_name) !== norm(f.name) ? el("div", { class: "firm-legal" }, "Legal name: " + f.legal_name) : null,
    el("dl", { class: "facts" },
      el("div", {}, el("dt", {}, "SEC-reported AUM"), el("dd", { class: "big" }, fmtAum(f.sec_aum_usd)),
        el("dd", {}, f.sec_aum_as_of ? `Form ADV, as of ${fmtDate(f.sec_aum_as_of)}` : "No AUM reported")),
      el("div", {}, el("dt", {}, "CRD number"), el("dd", { class: "big" }, f.crd || "—"),
        el("dd", {}, f.iapd_url ? ext(f.iapd_url, "SEC adviser page ↗") : null, f.crd ? [" · ", nav(`/?tab=map&firm=${f.crd}`, "On the RIA map")] : null)),
      el("div", {}, el("dt", {}, "Coverage"), el("dd", { class: "big" }, plural(stories.length, "deal")),
        el("dd", {}, deals.length ? plural(deals.length, "deal") + " in the tracker" : "No deals in the tracker"))),
    el("div", { class: "block-gap" }, sectionHead("Coverage"),
      stories.length ? stories.map((st) => feedRow(CL_BY_ID.get(st.cluster_id) || { ...st, id: st.cluster_id, firms: [], aum_usd: null },
        { timeLabel: st.last_published ? F.md.format(new Date(st.last_published)) : "" })) : el("p", { class: "state" }, "No deals yet.")),
    deals.length ? el("div", { class: "block-gap" }, sectionHead("Deals"), deals.map((d) => {
      const sec = secAum(d, SEC_DATE);
      return el("div", { class: "firm-deal" + (d.confidence === "low" ? " is-low" : "") },
        el("span", { class: "t" }, F.md.format(new Date(d.date))),
        el("span", { class: "line" }, party(d.acquirer), " ", el("span", { class: "verb" }, DEAL_VERB[d.deal_type] || "and"), " ", party(d.target),
          el("span", { class: "role" }, d.role === "acquirer" ? (d.deal_type === "merger" ? "Party" : "Acquirer") : "Target")),
        el("span", { class: "figs" }, d.value_usd ? el("span", { class: "aum price" }, fmtAum(d.value_usd)) : null, " ",
          el("span", { class: "aum" }, headlineAum(d) ? fmtAum(headlineAum(d)) : ""), " ",
          sec.v ? el("span", { class: "aum aum-sec", title: `SEC-reported AUM (as of ${fmtDate(sec.asOf)})` }, "SEC " + fmtAum(sec.v)) : null));
    })) : null));
}
function backLink() {
  return el("a", { class: "back", href: prevUrl || "/", onclick: (e) => {
    e.preventDefault();
    if (prevUrl) history.back(); else go("/");
  } }, "← Back");
}
function toggleFirmWatch(f) {
  if (firmWatched(f)) {
    const drop = new Set(MATCHERS.filter((m) => m.crds.has(f.crd)).map((m) => m.name.toLowerCase()));
    setWatch(WATCH.filter((w) => !drop.has(w.name.toLowerCase()) && norm(w.name) !== norm(f.name)));
  } else setWatch([...WATCH, { name: f.name, aliases: [] }]);
}

/* ---------- Archive + weekly ---------- */
async function renderArchive() {
  const box = $("#view-archive");
  put(box, ...skeletons(4));
  let idx;
  try { idx = await data("digests/index.json"); } catch (e) { put(box, errorState(e, renderArchive)); return; }
  const digests = idx.digests || [], weekly = idx.weekly || [];
  const fridays = new Map(weekly.map((w) => [w.end, w]));
  const main = el("div", { class: "col-main" }, el("h1", { class: "page-title", style: "margin-bottom:16px" }, "Archive"));
  if (!digests.length) main.append(el("p", { class: "state" }, "No digests archived yet. A day's digest is archived once its summaries are written."));
  const weeks = new Map();
  for (const d of digests) { const k = mondayOf(d.date); if (!weeks.has(k)) weeks.set(k, []); weeks.get(k).push(d); }
  for (const [monday, days] of weeks) {
    main.append(sectionHead("Week of " + fmtDate(monday, U.mdLong)));
    for (const d of days) {
      const lead = el("span", { class: "lead" }, plural(d.item_count, "deal"));
      const recap = fridays.get(d.date);
      main.append(nav(`/?tab=today&date=${d.date}`, [
        el("span", { class: "when" }, fmtDate(d.date, U.wday), el("br"), fmtDate(d.date, U.md)),
        el("span", {}, lead, el("span", { class: "meta-line" }, plural(d.item_count, "deal") + (recap ? " · Weekly M&A recap" : ""))),
      ], "arch-row"));
      optional(`digests/${d.date}.json`, null).then((full) => {
        if (!full) return;
        const first = full.items && full.items[0] ? full.items[0].headline : (full.opener || "").split(/[.;:]/)[0];
        if (first) lead.textContent = first;
      });
    }
  }
  if (digests.length) main.append(el("p", { class: "note", style: "margin-top:16px; font-size:14px; color:var(--muted)" },
    "The archive begins " + fmtDate(digests[digests.length - 1].date, U.long) + "."));
  const side = el("aside", { class: "col-side", "aria-label": "Friday M&A recaps" }, sectionHead("Friday M&A recaps"));
  if (!weekly.length) side.append(el("p", { class: "side-empty" }, "The first recap is published on a Friday."));
  for (const w of weekly) {
    const desc = el("span", { class: "desc" }, plural(w.deal_count, "deal") + ".");
    side.append(nav(`/?tab=weekly&week=${w.week}`, [
      el("span", { class: "title" }, "Week of " + fmtDate(w.start, U.mdLong)), desc,
      el("span", { class: "meta-line" }, "Published " + fmtDate(w.end, U.wdayShort) + ", " + fmtDate(w.end, U.md)),
    ], "recap-link"));
    optional(`weekly/${w.week}.json`, null).then((r) => {
      if (r && r.total_disclosed_value_usd) desc.textContent = `${plural(r.deals.length, "deal")}, ${fmtAum(r.total_disclosed_value_usd)} in disclosed prices.`;
    });
  }
  put(box, el("div", { class: "cols" }, main, side));
}
let weeklySort = { key: "date", dir: -1 };
async function renderWeekly(s) {
  const box = $("#view-weekly");
  put(box, ...skeletons(4));
  let w;
  try {
    const idx = await data("weekly/index.json");
    const week = s.week || (idx.weekly[0] && idx.weekly[0].week);
    if (!week) { put(box, nav("/?tab=archive", "← Archive", "back"), el("p", { class: "state" }, "No weekly recap yet. Recaps are published on Fridays.")); return; }
    w = await data(`weekly/${week}.json`);
  } catch (e) { put(box, errorState(e, () => renderWeekly(s))); return; }
  const top = (w.top_acquirers || []).map((a) => (a.slug ? nav(`/firm/${encodeURIComponent(a.slug)}`, `${a.name} (${a.deals})`) : `${a.name} (${a.deals})`));
  put(box, el("div", { class: "col-main", style: "max-width:none" },
    nav("/?tab=archive", "← Archive", "back"),
    el("div", { class: "kicker", style: "margin-top:10px" }, "Friday M&A recap"),
    el("h1", { class: "page-title", style: "margin-top:4px" }, "Week of " + fmtDate(w.start, U.mdLong)),
    el("div", { class: "meta-line", style: "margin-top:6px" }, fmtDate(w.start, U.long) + " – " + fmtDate(w.end, U.long)),
    w.ai && w.paragraph ? el("p", { class: "opener", style: "max-width:780px" }, w.paragraph) : null,
    el("dl", { class: "facts stats" },
      el("div", {}, el("dt", {}, "Deals"), el("dd", { class: "big" }, String(w.deals.length)),
        el("dd", {}, (w.industry_counts || []).slice(0, 3).map((x) => `${IND_SHORT[x.industry] || x.industry} ${x.deals}`).join(" · ") || null)),
      w.total_disclosed_value_usd != null || w.disclosed_value_deals != null
        ? el("div", {}, el("dt", {}, "Disclosed prices"), el("dd", { class: "big" }, fmtAum(w.total_disclosed_value_usd)),
          el("dd", {}, `from ${plural(w.disclosed_value_deals || 0, "deal")} with a stated price`)) : null,
      el("div", {}, el("dt", {}, "RIA target AUM"), el("dd", { class: "big" }, fmtAum(w.total_disclosed_aum_usd)),
        el("dd", {}, `from ${plural(w.disclosed_aum_deals, "deal")} with disclosed AUM`)),
      el("div", {}, el("dt", {}, "Most active"), el("dd", { class: "big", style: "font-size:20px; padding-top:6px" },
        top.length ? top.map((t, i) => [t, i < top.length - 1 ? ", " : ""]) : "—"))),
    w.deals.length ? dealsBlock(w.deals, SEC_DATE, weeklySort, (key, dir) => { weeklySort = { key, dir }; renderWeekly(s); })
      : el("p", { class: "state" }, "No deals were tracked this week.")));
}

/* ---------- Sources ---------- */
async function renderSources() {
  const box = $("#view-sources");
  put(box, ...skeletons(6));
  let d;
  try { d = await data("sources.json"); } catch (e) { put(box, errorState(e, renderSources)); return; }
  const last = META && META.last_refresh ? `${F.long.format(new Date(META.last_refresh))} at ${fmtTime(META.last_refresh)} PT` : "not yet run";
  put(box, el("div", { style: "max-width:1040px" },
    el("h1", { class: "page-title" }, "Sources"),
    el("p", { class: "prose", style: "margin:10px 0 18px" }, `Status from the last run, ${last}. Only headlines that announce a deal are kept; everything else is dropped. `
      + "Only the headline, link, date and a short description are stored; gated outlets contribute headlines only."),
    el("div", { class: "src-list" }, (d.sources || []).map((r) => el("div", { class: "src-row" },
      r.homepage ? ext(r.homepage, r.name, "name") : el("span", { class: "name" }, r.name),
      el("span", { class: "method" }, r.method || "—"),
      el("span", { class: "items" }, plural(r.items_last_run || 0, "item") + (r.enabled && r.ok && r.dropped_last_run ? ` · ${r.dropped_last_run} not deals` : "")),
      !r.enabled ? el("span", { class: "off" }, "Disabled")
        : r.ok ? el("span", { class: "ok" }, "OK")
          : el("span", { class: "fail" }, r.reason || "Failed"))))));
}

/* ---------- watchlist drawer ---------- */
let lastFocus = null;
function openDrawer() {
  lastFocus = document.activeElement;
  renderWatchlist();
  $("#watch-msg").textContent = "";
  $("#drawer-backdrop").hidden = false;
  $("#drawer").hidden = false;
  document.body.style.overflow = "hidden";
  $("#watch-name").focus();
}
function closeDrawer() {
  $("#drawer").hidden = true;
  $("#drawer-backdrop").hidden = true;
  document.body.style.overflow = "";
  if (lastFocus && lastFocus.focus) lastFocus.focus();
}
function renderWatchlist() {
  const ul = $("#watchlist");
  put(ul, ...(WATCH.length ? WATCH.map((f) => el("li", {},
    el("span", { style: "min-width:0" }, el("span", { class: "w-name" }, f.name),
      f.aliases.length ? el("span", { class: "w-alias" }, "Also: " + f.aliases.join(", ")) : null),
    el("button", { class: "textbtn", type: "button", "aria-label": "Remove " + f.name,
      onclick: () => setWatch(WATCH.filter((x) => x !== f), `Removed ${f.name}.`) }, "Remove")))
    : [el("li", {}, el("span", { class: "empty" }, "No firms yet. Add one below."))]));
}
function setWatch(list, msg) {
  WATCH = Watch.clean(list);
  const saved = Watch.save(WATCH);
  compileWatch();
  $("#watch-open").textContent = `Watchlist (${WATCH.length})`;
  if (!$("#drawer").hidden) renderWatchlist();
  $("#watch-msg").textContent = saved ? (msg || "") : "This browser blocked storage, so the watchlist won't be kept.";
  route();
}
function trapFocus(e) {
  if ($("#drawer").hidden) return;
  if (e.key === "Escape") { e.preventDefault(); closeDrawer(); return; }
  if (e.key !== "Tab") return;
  const vis = [...$("#drawer").querySelectorAll("button, input, a[href], select")].filter((x) => !x.disabled && x.getClientRects().length);
  if (!vis.length) return;
  const first = vis[0], last = vis[vis.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/* ---------- theme ---------- */
function themeLabel() { $("#theme-toggle").textContent = document.documentElement.dataset.theme === "dark" ? "Light mode" : "Dark mode"; }
function initTheme() {
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* private mode */ }
    themeLabel();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    let saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (err) {}
    if (!saved) { document.documentElement.dataset.theme = e.matches ? "dark" : "light"; themeLabel(); }
  });
  themeLabel();
}

/* ---------- wiring ---------- */
function init() {
  initTheme();
  let t = null;
  $("#q").addEventListener("input", (e) => { clearTimeout(t); const v = e.target.value.trim(); t = setTimeout(() => { feedShown = PAGE; writeState({ tab: "feed", q: v }, true); }, 200); });
  $("#filters").addEventListener("submit", (e) => { e.preventDefault(); writeState({ tab: "feed", q: $("#q").value.trim() }); });
  $("#source").addEventListener("change", (e) => { feedShown = PAGE; writeState({ tab: "feed", source: e.target.value }); });
  $("#region").addEventListener("change", (e) => { feedShown = PAGE; writeState({ tab: "feed", region: e.target.value }); });
  $("#when").addEventListener("change", (e) => { feedShown = PAGE; writeState({ tab: "feed", when: e.target.value }); });
  $("#from").addEventListener("change", (e) => writeState({ tab: "feed", when: "range", from: e.target.value }));
  $("#to").addEventListener("change", (e) => writeState({ tab: "feed", when: "range", to: e.target.value }));
  $("#watch").addEventListener("change", (e) => { feedShown = PAGE; writeState({ tab: "feed", watch: e.target.checked }); });
  $("#ind-bar").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-ind]");
    if (!b) return;
    const st = readState(), ind = b.dataset.ind, cur = st.industry;
    feedShown = PAGE;
    writeState({ industry: !ind ? [] : cur.includes(ind) ? cur.filter((c) => c !== ind) : [...cur, ind] });
  });
  $("#more").addEventListener("click", () => { feedShown += PAGE; renderFeed(readState(), true); });
  $("#watch-open").addEventListener("click", openDrawer);
  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-backdrop").addEventListener("click", closeDrawer);
  $("#watch-add").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("#watch-name").value.trim();
    const aliases = $("#watch-aliases").value.split(",").map((a) => a.trim()).filter(Boolean);
    const msg = $("#watch-msg");
    if (!name) { msg.textContent = "Enter a firm name."; return; }
    if (name.replace(/\s/g, "").length < 3 && !aliases.some((a) => a.replace(/\s/g, "").length >= 3)) { msg.textContent = "Use at least three characters; shorter names are never matched."; return; }
    if (WATCH.some((f) => f.name.toLowerCase() === name.toLowerCase())) { msg.textContent = `${name} is already on the list.`; return; }
    $("#watch-name").value = ""; $("#watch-aliases").value = "";
    setWatch([...WATCH, { name, aliases }], `Added ${name}.`);
    $("#watch-name").focus();
  });
  $("#watch-export").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify({ version: 1, firms: WATCH }, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob), download: "fiduciary-wire-watchlist.json" });
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
      setWatch(list, `Imported ${plural(list.length, "firm")}.`);
    } catch (err) { $("#watch-msg").textContent = "Import failed: " + err.message + "."; }
  });
  document.addEventListener("keydown", trapFocus);
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-nav]");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    feedShown = PAGE;
    go(a.getAttribute("href"));
    window.scrollTo(0, 0);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && $("#drawer").hidden && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault();
      if (readState().tab !== "feed") writeState({ tab: "feed" });
      $("#q").focus();
    }
  });
  window.addEventListener("popstate", () => { prevUrl = null; route(); });
  route();
}
init();
