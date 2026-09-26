/* Wealth Wire front end — vanilla JS, no build step. The URL query string is the single source of
   truth for which tab is shown and every filter/search value. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const CAT_CLASS = {
  "M&A": "cat-mna", "People Moves": "cat-people", "Regulation": "cat-reg", "Wealthtech": "cat-tech",
  "Products & Funds": "cat-prod", "Markets": "cat-mkt", "Other": "cat-other",
};
const TABS = ["feed", "mna", "digest", "sources"];
let META = null;
let feedOffset = 0;
let feedToken = 0;

/* ---------- helpers ---------- */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}
function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : null; }
function extLink(href, text, cls) {
  return el("a", { href: safeUrl(href), class: cls, target: "_blank", rel: "noopener noreferrer" }, text);
}
function catChip(cat) { return el("span", { class: "cat " + (CAT_CLASS[cat] || "cat-other") }, cat || "Other"); }

function fmtAum(v) {
  if (!v) return "";
  const units = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
  for (const [n, s] of units) {
    if (v >= n) {
      const x = v / n;
      return "$" + (x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1).replace(/\.0$/, "") : x.toFixed(2).replace(/0$/, "").replace(/\.0$/, "")) + s;
    }
  }
  return "$" + Math.round(v);
}
const dFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const tFmt = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const fullFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
function fmtTime(iso, withDay = true) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay || !withDay ? tFmt.format(d) : dFmt.format(d) + " " + tFmt.format(d);
}
function fmtDay(iso) { return iso ? dFmt.format(new Date(iso)) : ""; }
function relAgo(iso) {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  if (mins < 48 * 60) return Math.round(mins / 60) + "h ago";
  return Math.round(mins / 1440) + "d ago";
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, { headers: { "Accept": "application/json", ...(opts.body ? { "Content-Type": "application/json" } : {}) }, ...opts });
  } catch (e) {
    throw new Error("Can't reach the Wealth Wire server. Is it running?");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  if (!res.ok) throw new Error((data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `HTTP ${res.status}`);
  return data;
}

function stateBox(kind, title, body, action) {
  return el("div", { class: "state " + (kind || ""), role: kind === "error" ? "alert" : null },
    el("h3", { text: title }), body ? el("p", { text: body }) : null, action || null);
}
function skeletons(n) {
  const frag = document.createDocumentFragment();
  const tpl = $("#tpl-skeleton");
  for (let i = 0; i < n; i++) frag.append(tpl.content.cloneNode(true));
  return frag;
}

/* ---------- URL state ---------- */
function readState() {
  const p = new URLSearchParams(location.search);
  const tab = TABS.includes(p.get("tab")) ? p.get("tab") : "feed";
  return {
    tab,
    q: p.get("q") || "",
    source: p.get("source") || "",
    category: (p.get("category") || "").split(",").filter(Boolean),
    from: p.get("from") || "",
    to: p.get("to") || "",
    watch: p.get("watch") === "1",
    conf: p.get("conf") || "",
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
    if (s.from) p.set("from", s.from);
    if (s.to) p.set("to", s.to);
    if (s.watch) p.set("watch", "1");
  }
  if (s.tab === "mna" && s.conf) p.set("conf", s.conf);
  const url = location.pathname + (p.toString() ? "?" + p.toString() : "");
  if (url !== location.pathname + location.search) {
    history[replace ? "replaceState" : "pushState"](null, "", url);
  }
  route();
}

/* ---------- theme ---------- */
function initTheme() {
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("ww-theme", next); } catch (e) { /* private mode */ }
  });
  // Follow system changes only while the user hasn't chosen explicitly.
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    let saved = null;
    try { saved = localStorage.getItem("ww-theme"); } catch (err) {}
    if (!saved) document.documentElement.dataset.theme = e.matches ? "dark" : "light";
  });
}

/* ---------- meta / header ---------- */
async function loadMeta() {
  try {
    META = await api("/api/meta");
  } catch (e) {
    META = { categories: Object.keys(CAT_CLASS), sources: [], last_ingest: null, demo: false, items: 0, error: e.message };
  }
  $("#demo-chip").hidden = !META.demo;
  const ok = META.sources.filter((s) => s.ok).length;
  $("#ingest-status").textContent = META.error ? "server unreachable"
    : `updated ${relAgo(META.last_ingest)} · ${ok}/${META.sources.length} sources · ${META.items} items`;
  if (META.last_ingest) $("#ingest-status").title = "Last ingestion: " + fullFmt.format(new Date(META.last_ingest));

  const sel = $("#source");
  sel.replaceChildren(el("option", { value: "" }, "All sources"),
    ...META.sources.map((s) => el("option", { value: s.name }, s.name + (s.ok ? "" : " (failed)"))));
  const chips = $("#cat-chips");
  chips.replaceChildren(...META.categories.map((c) =>
    el("button", { type: "button", class: CAT_CLASS[c] || "cat-other", "data-cat": c, "aria-pressed": "false" }, c)));
}

