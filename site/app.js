"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const app = $("#app");
const NS = "http://www.w3.org/2000/svg";
const PORTFOLIO_KEY = "tawzi.portfolio";
const EXAMPLE_HOLDINGS = [
  { code: "2222", shares: 1000 },
  { code: "1120", shares: 300 },
  { code: "7010", shares: 400 },
  { code: "2010", shares: 200 },
];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FREQUENCY = { 1: "Annual", 2: "Semi-annual", 4: "Quarterly", 12: "Monthly" };
const SORTS = {
  yield: { label: "Highest yield", key: c => c.yield, desc: true },
  ttm_dps: { label: "Biggest dividend (12 mo)", key: c => c.ttm_dps || null, desc: true },
  streak: { label: "Most years in a row", key: c => c.streak || null, desc: true },
  cagr_5y: { label: "Fastest growth (5 yr)", key: c => c.cagr_5y, desc: true },
  next_ex: { label: "Soonest ex-date", key: c => c.next_ex, desc: false },
  code: { label: "Company code", key: c => c.code, desc: false },
};

let data, byCode, asOf, portfolio;
let redraws = [];
let pendingCode = null;
const screener = { q: "", sort: "yield", quarterly: false, streak: false, upcoming: false };

/* ---------- formatting ---------- */

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const day = iso => new Date(`${iso}T00:00:00Z`);
const daysFrom = (a, b) => Math.round((b - a) / 86400000);
const num = (v, digits = 2) =>
  v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = v => (v == null ? "—" : `${v.toFixed(2)}%`);
