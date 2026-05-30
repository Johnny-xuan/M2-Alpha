/* ════════════════════════════════════════════════════════════════════════
   main.js — entry point for M²-Alpha · A 股每日选股参考
   ──────────────────────────────────────────────────────────────────────── */
import { $ } from "./utils.js";
import { startNavClock, initNavScrollSpy } from "./navbar.js";
import { renderFeatured, startCountUps } from "./hero.js";
import { renderPicksTable } from "./picks.js";
import { renderScorecardSummary, renderExcessChart, initDateRange } from "./scorecard.js";
import { renderEquityChart } from "./equity-chart.js";
import { renderMonthlyBars } from "./monthly.js";
import { renderHoldingsPanel } from "./holdings.js";

(async function init() {
  const res = await fetch("data/data.json");
  const data = await res.json();
  window._data = data;          // debugging

  populateMeta(data);
  startNavClock();
  renderFeatured(data);
  renderPicksTable(data);
  renderScorecardSummary(data);
  renderExcessChart(data);
  initDateRange(data);
  renderEquityChart(data);
  renderMonthlyBars(data);
  renderHoldingsPanel(data);
  startCountUps();
  initNavScrollSpy();
})();

/** populate meta-level data: dates / counters / signal pill */
function populateMeta(data) {
  const s = data.summary;
  const latest = data.current_holdings?.[0]?._asof || "2026-06-01";
  $("#nav-asof").textContent = latest;
  $("#qs-asof").textContent = latest;
  $("#featured-date").textContent = `${latest} 开盘`;
  $("#picks-asof").textContent = s.asof;
  $("#perf-bench").textContent = (s.benchmark_cum >= 0 ? "+" : "") + s.benchmark_cum.toFixed(1) + "%";
}
