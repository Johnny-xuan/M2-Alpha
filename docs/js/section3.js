/* ────────────────────────────────────────────────────────────
   section3.js — Section 03 controller
     · master time-range selector (chips + date inputs)
     · sub-tabs (overview / equity / monthly / holdings)
     · re-computes all 4 panels' data from the selected range
   ──────────────────────────────────────────────────────────── */
import { $, $$, fmtPct } from "./utils.js";
import { drawEquityChart } from "./equity-chart.js";
import { renderMonthlyBars } from "./monthly.js";
import { renderHoldingsPanel } from "./holdings.js";

const STARTING_NAV = 1_000_000;

let _data = null;
let _range = null;   // { start: "YYYY-MM-DD", end: "YYYY-MM-DD" }

export function initSection3(data) {
  _data = data;
  if (!data.equity_curve?.length) return;

  const minD = data.equity_curve[0].d;
  const maxD = data.equity_curve[data.equity_curve.length - 1].d;
  _range = { start: minD, end: maxD };

  const startEl = $("#s3-start"), endEl = $("#s3-end");
  startEl.min = endEl.min = minD;
  startEl.max = endEl.max = maxD;
  startEl.value = minD; endEl.value = maxD;

  // preset chips
  $$('[data-s3-preset]').forEach(btn => {
    btn.addEventListener("click", () => {
      $$('[data-s3-preset]').forEach(b => b.classList.remove("sc-chip-btn--active"));
      btn.classList.add("sc-chip-btn--active");
      applyPreset(btn.dataset.s3Preset);
    });
  });
  $("#s3-apply").addEventListener("click", () => {
    $$('[data-s3-preset]').forEach(b => b.classList.remove("sc-chip-btn--active"));
    applyRange(startEl.value, endEl.value);
  });
  [startEl, endEl].forEach(el => {
    el.addEventListener("change", () => {
      $$('[data-s3-preset]').forEach(b => b.classList.remove("sc-chip-btn--active"));
    });
    el.addEventListener("keydown", e => { if (e.key === "Enter") $("#s3-apply").click(); });
  });

  // sub-tabs
  $$('.section-tab').forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.stab));
  });

  // initial render
  rerenderAll();
}

function switchTab(name) {
  $$('.section-tab').forEach(b => b.classList.toggle("section-tab--active", b.dataset.stab === name));
  $$('[data-stab-panel]').forEach(p => {
    p.hidden = p.dataset.stabPanel !== name;
  });
  // re-render the now-visible panel (charts need to size correctly after un-hiding)
  if (name === "equity") {
    const slice = filterEquity();
    drawEquityChart(slice);
  } else if (name === "monthly") {
    renderMonthlyBars(filterMonthly(slice => slice));
  }
}

function applyPreset(preset) {
  const all = _data.equity_curve;
  const lastDate = all[all.length - 1].d;
  if (preset === "all") {
    _range = { start: all[0].d, end: lastDate };
  } else {
    const m = { "1m": 1, "3m": 3, "6m": 6, "1y": 12 }[preset];
    const d = new Date(lastDate); d.setMonth(d.getMonth() - m);
    _range = { start: d.toISOString().slice(0, 10), end: lastDate };
  }
  $("#s3-start").value = _range.start;
  $("#s3-end").value = _range.end;
  rerenderAll();
}

function applyRange(startD, endD) {
  if (!startD || !endD) return;
  _range = { start: startD, end: endD };
  rerenderAll();
}

function filterEquity() {
  return _data.equity_curve.filter(d => d.d >= _range.start && d.d <= _range.end);
}

function filterMonthly() {
  const startM = _range.start.slice(0, 7);
  const endM = _range.end.slice(0, 7);
  return _data.monthly_returns.filter(m => m.m >= startM && m.m <= endM);
}

function filterScorecardPicks() {
  const byDate = _data.scorecard?.by_date || {};
  const out = [];
  for (const [d, day] of Object.entries(byDate)) {
    if (d >= _range.start && d <= _range.end) out.push(day);
  }
  return out;
}

/* ──────────── compute overview stats from filtered slice ──────────── */
function computeOverview(slice) {
  if (slice.length < 2) return null;
  const startNav = slice[0].nav;
  const endNav = slice[slice.length - 1].nav;
  const cum = (endNav / startNav - 1) * 100;
  const benchStart = slice[0].bench;
  const benchEnd = slice[slice.length - 1].bench;
  const benchPct = (benchEnd / benchStart - 1) * 100;

  const rets = [];
  for (let i = 1; i < slice.length; i++) rets.push(slice[i].nav / slice[i - 1].nav - 1);
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const varr = rets.reduce((a, b) => a + (b - mean) * (b - mean), 0) / rets.length;
  const std = Math.sqrt(varr);
  const sharpe = std > 0 ? (mean / std) * Math.sqrt(252) : 0;

  let peak = slice[0].nav, mdd = 0;
  for (const d of slice) {
    if (d.nav > peak) peak = d.nav;
    const dd = d.nav / peak - 1;
    if (dd < mdd) mdd = dd;
  }

  const finalMult = endNav / startNav;
  return {
    cum, benchPct, excess: cum - benchPct, sharpe, mdd: mdd * 100, finalMult,
    days: slice.length,
    startDate: slice[0].d, endDate: slice[slice.length - 1].d,
  };
}