/* ---------- routing ---------- */
function route() {
  const s = readState();
  for (const t of TABS) {
    $("#view-" + t).hidden = t !== s.tab;
    const a = $(`.tabs a[data-tab="${t}"]`);
    a.setAttribute("aria-selected", String(t === s.tab));
  }
  document.title = { feed: "Wealth Wire", mna: "M&A · Wealth Wire", digest: "Digest · Wealth Wire", sources: "Sources · Wealth Wire" }[s.tab];
  if (s.tab === "feed") renderFeed(s);
  else if (s.tab === "mna") renderMna(s);
  else if (s.tab === "digest") renderDigest();
  else renderSources();
}

/* ---------- feed ---------- */
function syncFilterInputs(s) {
  if (document.activeElement !== $("#q")) $("#q").value = s.q;
  $("#source").value = s.source;
  $("#from").value = s.from;
  $("#to").value = s.to;
  $("#watch").checked = s.watch;
  for (const b of $("#cat-chips").children) b.setAttribute("aria-pressed", String(s.category.includes(b.dataset.cat)));
}

function feedParams(s, offset) {
  const p = new URLSearchParams();
  if (s.q) p.set("q", s.q);
  if (s.source) p.set("source", s.source);
  if (s.category.length) p.set("category", s.category.join(","));
  // date inputs are local calendar days → send UTC instants
  if (s.from) p.set("from", new Date(s.from + "T00:00:00").toISOString());
  if (s.to) { const d = new Date(s.to + "T00:00:00"); d.setDate(d.getDate() + 1); p.set("to", d.toISOString()); }
  if (s.watch) p.set("watch", "1");
  p.set("offset", offset);
  return p;
}

