/* ════════════════════════════════════════════════════════════════════════
   main.js — entry point for M²-Alpha · A 股每日选股参考
   ──────────────────────────────────────────────────────────────────────── */
import { $ } from "./utils.js";
import { startNavClock, initNavScrollSpy } from "./navbar.js";
import { initTheme } from "./theme.js";
import { renderFeatured, startCountUps } from "./hero.js";
import { renderPicksTable } from "./picks.js";
import { renderScorecardSummary, renderExcessChart, initDateRange } from "./scorecard.js";
import { initSection3 } from "./section3.js";

(async function init() {
  initTheme();                  // before anything else, avoid FOUC
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
  initSection3(data);           // master range + sub-tabs for backtest section
  startCountUps();
  initNavScrollSpy();
})();

/** populate meta-level data: dates, summary stats, scorecard stats, dynamic text */
function populateMeta(data) {
  const s = data.summary;
  const sc = data.scorecard?.summary || {};
  const months = data.monthly_returns || [];
  const latest = s.asof || "—";

  // —— 顶栏 / hero / picks 信号日期 ——
  document.querySelectorAll("#nav-asof, #qs-asof").forEach(el => el.textContent = latest);
  const feat = document.getElementById("featured-date");
  if (feat) feat.textContent = `${latest} 开盘`;
  const picksAsof = document.getElementById("picks-asof");
  if (picksAsof) picksAsof.textContent = latest;

  // —— 衍生量 ——
  const finalNavMult = s.final_nav && s.starting_nav
    ? s.final_nav / s.starting_nav
    : 1 + (s.cum_return || 0) / 100;

  const monthsTotal = months.length;
  const monthsWon = months.filter(m => (m.excess || 0) > 0).length;
  const tradingDays = s.n_days || (data.equity_curve?.length ?? 0);

  // —— Hero / Backtest 大数字（data-stat 注入到 data-count-to）——
  const STAT_MAP = {
    cum_return:        s.cum_return,
    monthly_win_rate:  s.monthly_win_rate,
    max_drawdown:      s.max_drawdown,
    sharpe:            s.sharpe,
    excess:            s.excess,
    final_nav_mult:    finalNavMult,
  };
  document.querySelectorAll("[data-stat]").forEach(el => {
    const v = STAT_MAP[el.dataset.stat];
    if (v != null) el.dataset.countTo = v;
  });

  // —— 文本占位符 ——
  const TPL = {
    excess_pp:           (s.excess >= 0 ? "+" : "") + s.excess.toFixed(1) + " pp",
    monthly_win_text:    `${s.monthly_win_rate.toFixed(0)}% (${monthsWon}/${monthsTotal})`,
    monthly_won_text:    `${monthsTotal} 个月中 ${monthsWon} 个月跑赢`,
    monthly_won_count:   `${monthsWon} / ${monthsTotal}`,
    months_total:        monthsTotal,
    period_range:        `${s.start || "—"} → ${s.asof || "—"}`,
    start_date:          s.start || "—",
    trading_days:        tradingDays,
    benchmark_cum:       (s.benchmark_cum >= 0 ? "+" : "") + (s.benchmark_cum || 0).toFixed(1) + "%",
  };
  document.querySelectorAll("[data-tpl]").forEach(el => {
    const v = TPL[el.dataset.tpl];
    if (v != null) el.textContent = v;
  });

  // Backtest 段里"沪深 300 同期 X%"
  document.querySelectorAll('[data-stat-text="benchmark_cum"]').forEach(el => {
    el.textContent = TPL.benchmark_cum;
  });

  // —— Scorecard summary stats ——
  const SC_STAT_MAP = {
    excess_avg:               sc.excess_avg,
    win_rate_vs_bench_daily:  sc.win_rate_vs_bench_daily,
    avg_hit_rate:             sc.avg_hit_rate,
  };
  document.querySelectorAll("[data-sc-stat]").forEach(el => {
    const v = SC_STAT_MAP[el.dataset.scStat];
    if (v != null) el.dataset.countTo = v;
  });

  const SC_TEXT_MAP = {
    n_days_total: sc.n_days_total,
    win_days: sc.n_days_total != null && sc.win_rate_vs_bench_daily != null
      ? Math.round(sc.n_days_total * sc.win_rate_vs_bench_daily / 100)
      : null,
  };
  document.querySelectorAll("[data-sc-text]").forEach(el => {
    const v = SC_TEXT_MAP[el.dataset.scText];
    if (v != null) el.textContent = v;
  });
}