const signed = v => (v > 0 ? `+${v}` : `${v}`);
const dateLabel = iso =>
  iso ? day(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—";
let hijriFormat = null;
try {
  hijriFormat = new Intl.DateTimeFormat("en-u-ca-islamic-umalqura", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
} catch { /* calendar unsupported: Hijri dates are simply left out */ }
const hijri = iso => (iso && hijriFormat ? hijriFormat.format(day(iso)) : "");
function compact(v) {
  for (const [size, unit] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (Math.abs(v) >= size) return `${+(v / size).toPrecision(3)}${unit}`;
  }
  return `${+v.toPrecision(3)}`;
}
const freqLabel = n => (n ? FREQUENCY[n] || `${n}× a year` : "—");
const sinceYear = c => (c.streak ? asOf.getUTCFullYear() - c.streak : null);
const symbol = c => `<span class="sym">${esc(c.code)}${c.name ? `<small>${esc(c.name)}</small>` : ""}</span>`;
const kindPill = kind => (kind ? `<span class="pill${/special/i.test(kind) ? " special" : ""}">${esc(kind)}</span>` : "");
const monthLabel = ym => `${MONTHS[+ym.slice(5, 7) - 1]} ${ym.slice(2, 4)}`;

function sinceText(c) {
  const since = sinceYear(c);
  if (!since) return "No unbroken run";
  return since <= c.first_year ? `Every year since at least ${since}` : `Every year since ${since}`;
}

/* ---------- storage (per-browser convenience only) ---------- */

function loadHoldings() {
  try {
    const saved = localStorage.getItem(PORTFOLIO_KEY);
    if (saved) return { holdings: JSON.parse(saved).filter(h => byCode[h.code]), example: false };
  } catch { /* storage blocked: fall back to the example */ }
  return { holdings: EXAMPLE_HOLDINGS.filter(h => byCode[h.code]).map(h => ({ ...h })), example: true };
}

function saveHoldings() {
  portfolio.example = false;
  try {
    localStorage.setItem(PORTFOLIO_KEY, JSON.stringify(portfolio.holdings));
  } catch { /* not persisted, still works for this visit */ }
}

/* ---------- routing ---------- */

function route() {
  const token = location.hash.slice(1);
  redraws = [];
  let tab = "home";
  if (/^s\d+$/.test(token) && byCode[token.slice(1)]) {
    tab = "screener";
    renderSymbol(byCode[token.slice(1)]);
  } else if (token === "screener") {
    tab = "screener";
    renderScreener();
  } else if (token === "portfolio") {
    tab = "portfolio";
    renderPortfolio();
  } else {
    renderHome();
  }
  document.querySelectorAll("[data-tab]").forEach(a => {
    if (a.dataset.tab === tab) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
}

function asOfNote() {
  return data.source === "archive"
    ? `Archived data as of ${dateLabel(data.as_of)}. The daily update replaces it with live prices and dividends.`
    : `Updated ${dateLabel(data.as_of)} after market close.`;
}

/* ---------- Today ---------- */

function upcomingEvents() {
  const events = [];
  for (const c of data.companies) {
    for (const d of c.dividends) {
      if (day(d.ex) > asOf) events.push({ c, d, when: d.ex, type: "ex" });
      else if (d.pay && day(d.pay) >= asOf) events.push({ c, d, when: d.pay, type: "pay" });
    }
    if (c.next_ex && !c.dividends.some(d => d.ex === c.next_ex)) {
      events.push({ c, d: { ex: c.next_ex, pay: c.next_pay, amount: null }, when: c.next_ex, type: "ex" });
    }
  }
  return events.sort((a, b) => a.when.localeCompare(b.when));
}

function eventItem({ c, d, when, type }) {
  const n = daysFrom(asOf, day(when));
  const rel = n === 0 ? "today" : `in ${n} day${n === 1 ? "" : "s"}`;
  const what = type === "ex" ? `Ex-dividend ${rel}` : `Paid ${rel}`;
  const paid = type === "ex" && d.pay ? ` · paid ${dateLabel(d.pay)}` : "";
  return `<li><a class="event" href="#s${esc(c.code)}">
    <div class="datechip"><b>${day(when).getUTCDate()}</b><span>${MONTHS[day(when).getUTCMonth()]}</span></div>
    <div>
      <div class="event-name">${symbol(c)}</div>
      <div class="event-meta">${what}${paid} ${kindPill(d.kind)}</div>
      <div class="event-hijri">${esc(hijri(when))}</div>
    </div>
    <div class="event-amount">${d.amount != null ? `<b>${num(d.amount, 3)}</b><span>SAR a share</span>` : `<span>Amount not announced</span>`}</div>
  </a></li>`;
}

function rankList(items, value, sub) {
  if (!items.length) return `<p class="muted">Nothing to show yet.</p>`;
  return `<ol class="rank">${items
    .map(c => `<li><a href="#s${esc(c.code)}">${symbol(c)}<span class="val">${value(c)}</span><span class="sub">${sub(c)}</span></a></li>`)
    .join("")}</ol>`;
}

function renderHome() {
  const events = upcomingEvents().slice(0, 12);
  const reliable = data.companies
    .filter(c => c.streak > 0)
    .sort((a, b) => b.streak - a.streak || (b.frequency || 0) - (a.frequency || 0) || (b.cagr_5y ?? -999) - (a.cagr_5y ?? -999))
    .slice(0, 8);
  const growers = data.companies
    .filter(c => c.cagr_5y != null && c.streak >= 5)
    .sort((a, b) => b.cagr_5y - a.cagr_5y)
    .slice(0, 8);
  const yields = data.companies.filter(c => c.yield != null).sort((a, b) => b.yield - a.yield).slice(0, 8);

  app.innerHTML = `
    <div class="page-head">
      <h1>Dividends coming up</h1>
      <p class="lede">Ex-dividend dates and payouts across the Saudi market. Own the shares before the ex-dividend date to receive the payout.</p>
      <span class="asof">${esc(asOfNote())}</span>
    </div>
    <section class="section">
      ${events.length
        ? `<ul class="events">${events.map(eventItem).join("")}</ul>`
        : `<p class="muted">No announced dividends after ${dateLabel(data.as_of)}.</p>`}
    </section>
    <div class="cols">
      <section class="section card">
        <div class="section-head"><h2>Paid every year</h2><a href="#screener" data-sort="streak">Screener</a></div>
        ${rankList(reliable, c => freqLabel(c.frequency), sinceText)}
      </section>
      <section class="section card">
        <div class="section-head"><h2>Fastest-growing dividends</h2><a href="#screener" data-sort="cagr_5y">Screener</a></div>
        ${rankList(growers, c => `${signed(c.cagr_5y)}% a year`, c => `Over 5 years · ${num(c.ttm_dps, 3)} SAR in the last 12 months`)}
      </section>
      ${yields.length >= 5 ? `
      <section class="section card">
        <div class="section-head"><h2>Highest yield</h2><a href="#screener" data-sort="yield">Screener</a></div>
        ${rankList(yields, c => pct(c.yield), c => `${num(c.ttm_dps, 3)} SAR on a ${num(c.price)} SAR share`)}
      </section>` : ""}
    </div>`;
  app.querySelectorAll("[data-sort]").forEach(a => a.addEventListener("click", () => { screener.sort = a.dataset.sort; }));
}

/* ---------- Screener ---------- */

function renderScreener() {
  const chip = (id, text) => `<button type="button" class="chip" id="f-${id}" aria-pressed="${screener[id]}">${text}</button>`;
  app.innerHTML = `
    <div class="page-head">
      <h1>Screener</h1>
      <p class="lede">Every company in the dataset. Select a row for its full dividend history.</p>
    </div>
    <section class="section">
      <div class="controls">
        <input id="q" class="field search" type="search" placeholder="Search code or name" aria-label="Search code or name" value="${esc(screener.q)}">
        <select id="sort" class="field" aria-label="Sort by">
          ${Object.entries(SORTS).map(([k, s]) => `<option value="${k}"${k === screener.sort ? " selected" : ""}>${s.label}</option>`).join("")}
        </select>
        ${chip("quarterly", "Pays quarterly")}
        ${chip("streak", "5+ years in a row")}
        ${chip("upcoming", "Dividend coming up")}
      </div>
      <span class="count" id="count"></span>
      <div class="card flush table-wrap">
        <table>
          <thead><tr>
            <th>Company</th><th class="num">Yield</th><th class="num">Last 12 mo (SAR)</th><th>Pays</th>
            <th class="num">Years in a row</th><th class="num">5-yr growth</th><th>Next ex-date</th>
          </tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
      <span class="asof">${esc(asOfNote())}</span>
    </section>`;

  $("#q").addEventListener("input", e => { screener.q = e.target.value; drawRows(); });
  $("#sort").addEventListener("change", e => { screener.sort = e.target.value; drawRows(); });
  for (const id of ["quarterly", "streak", "upcoming"]) {
    $(`#f-${id}`).addEventListener("click", e => {
      screener[id] = !screener[id];
      e.currentTarget.setAttribute("aria-pressed", screener[id]);
      drawRows();
    });
  }
  const rows = $("#rows");
  const open = tr => tr && (location.hash = `s${tr.dataset.code}`);
  rows.addEventListener("click", e => open(e.target.closest("tr")));
  rows.addEventListener("keydown", e => { if (e.key === "Enter") open(e.target.closest("tr")); });
  drawRows();
}

function drawRows() {
  const q = screener.q.trim().toLowerCase();
  const { key, desc } = SORTS[screener.sort];
  const list = data.companies
    .filter(c => !q || c.code.includes(q) || (c.name || "").toLowerCase().includes(q))
    .filter(c => !screener.quarterly || c.frequency >= 4)
    .filter(c => !screener.streak || c.streak >= 5)
    .filter(c => !screener.upcoming || c.next_ex)
    .sort((a, b) => {
      const x = key(a), y = key(b);
      if (x == null || y == null) return (x == null) - (y == null) || a.code.localeCompare(b.code);
      const order = typeof x === "string" ? x.localeCompare(y) : x - y;
      return desc ? -order : order;
    });
  $("#count").textContent = `${list.length} of ${data.companies.length} companies`;
  $("#rows").innerHTML = list.length
    ? list.map(c => `<tr class="link" tabindex="0" data-code="${esc(c.code)}">
        <td>${symbol(c)}</td>
        <td class="num">${pct(c.yield)}</td>
        <td class="num">${c.ttm_dps ? num(c.ttm_dps, 3) : "—"}</td>
        <td>${freqLabel(c.frequency)}</td>
        <td class="num">${c.streak || "—"}</td>
        <td class="num ${c.cagr_5y > 0 ? "up" : c.cagr_5y < 0 ? "down" : ""}">${c.cagr_5y != null ? `${signed(c.cagr_5y)}%` : "—"}</td>
        <td>${c.next_ex ? dateLabel(c.next_ex) : `<span class="muted">—</span>`}</td>
      </tr>`).join("")
    : `<tr><td colspan="7" class="muted">No companies match. Clear a filter or the search.</td></tr>`;
}

/* ---------- Symbol ---------- */

function tile(label, value, note) {
  return `<div class="tile"><span class="tile-label">${label}</span><span class="tile-value">${value}</span><span class="tile-note">${note || "&nbsp;"}</span></div>`;
}

function chartCard(title, note, id) {
  return `<div class="card chart-card"><h3>${title}</h3><p>${note}</p><div class="chart" id="${id}"></div></div>`;
}

function renderSymbol(c) {
  const dps = c.annual.filter(r => r.dps > 0).slice(-10);
  const yields = c.annual.filter(r => r.yield != null).slice(-10);
  const fin = c.annual.filter(r => r.revenue != null || r.net_income != null);
  const margins = fin.filter(r => r.margin != null);
  const perYear = {};
  for (const d of c.dividends) perYear[d.ex.slice(0, 4)] = (perYear[d.ex.slice(0, 4)] || 0) + 1;
  const yearAgo = new Date(asOf - 365 * 86400000);
  const recent = c.dividends.filter(d => day(d.ex) > yearAgo && day(d.ex) <= asOf).length;
  const sourceNote = c.source === "archive" && data.source !== "archive"
    ? "Live data was unavailable for this company today, so this page shows archived data."
    : asOfNote();

  app.innerHTML = `
    <a class="back" href="#screener">← Screener</a>
    <div class="sym-head">
      <h1>${esc(c.code)}<small>${esc(c.name || "Company name arrives with the live update")}</small></h1>
      <div class="price">${c.price != null
        ? `<b>${num(c.price)}</b> SAR<span>Close on ${dateLabel(c.price_date)}</span>`
        : `<span>No recent price in this data</span>`}</div>
    </div>
    ${c.next_ex ? `<div class="notice"><span>Next ex-dividend date <b>${dateLabel(c.next_ex)}</b>${hijri(c.next_ex) ? ` (${esc(hijri(c.next_ex))})` : ""}. Own the shares by the trading day before.</span></div>` : ""}
    <div class="tiles">
      ${tile("Dividend yield", pct(c.yield), c.yield != null ? "Last 12 months ÷ share price" : "Needs a current share price")}
      ${tile("Dividends, last 12 months", c.ttm_dps ? `${num(c.ttm_dps, 3)} <small>SAR</small>` : "None", c.ttm_dps ? `${recent} payment${recent === 1 ? "" : "s"}` : "")}
      ${tile("Paid every year since", sinceYear(c) ?? "—", c.streak ? (sinceYear(c) <= c.first_year ? "Earliest year in this data" : `${c.streak} year${c.streak === 1 ? "" : "s"} in a row`) : "No unbroken run")}
      ${tile("Payments per year", freqLabel(c.frequency), c.cagr_5y != null ? `5-yr growth ${signed(c.cagr_5y)}% a year` : "")}
    </div>
    <div class="actions">
      <button type="button" class="btn" id="add">Add to portfolio</button>
      ${(c.charts || []).map(k => `<a class="btn ghost" href="charts/${esc(c.code)}/${k}.png" target="_blank" rel="noopener">${k === "dividends" ? "Dividend" : "Performance"} chart image</a>`).join("")}
    </div>
    <div class="charts">
      ${dps.length ? chartCard("Dividends per share", "SAR, grouped by the year of the ex-dividend date", "c-dps") : ""}
      ${yields.length >= 2 ? chartCard("Dividend yield", "The year's dividends ÷ year-end share price", "c-yield") : ""}
      ${fin.length ? chartCard("Revenue and net income", "SAR, by fiscal year", "c-fin") : ""}
      ${margins.length >= 2 ? chartCard("Net margin", "Net income ÷ revenue", "c-margin") : ""}
      ${c.prices.length >= 2 ? chartCard("Share price", "Monthly close, SAR", "c-price") : ""}
    </div>
    <section class="section">
      <div class="section-head"><h2>Dividend history</h2><span class="count">${c.dividends.length} payment${c.dividends.length === 1 ? "" : "s"}</span></div>
      ${c.dividends.length ? `
      <div class="card flush table-wrap">
        <table>
          <thead><tr><th>Ex-dividend date</th><th>Record date</th><th>Paid</th><th class="num">Amount (SAR)</th><th>Type</th></tr></thead>
          <tbody>${c.dividends.map(d => `<tr>
            <td>${dateLabel(d.ex)}<br><span class="muted">${esc(hijri(d.ex))}</span></td>
            <td>${dateLabel(d.record)}</td>
            <td>${dateLabel(d.pay)}</td>
            <td class="num">${num(d.amount, 3)}</td>
            <td>${kindPill(d.kind) || `<span class="muted">—</span>`}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>` : `<p class="muted">No dividends recorded for ${esc(c.code)} in this data.</p>`}
      <span class="asof">${esc(sourceNote)}</span>
    </section>`;

  $("#add").addEventListener("click", () => { pendingCode = c.code; location.hash = "portfolio"; });
  if (dps.length) {
    columnChart($("#c-dps"), {
      categories: dps.map(r => r.year),
      series: [{ name: "Dividends per share", values: dps.map(r => r.dps), cls: "s1" }],
      format: v => `${num(v, 3)} SAR`,
      tickFormat: v => `${+v.toFixed(3)}`,
      detail: i => `${perYear[dps[i].year] || 0} payment${perYear[dps[i].year] === 1 ? "" : "s"}`,
      capLast: true,
    });
  }
  if (yields.length >= 2) {
    lineChart($("#c-yield"), { points: yields.map(r => ({ label: r.year, value: r.yield })), format: pct, tickFormat: v => `${+v.toFixed(1)}%`, cls: "s3" });
  }
  if (fin.length) {
    columnChart($("#c-fin"), {
      categories: fin.map(r => r.year),
      series: [
        { name: "Revenue", values: fin.map(r => r.revenue), cls: "s1" },
        { name: "Net income", values: fin.map(r => r.net_income), cls: "s2" },
      ],
      format: v => `${compact(v)} SAR`,
      tickFormat: compact,
    });
  }
  if (margins.length >= 2) {
    lineChart($("#c-margin"), { points: margins.map(r => ({ label: r.year, value: r.margin })), format: pct, tickFormat: v => `${+v.toFixed(1)}%`, cls: "s3" });
  }
  if (c.prices.length >= 2) {
    lineChart($("#c-price"), {
      points: c.prices.map(([ym, close]) => ({ label: monthLabel(ym), value: close })),
      format: v => `${num(v)} SAR`,
      tickFormat: v => `${+v.toFixed(2)}`,
      cls: "s1",
      area: true,
      zeroBased: false,
    });
  }
}

/* ---------- Portfolio ---------- */

function projectIncome() {
  const yearAgo = new Date(asOf - 365 * 86400000);
  const months = MONTHS.map(() => ({ total: 0, parts: new Map() }));
  const rows = portfolio.holdings.map(h => {
    const c = byCode[h.code];
    const recent = c.dividends.filter(d => day(d.ex) > yearAgo && day(d.ex) <= asOf);
    for (const d of recent) {
      const m = months[day(d.pay || d.ex).getUTCMonth()];
      m.total += d.amount * h.shares;
      m.parts.set(h.code, (m.parts.get(h.code) || 0) + d.amount * h.shares);
    }
    const perShare = recent.reduce((sum, d) => sum + d.amount, 0);
    return { h, c, perShare, income: perShare * h.shares, value: c.price != null ? c.price * h.shares : null };
  });
  const total = rows.reduce((sum, r) => sum + r.income, 0);
  const priced = rows.filter(r => r.value != null);
  const value = priced.reduce((sum, r) => sum + r.value, 0);
  const pricedIncome = priced.reduce((sum, r) => sum + r.income, 0);
  return { rows, months, total, yieldOnValue: value ? (pricedIncome / value) * 100 : null };
}

function renderPortfolio() {
  const { rows, months, total, yieldOnValue } = projectIncome();
  app.innerHTML = `
    <div class="page-head">
      <h1>Portfolio income <span class="pro">Pro</span></h1>
      <p class="lede">What your holdings would pay over a year, based on what each company paid in the last 12 months.</p>
    </div>
    ${portfolio.example ? `<div class="notice"><span>This is an example portfolio. Add your own holdings below; they are saved in this browser only.</span><button type="button" class="btn ghost" id="clear">Clear example</button></div>` : ""}
    <div class="card hero-figure">
      <span class="label">Projected yearly dividends</span>
      <span class="value">${num(total, 0)}<small>SAR</small></span>
      <span class="note">${rows.length
        ? `About ${num(total / 12, 0)} SAR a month on average${yieldOnValue != null ? ` · ${pct(yieldOnValue)} yield on holdings with a price` : ""}`
        : "Add a holding to see your income."}</span>
    </div>
    <section class="section">
      <h2>By month paid</h2>
      <div class="card chart-card"><p class="muted" style="margin:0">Based on last year's payment dates. Months with no payout are empty.</p><div class="chart" id="c-months"></div></div>
    </section>
    <section class="section">
      <h2>Holdings</h2>
      ${rows.length ? `
      <div class="card flush table-wrap">
        <table>
          <thead><tr><th>Company</th><th class="num">Shares</th><th class="num">Dividends / share (12 mo)</th><th class="num">Yearly income (SAR)</th><th>Next ex-date</th><th><span class="muted" aria-hidden="true"></span></th></tr></thead>
          <tbody>${rows.map((r, i) => `<tr>
            <td><a href="#s${esc(r.c.code)}">${symbol(r.c)}</a></td>
            <td class="num"><input class="field shares-input" type="number" min="1" step="1" value="${r.h.shares}" data-i="${i}" id="shares-${esc(r.c.code)}" aria-label="Shares of ${esc(r.c.code)}"></td>
            <td class="num">${num(r.perShare, 3)}</td>
            <td class="num">${num(r.income, 0)}</td>
            <td>${r.c.next_ex ? dateLabel(r.c.next_ex) : `<span class="muted">—</span>`}</td>
            <td><button type="button" class="remove" data-i="${i}" aria-label="Remove ${esc(r.c.code)}">×</button></td>
          </tr>`).join("")}</tbody>
        </table>
      </div>` : ""}
      <form class="add-form" id="add-form" novalidate>
        <label>Company code<input id="add-code" class="field" list="codes" inputmode="numeric" placeholder="2222" autocomplete="off"></label>
        <label>Shares<input id="add-shares" class="field" type="number" min="1" step="1" value="100"></label>
        <button class="btn" type="submit">Add holding</button>
        <datalist id="codes">${data.companies.map(c => `<option value="${esc(c.code)}">${esc(c.name || "")}</option>`).join("")}</datalist>
      </form>
      <p id="add-error" class="down" hidden></p>
    </section>`;

  columnChart($("#c-months"), {
    categories: MONTHS,
    series: [{ name: "Dividends", values: months.map(m => m.total || null), cls: "s1" }],
    format: v => `${num(v, 0)} SAR`,
    tickFormat: compact,
    detail: i => [...months[i].parts].map(([code, v]) => `${code}: ${num(v, 0)}`).join(" · "),
  });

  $("#clear")?.addEventListener("click", () => { portfolio.holdings = []; saveHoldings(); renderPortfolio(); });
  app.querySelectorAll(".remove").forEach(b => b.addEventListener("click", () => {
    portfolio.holdings.splice(+b.dataset.i, 1);
    saveHoldings();
    renderPortfolio();
  }));
  app.querySelectorAll(".shares-input").forEach(input => input.addEventListener("change", () => {
    const shares = Math.floor(+input.value);
    if (shares > 0) {
      portfolio.holdings[+input.dataset.i].shares = shares;
      saveHoldings();
    }
    renderPortfolio();
  }));
  const codeInput = $("#add-code");
  if (pendingCode) {
    codeInput.value = pendingCode;
    pendingCode = null;
    $("#add-shares").focus();
  }
  $("#add-form").addEventListener("submit", e => {
    e.preventDefault();
    const code = codeInput.value.trim();
    const shares = Math.floor(+$("#add-shares").value);
    const error = $("#add-error");
    if (!byCode[code]) {
      error.textContent = `${code ? `“${code}” is not in the dataset.` : "Enter a company code."} Use the four-digit code, for example 2222.`;
      error.hidden = false;
      return;
    }
    if (!(shares > 0)) {
      error.textContent = "Enter how many shares you own, as a whole number above zero.";
      error.hidden = false;
      return;
    }
    const existing = portfolio.holdings.find(h => h.code === code);
    if (existing) existing.shares += shares;
    else portfolio.holdings.push({ code, shares });
    saveHoldings();
    renderPortfolio();
  });
}

/* ---------- charts (inline SVG, drawn to the container's width) ---------- */

function svgEl(tag, attrs, parent) {
  const el = document.createElementNS(NS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  parent?.appendChild(el);
  return el;
}

function niceScale(lo, hi, count = 4) {
  if (lo === hi) hi = lo + 1;
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(f => f * mag).find(s => s >= raw * 0.999);
  const min = Math.floor(lo / step + 1e-9) * step;
  const max = Math.ceil(hi / step - 1e-9) * step;
  const ticks = [];
  for (let v = min; v <= max + step / 2; v += step) ticks.push(+v.toFixed(10));
  return { min, max: ticks[ticks.length - 1], ticks };
}

// Column with a 4px rounded data end and a square foot on the baseline.
function barPath(x, y0, y1, w) {
  const r = Math.min(4, w / 2, Math.abs(y1 - y0));
  const s = y1 < y0 ? 1 : -1;
  return `M${x},${y0}V${y1 + s * r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + s * r}V${y0}Z`;
}

function axes(svg, sc, y, m, width) {
  for (const t of sc.ticks) {
    svgEl("line", { x1: m.left, x2: width - m.right, y1: y(t), y2: y(t), class: t === 0 ? "base" : "grid" }, svg);
    svgEl("text", { x: m.left - 8, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = sc.format(t);
  }
}

function showTip(el, svg, tip, html, x, top) {
  tip.innerHTML = html;
  tip.hidden = false;
  const left = Math.max(0, Math.min(x - tip.offsetWidth / 2, el.clientWidth - tip.offsetWidth));
  tip.style.left = `${left}px`;
  // SVG elements have no offsetTop, so measure the svg against its container.
  const svgTop = svg.getBoundingClientRect().top - el.getBoundingClientRect().top;
  tip.style.top = `${Math.max(0, svgTop + top - tip.offsetHeight - 8)}px`;
}

function columnChart(el, { categories, series, format, tickFormat = compact, detail, capLast = false, height = 220 }) {
  const draw = () => {
    el.innerHTML = series.length > 1
      ? `<div class="legend">${series.map((s, i) => `<span><i class="k${i + 1}"></i>${esc(s.name)}</span>`).join("")}</div>`
      : "";
    const width = el.clientWidth || 320;
    const m = { top: 22, right: 6, bottom: 24, left: 46 };
    const values = series.flatMap(s => s.values).filter(v => v != null);
    const sc = niceScale(Math.min(0, ...values), Math.max(0, ...values));
    sc.format = tickFormat;
    const plotH = height - m.top - m.bottom;
    const y = v => m.top + ((sc.max - v) / (sc.max - sc.min)) * plotH;
    const band = (width - m.left - m.right) / categories.length;
    const n = series.length, gap = 2;
    const barW = Math.max(2, Math.min(24, (band * 0.7 - gap * (n - 1)) / n));
    const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": series.map(s => s.name).join(" and ") + " by " + (typeof categories[0] === "number" ? "year" : "month") }, el);
    axes(svg, sc, y, m, width);
    const every = Math.ceil(36 / band);
    const bands = categories.map((cat, i) => {
      const hit = svgEl("rect", { x: m.left + band * i, y: m.top, width: band, height: plotH, class: "band" }, svg);
      const cx = m.left + band * (i + 0.5);
      series.forEach((s, j) => {
        const v = s.values[i];
        if (!v) return;
        const x = cx + (j - (n - 1) / 2) * (barW + gap) - barW / 2;
        svgEl("path", { d: barPath(x, y(0), y(v), barW), class: `bar ${s.cls}` }, svg);
      });
      if ((categories.length - 1 - i) % every === 0) {
        svgEl("text", { x: cx, y: height - 6, "text-anchor": "middle" }, svg).textContent = cat;
      }
      return hit;
    });
    if (capLast && n === 1) {
      const i = categories.length - 1, v = series[0].values[i];
      if (v) svgEl("text", { x: m.left + band * (i + 0.5), y: y(v) - 6, "text-anchor": "middle", class: "cap" }, svg).textContent = format(v);
    }
    const tip = document.createElement("div");
    tip.className = "tip";
    tip.hidden = true;
    el.appendChild(tip);
    bands.forEach((hit, i) => {
      const show = () => {
        bands.forEach(b => b.classList.toggle("on", b === hit));
        const lines = series.map(s => `${n > 1 ? `${esc(s.name)}: ` : ""}${s.values[i] == null ? "—" : esc(format(s.values[i]))}`);
        const extra = detail ? detail(i) : "";
        const top = Math.min(...series.map(s => (s.values[i] ? y(Math.max(s.values[i], 0)) : y(0))));
        showTip(el, svg, tip, `<b>${esc(categories[i])}</b>${lines.join("<br>")}${extra ? `<br>${esc(extra)}` : ""}`, m.left + band * (i + 0.5), top);
      };
      hit.addEventListener("pointerenter", show);
      hit.addEventListener("click", show);
    });
    svg.addEventListener("pointerleave", () => { tip.hidden = true; bands.forEach(b => b.classList.remove("on")); });
  };
  draw();
  redraws.push(draw);
}

function lineChart(el, { points, format, tickFormat, cls = "s1", area = false, zeroBased = true, height = 180 }) {
  const draw = () => {
    el.innerHTML = "";
    const width = el.clientWidth || 320;
    const m = { top: 22, right: 14, bottom: 24, left: 46 };
    const values = points.map(p => p.value);
    let lo = Math.min(...values), hi = Math.max(...values);
    if (zeroBased) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    else { const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad; }
    const sc = niceScale(lo, hi);
    sc.format = tickFormat;
    const plotH = height - m.top - m.bottom, plotW = width - m.left - m.right;
    const y = v => m.top + ((sc.max - v) / (sc.max - sc.min)) * plotH;
    const x = i => m.left + 10 + (i * (plotW - 20)) / Math.max(1, points.length - 1);
    const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": `Line chart, latest ${format(values[values.length - 1])}` }, el);
    axes(svg, sc, y, m, width);
    const d = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join("");
    if (area) svgEl("path", { d: `${d}L${x(points.length - 1)},${y(sc.min)}L${x(0)},${y(sc.min)}Z`, class: `area ${cls}` }, svg);
    svgEl("path", { d, class: `line ${cls}` }, svg);
    const last = points.length - 1;
    points.forEach((p, i) => {
      if (points.length <= 12 || i === last) svgEl("circle", { cx: x(i), cy: y(p.value), r: 4, class: `dot ${cls}` }, svg);
    });
    svgEl("text", { x: x(last), y: y(values[last]) - 10, "text-anchor": "end", class: "cap" }, svg).textContent = format(values[last]);
    const every = Math.ceil(points.length / Math.max(2, Math.floor(plotW / 64)));
    points.forEach((p, i) => {
      if ((last - i) % every === 0) svgEl("text", { x: x(i), y: height - 6, "text-anchor": "middle" }, svg).textContent = p.label;
    });
    const cross = svgEl("line", { y1: m.top, y2: m.top + plotH, class: "cross", visibility: "hidden" }, svg);
    const focus = svgEl("circle", { r: 5, class: `dot ${cls}`, visibility: "hidden" }, svg);
    const hit = svgEl("rect", { x: m.left, y: 0, width: plotW, height, class: "band" }, svg);
    const tip = document.createElement("div");
    tip.className = "tip";
    tip.hidden = true;
    el.appendChild(tip);
    const move = e => {
      const box = svg.getBoundingClientRect();
      const px = ((e.clientX - box.left) / box.width) * width;
      const i = Math.max(0, Math.min(last, Math.round(((px - m.left - 10) / (plotW - 20)) * last)));
      for (const [k, v] of [["x1", x(i)], ["x2", x(i)]]) cross.setAttribute(k, v);
      focus.setAttribute("cx", x(i));
      focus.setAttribute("cy", y(values[i]));
      cross.setAttribute("visibility", "visible");
      focus.setAttribute("visibility", "visible");
      showTip(el, svg, tip, `<b>${esc(points[i].label)}</b>${esc(format(values[i]))}`, x(i), y(values[i]));
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => {
      tip.hidden = true;
      cross.setAttribute("visibility", "hidden");
      focus.setAttribute("visibility", "hidden");
    });
  };
  draw();
  redraws.push(draw);
}

/* ---------- boot ---------- */

async function boot() {
  try {
    const res = await fetch("data.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`the server answered ${res.status}`);
    data = await res.json();
  } catch (e) {
    app.innerHTML = `<div class="page-head"><h1>The dividend data didn't load</h1>
      <p class="lede">The data file could not be read (${esc(e.message)}). Check your connection, then reload the page.</p></div>`;
    return;
  }
  byCode = Object.fromEntries(data.companies.map(c => [c.code, c]));
  asOf = day(data.as_of);
  portfolio = loadHoldings();
  route();
}

window.addEventListener("hashchange", route);
let lastWidth = window.innerWidth, resizeTimer;
window.addEventListener("resize", () => {
  if (window.innerWidth === lastWidth) return; // phones fire resize on scroll as the address bar hides
  lastWidth = window.innerWidth;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => redraws.forEach(draw => draw()), 150);
});
if ("serviceWorker" in navigator && location.protocol === "https:") {
  try { navigator.serviceWorker.register("sw.js").catch(() => {}); } catch { /* not allowed here */ }
}
boot();