function highlight(text, q) {
  const terms = (q || "").split(/\s+/).map((t) => t.replace(/[^\w$.&'-]/g, "")).filter((t) => t.length > 1);
  if (!terms.length) return [text];
  const re = new RegExp("(" + terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
  return text.split(re).map((part, i) => (i % 2 ? el("mark", {}, part) : part));
}

function card(c, s) {
  const watch = (c.watchlist_hits || []).length > 0;
  const multi = c.outlet_count > 1;
  const srcs = c.sources.map((x) =>
    el("a", { class: "src", href: safeUrl(x.url), target: "_blank", rel: "noopener noreferrer", title: `${x.name} · ${fullFmt.format(new Date(x.published_at))}` },
      x.name, multi ? el("span", { class: "src-time" }, fmtTime(x.published_at)) : null));
  const firms = (c.firms || []).slice(0, 4).map((f) => el("span", { class: "firm" }, f));
  return el("article", { class: "card" + (watch ? " is-watch" : ""), "data-cluster": c.id },
    el("div", { class: "card-meta" },
      el("time", { class: "card-time", datetime: c.last_published, title: "First reported " + fullFmt.format(new Date(c.first_published)) }, fmtTime(c.first_published)),
      catChip(c.category),
      watch ? el("span", { class: "chip chip-watch", title: "Watchlist: " + c.watchlist_hits.join(", ") }, "★ " + c.watchlist_hits.join(", ")) : null,
      el("span", { class: "card-outlets" + (multi ? " multi" : "") }, multi ? `${c.outlet_count} outlets` : "")),
    el("div", { class: "card-main" },
      el("div", { class: "card-body" },
        el("h3", { class: "card-title" }, el("a", { href: safeUrl(c.url), target: "_blank", rel: "noopener noreferrer" }, ...highlight(c.headline, s.q))),
        c.description ? el("p", { class: "card-desc" }, ...highlight(c.description, s.q)) : null,
        el("div", { class: "card-foot" }, ...srcs, firms.length ? el("span", { class: "foot-sep" }) : null, ...firms)),
      c.aum_usd ? el("div", { class: "aum", title: "Assets under management mentioned in the story" }, fmtAum(c.aum_usd), el("small", {}, "AUM")) : null));
}

function describeFilters(s) {
  const bits = [];
  if (s.q) bits.push(`“${s.q}”`);
  if (s.source) bits.push(s.source);
  if (s.category.length) bits.push(s.category.join(" + "));
  if (s.from || s.to) bits.push(`${s.from || "…"} → ${s.to || "…"}`);
  if (s.watch) bits.push("watchlist");
  return bits.join(" · ");
}

async function renderFeed(s, append = false) {
  syncFilterInputs(s);
  const token = ++feedToken;
  const list = $("#feed-list");
  const errBox = $("#feed-error");
  if (!append) {
    feedOffset = 0;
    list.replaceChildren(skeletons(6));
    $("#pinned").hidden = true;
    $("#more").hidden = true;
    errBox.replaceChildren();
    $("#feed-summary").textContent = "Loading…";
  }
  let data;
  try {
    data = await api("/api/feed?" + feedParams(s, feedOffset));
  } catch (e) {
    if (token !== feedToken) return;
    list.replaceChildren();
    $("#feed-summary").textContent = "";
    errBox.replaceChildren(stateBox("error", "Couldn't load stories", e.message,
      el("button", { class: "btn", type: "button", onclick: () => renderFeed(readState()) }, "Retry")));
    return;
  }
  if (token !== feedToken) return;  // a newer request superseded this one

  if (!append) {
    list.replaceChildren();
    const pinned = data.pinned || [];
    $("#pinned").hidden = pinned.length === 0;
    $("#pinned-count").textContent = pinned.length ? String(pinned.length) : "";
    $("#pinned-list").replaceChildren(...pinned.map((c) => card(c, s)));
  }
  list.append(...data.clusters.map((c) => card(c, s)));
  feedOffset = data.offset + data.clusters.length;
  $("#more").hidden = feedOffset >= data.total;

  const filt = describeFilters(s);
  const total = data.total;
  const summary = $("#feed-summary");
  summary.replaceChildren(el("b", {}, String(total)), ` ${total === 1 ? "story" : "stories"}`,
    (data.pinned || []).length && !s.watch ? ` · ${data.pinned.length} pinned` : "",
    filt ? ` · ${filt}` : "");

  if (total === 0 && !(data.pinned || []).length) {
    const hasFilters = filt.length > 0;
    if (META && META.items === 0) {
      list.replaceChildren(); errBox.replaceChildren(stateBox("", "No stories yet",
        "Nothing has been ingested. Run `python -m wealthwire ingest` (or ./run.sh) and check the Sources tab for failures."));
    } else {
      errBox.replaceChildren(stateBox("", hasFilters ? "No stories match these filters" : "No stories",
        hasFilters ? "Try a broader search, another source or category, or a wider date range." : "",
        hasFilters ? el("button", { class: "btn", type: "button", onclick: clearFilters }, "Clear filters") : null));
    }
  }
}

function clearFilters() { writeState({ q: "", source: "", category: [], from: "", to: "", watch: false }); }

function initFilters() {
  let t = null;
  $("#q").addEventListener("input", (e) => {
    clearTimeout(t);
    const v = e.target.value.trim();
    t = setTimeout(() => writeState({ q: v }, true), 250);
  });
  $("#filters").addEventListener("submit", (e) => { e.preventDefault(); writeState({ q: $("#q").value.trim() }); });
  $("#source").addEventListener("change", (e) => writeState({ source: e.target.value }));
  $("#from").addEventListener("change", (e) => writeState({ from: e.target.value }));
  $("#to").addEventListener("change", (e) => writeState({ to: e.target.value }));
  $("#watch").addEventListener("change", (e) => writeState({ watch: e.target.checked }));
  $("#clear").addEventListener("click", clearFilters);
  $("#cat-chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-cat]");
    if (!b) return;
    const cur = readState().category;
    const cat = b.dataset.cat;
    writeState({ category: cur.includes(cat) ? cur.filter((c) => c !== cat) : [...cur, cat] });
  });
  $("#more").addEventListener("click", () => renderFeed(readState(), true));
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault();
      if (readState().tab !== "feed") writeState({ tab: "feed" });
      $("#q").focus();
    }
  });
}

/* ---------- sidebar: trending + watchlist ---------- */
async function renderTrending() {
  const box = $("#trending");
  try {
    const rows = await api("/api/trending");
    if (!rows.length) { box.replaceChildren(el("li", { class: "muted" }, "No firm mentions in the last 7 days.")); return; }
    const max = rows[0].stories;
    box.replaceChildren(...rows.map((r) => el("li", {},
      el("div", { style: "flex:1;min-width:0" },
        el("a", { href: "?q=" + encodeURIComponent(r.firm), "data-firm": r.firm, title: "Search for " + r.firm,
          onclick: (e) => { e.preventDefault(); writeState({ tab: "feed", q: r.firm }); } }, r.firm),
        el("span", { class: "bar", style: `width:${Math.max(8, Math.round(100 * r.stories / max))}%` })),
      el("span", { class: "n", title: `${r.stories} ${r.stories === 1 ? "story" : "stories"}` }, r.stories))));
  } catch (e) {
    box.replaceChildren(el("li", { class: "form-msg err" }, "Couldn't load trending firms: " + e.message));
  }
}