/* ──────────── re-render everything for current range ──────────── */
function rerenderAll() {
  const eqSlice = filterEquity();
  const monthlySlice = filterMonthly();
  const picksSlice = filterScorecardPicks();

  // Section meta (range summary)
  $("#s3-range-text").textContent = `${_range.start} → ${_range.end}`;
  $("#s3-meta-days").textContent = eqSlice.length;
  $("#s3-meta-months").textContent = monthlySlice.length;

  // Overview panel
  renderOverview(eqSlice, monthlySlice);

  // Equity chart (only render if its panel is visible OR pre-compute and store)
  const eqActive = !$('[data-stab-panel="equity"]').hidden;
  if (eqActive) drawEquityChart(eqSlice);

  // Monthly bars (only if visible)
  const mActive = !$('[data-stab-panel="monthly"]').hidden;
  if (mActive) {
    renderMonthlyBars({ monthly_returns: monthlySlice });
    const won = monthlySlice.filter(m => (m.excess || 0) > 0).length;
    $("#s3-monthly-win-frac").textContent = `${won} / ${monthlySlice.length}`;
  }

  // Holdings — recompute industry / top-held from sliced picks
  const hActive = !$('[data-stab-panel="holdings"]').hidden;
  if (hActive) {
    const subdata = recomputeHoldings(picksSlice);
    renderHoldingsPanel(subdata);
  }
}

function renderOverview(eqSlice, monthlySlice) {
  const o = computeOverview(eqSlice);
  if (!o) return;
  const monthsWon = monthlySlice.filter(m => (m.excess || 0) > 0).length;
  const monthlyWinRate = monthlySlice.length ? monthsWon / monthlySlice.length * 100 : 0;

  setNum("#s3-final-nav-mult", o.finalMult.toFixed(2) + "x", "");
  setNum("#s3-cum-return", (o.cum >= 0 ? "+" : "") + o.cum.toFixed(2) + "%", o.cum >= 0 ? "gain" : "loss");
  setNum("#s3-excess", (o.excess >= 0 ? "+" : "") + o.excess.toFixed(2) + "pp", o.excess >= 0 ? "gain" : "loss");
  setNum("#s3-monthly-win-rate", monthlyWinRate.toFixed(1) + "%", monthlyWinRate >= 50 ? "gain" : "loss");
  setNum("#s3-mdd", o.mdd.toFixed(2) + "%", "loss");
  setNum("#s3-sharpe", o.sharpe.toFixed(2), o.sharpe >= 1 ? "gain" : "");

  $("#s3-bench-cum").textContent = (o.benchPct >= 0 ? "+" : "") + o.benchPct.toFixed(2) + "%";
  $("#s3-monthly-win-text").textContent = `${monthlySlice.length} 个月中 ${monthsWon} 个月跑赢`;
}

function setNum(sel, txt, cls) {
  const el = $(sel);
  if (!el) return;
  el.textContent = txt;
  el.classList.remove("gain", "loss");
  if (cls) el.classList.add(cls);
}

function recomputeHoldings(picksDays) {
  const indCount = {};
  const tickerCount = {};
  const tickerInfo = {};
  let totalPicks = 0;
  for (const day of picksDays) {
    for (const p of (day.picks || [])) {
      const ind = p.ind || "—";
      indCount[ind] = (indCount[ind] || 0) + 1;
      tickerCount[p.ts] = (tickerCount[p.ts] || 0) + 1;
      totalPicks++;
      if (!tickerInfo[p.ts]) tickerInfo[p.ts] = { name: p.name || p.ts, industry: p.ind || "—" };
    }
  }
  const nDays = picksDays.length || 1;

  const industry_avg = Object.entries(indCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([k, v]) => ({ industry: k, weight: +(v / totalPicks * 100).toFixed(2) }));

  const top_held = Object.entries(tickerCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([ts, days]) => ({
      ts,
      name: tickerInfo[ts].name,
      industry: tickerInfo[ts].industry,
      days,
      pct: +(days / nDays * 100).toFixed(1),
    }));

  return { industry_avg, top_held };
}