async function renderWatchlist() {
  const box = $("#watchlist");
  try {
    const data = await api("/api/watchlist");
    if (!data.firms.length) { box.replaceChildren(el("li", { class: "muted" }, "No firms yet — add one below.")); return; }
    box.replaceChildren(...data.firms.map((f) => el("li", {},
      el("span", { class: "w-name" }, f.name,
        f.aliases.length ? el("span", { class: "w-alias" }, "aka " + f.aliases.join(", ")) : null),
      el("span", { class: "w-count", title: "Stories in the last 7 days" }, f.recent || ""),
      el("button", { type: "button", "aria-label": "Remove " + f.name, title: "Remove " + f.name, onclick: () => removeWatch(f.name) }, "×"))));
  } catch (e) {
    box.replaceChildren(el("li", { class: "form-msg err" }, "Couldn't load watchlist: " + e.message));
  }
}

async function removeWatch(name) {
  const msg = $("#watch-msg");
  try {
    await api("/api/watchlist/" + encodeURIComponent(name), { method: "DELETE" });
    msg.className = "form-msg"; msg.textContent = `Removed ${name}.`;
    await renderWatchlist(); if (readState().tab === "feed") renderFeed(readState());
  } catch (e) { msg.className = "form-msg err"; msg.textContent = e.message; }
}

function initWatchForm() {
  $("#watch-add").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("#watch-msg");
    const name = $("#watch-name").value.trim();
    const aliases = $("#watch-aliases").value.split(",").map((a) => a.trim()).filter(Boolean);
    if (!name) return;
    try {
      await api("/api/watchlist", { method: "POST", body: JSON.stringify({ name, aliases }) });
      $("#watch-name").value = ""; $("#watch-aliases").value = "";
      msg.className = "form-msg"; msg.textContent = `Added ${name}.`;
      await renderWatchlist(); renderFeed(readState());
    } catch (err) { msg.className = "form-msg err"; msg.textContent = err.message; }
  });
}

/* ---------- M&A ---------- */
async function renderMna(s) {
  for (const a of document.querySelectorAll(".seg a")) a.setAttribute("aria-current", String(a.dataset.conf === s.conf));
  const wrap = $("#mna-wrap");
  const err = $("#mna-error");
  err.replaceChildren();
  wrap.replaceChildren(stateBox("", "Loading deals…"));
  let rows;
  try {
    rows = await api("/api/mna" + (s.conf ? "?confidence=" + encodeURIComponent(s.conf) : ""));
  } catch (e) {
    wrap.replaceChildren();
    err.replaceChildren(stateBox("error", "Couldn't load the M&A tracker", e.message,
      el("button", { class: "btn", type: "button", onclick: () => renderMna(readState()) }, "Retry")));
    return;
  }
  if (!rows.length) {
    wrap.replaceChildren(stateBox("", s.conf ? `No ${s.conf}-confidence deals` : "No deals yet",
      "Deals appear when ingested headlines are categorized as M&A."));
    return;
  }
  const blank = (v, why) => v ? v : el("span", { class: "blank", title: why }, "—");
  const body = rows.map((r) => {
    const isMerger = r.deal_type === "merger";
    return el("tr", { class: r.confidence === "low" ? "is-low" : "" },
      el("td", { class: "date", "data-label": "Date" }, fmtDay(r.deal_date)),
      el("td", { class: "party", "data-label": isMerger ? "Party A" : "Acquirer" }, el("div", {}, blank(r.acquirer, "could not be determined unambiguously"),
        el("span", { class: "headline" }, r.headline))),
      el("td", { class: "party", "data-label": isMerger ? "Party B" : "Target" }, blank(r.target, "could not be determined unambiguously")),
      el("td", { class: "num", "data-label": "Target AUM" }, r.target_aum_usd ? el("span", { class: "aum-cell" }, fmtAum(r.target_aum_usd)) : blank("", "not stated or ambiguous")),
      el("td", { "data-label": "Type" }, el("span", { class: "deal-type" }, r.deal_type || "—")),
      el("td", { "data-label": "Sources" }, el("div", { class: "srcs" }, ...r.sources.map((x) => extLink(x.url, x.name, "src")))),
      el("td", { "data-label": "Confidence" }, el("div", {},
        el("span", { class: "conf conf-" + r.confidence }, r.confidence === "low" ? "⚠ LOW" : "HIGH"),
        r.confidence === "low" && r.note ? el("span", { class: "conf-note" }, r.note) : null)));
  });
  wrap.replaceChildren(el("table", {},
    el("thead", {}, el("tr", {}, ...["Date", "Acquirer", "Target", "Target AUM", "Type", "Sources", "Confidence"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...body)));
}

/* ---------- Digest ---------- */
async function renderDigest() {
  const box = $("#digest");
  box.replaceChildren(stateBox("", "Loading digest…"));
  let d;
  try { d = await api("/api/digest"); } catch (e) {
    box.replaceChildren(stateBox("error", "Couldn't load the digest", e.message,
      el("button", { class: "btn", type: "button", onclick: renderDigest }, "Retry")));
    return;
  }
  if (d.date) {
    const body = el("div", { class: "digest-body" });
    body.innerHTML = d.html;  // sanitized server-side with bleach (allow-listed tags/attrs only)
    for (const a of body.querySelectorAll("a")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
    box.replaceChildren(el("article", { class: "digest" },
      el("div", { class: "digest-head digest-head-slim" }, el("span", { class: "digest-label" }, "Morning digest"),
        el("span", { class: "digest-date" }, d.date), el("span", { class: "muted mono digest-file" }, d.filename)),
      body));
    return;
  }
  const top = d.top || [];
  box.replaceChildren(el("article", { class: "digest" },
    el("div", { class: "digest-head" }, el("h1", {}, "No digest written yet")),
    el("p", {}, "There is no ", el("code", {}, "digests/YYYY-MM-DD.md"), " yet. Run ", el("code", {}, "/digest"),
      " in Claude Code to write today's. Meanwhile, here are the top stories from ", el("code", {}, "new_stories.json"), "."),
    top.length ? el("ol", { class: "fallback-list" }, ...top.map((c) => el("li", {},
      el("div", { class: "t" }, extLink(c.sources[0] && c.sources[0].url, c.headline)),
      el("div", {}, catChip(c.category), " ", el("span", { class: "mono muted", style: "font-size:12px" },
        `${c.outlet_count} outlet${c.outlet_count > 1 ? "s" : ""}`), c.aum_usd ? el("span", { class: "aum-cell", style: "margin-left:8px" }, fmtAum(c.aum_usd)) : null,
        (c.watchlist_hits || []).length ? el("span", { class: "chip chip-watch", style: "margin-left:8px" }, "★ " + c.watchlist_hits.join(", ")) : null),
      el("div", { class: "srcs" }, ...c.sources.map((x) => extLink(x.url, x.name, "src")))))) :
      stateBox("", "No new stories", "new_stories.json is empty or missing — run an ingestion first.")));
}

/* ---------- Sources ---------- */
async function renderSources() {
  const wrap = $("#sources-wrap");
  try { await loadMeta(); } catch (e) { /* loadMeta handles its own errors */ }
  if (META.error) { wrap.replaceChildren(stateBox("error", "Couldn't load sources", META.error)); return; }
  wrap.replaceChildren(el("table", {},
    el("thead", {}, el("tr", {}, ...["Source", "Method", "URL used", "Items", "New", "Notes / failure reason"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...META.sources.map((s) => el("tr", { class: s.ok ? "" : "is-low" },
      el("td", { class: "party", "data-label": "Source" }, el("span", {}, el("span", { class: "ok-dot " + (s.ok ? "ok" : "fail") }), s.name)),
      el("td", { "data-label": "Method" }, s.method),
      el("td", { class: "url", "data-label": "URL used" }, s.url_used ? extLink(s.url_used, s.url_used) : "—"),
      el("td", { class: "num", "data-label": "Items" }, s.items_last_run),
      el("td", { class: "num", "data-label": "New" }, s.new_last_run),
      el("td", { class: "reason", "data-label": s.ok ? "Notes" : "Reason" }, s.reason || (s.ok ? null : "not run yet")))))));
}

/* ---------- boot ---------- */
async function boot() {
  initTheme();
  initFilters();
  initWatchForm();
  document.querySelector(".tabs").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-tab]");
    if (!a || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    writeState({ tab: a.dataset.tab });
  });
  document.querySelector(".seg").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-conf]");
    if (!a || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    writeState({ tab: "mna", conf: a.dataset.conf });
  });
  window.addEventListener("popstate", route);
  await loadMeta();
  route();
  renderTrending();
  renderWatchlist();
}
boot();
