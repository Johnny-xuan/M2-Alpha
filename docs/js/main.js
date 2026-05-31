/* ════════════════════════════════════════════════════════════════════════
   main.js — entry point
   4 tab architecture: 今日推荐 / 每日复盘 / 回测业绩 / 关于
   ──────────────────────────────────────────────────────────────────────── */
import { $, $$, nextTradingDay } from "./utils.js";
import { startNavClock } from "./navbar.js";
import { initTheme } from "./theme.js";
import { initRouter } from "./router.js";
import { startCountUps } from "./hero.js";
import { renderPicksTable } from "./picks.js";
import { renderMiniExcess, renderRecentHits } from "./tab-picks.js";
import { renderScorecardSummary, renderExcessChart, initDateRange } from "./scorecard.js";
import { initSection3, refreshSection3 } from "./section3.js";

let _data = null;
const _renderedTabs = new Set(["picks"]);  // already rendered on init

(async function init() {
  initTheme();
  const res = await fetch("data/data.json");
  _data = await res.json();
  window._data = _data;

  populateMeta(_data);
  startNavClock();

  // Tab 1 is default - always render immediately
  renderTabPicks(_data);

  // Init router (sets initial visible tab + listens to clicks/hashchange)
  initRouter(onTabChange);

  startCountUps();
})();

/* ──────────── lazy tab rendering ──────────── */
function onTabChange(tab) {
  if (_renderedTabs.has(tab)) {
    // already rendered; just trigger refresh if it has charts that need resize
    if (tab === "backtest") refreshSection3();
    return;
  }
  _renderedTabs.add(tab);

  if (tab === "scorecard") renderTabScorecard(_data);
  else if (tab === "backtest") renderTabBacktest(_data);
  // "about" is static markup, no JS render needed
}

function renderTabPicks(data) {
  renderPicksTable(data);
  renderMiniExcess(data);
  renderRecentHits(data);
}

function renderTabScorecard(data) {
  renderScorecardSummary(data);
  renderExcessChart(data);
  initDateRange(data);
}

function renderTabBacktest(data) {
  initSection3(data);
}

/* ──────────── meta + dynamic text ──────────── */
function populateMeta(data) {
  const s = data.summary;
  const sc = data.scorecard?.summary || {};
  const months = data.monthly_returns || [];
  const latest = s.asof || "—";

  // 下一交易日 = picks 的真正"建仓日"
  const nextDay = nextTradingDay(latest);

  // navbar pill: 显示建仓日 (不是数据截止日)
  const navNextEl = document.getElementById("nav-next-day");
  if (navNextEl) navNextEl.textContent = nextDay;

  // picks 标题: 建仓日 (大) + 数据截止 (小字)
  const ntd = document.getElementById("next-trading-day");
  if (ntd) ntd.textContent = nextDay;
  const picksAsof = document.getElementById("picks-asof");
  if (picksAsof) picksAsof.textContent = latest;

  // derived
  const monthsTotal = months.length;
  const monthsWon = months.filter(m => (m.excess || 0) > 0).length;
  const tradingDays = s.n_days || (data.equity_curve?.length ?? 0);

  // STAT count-up animation values
  const STAT_MAP = {
    cum_return:        s.cum_return,
    monthly_win_rate:  s.monthly_win_rate,
    max_drawdown:      s.max_drawdown,
    sharpe:            s.sharpe,
    excess:            s.excess,
  };
  document.querySelectorAll("[data-stat]").forEach(el => {
    const v = STAT_MAP[el.dataset.stat];
    if (v != null) el.dataset.countTo = v;
  });

  // Template texts
  const fmtPctTxt = (v, d = 2) => (v >= 0 ? "+" : "") + v.toFixed(d) + "%";
  const TPL = {
    cum_return_text:        fmtPctTxt(s.cum_return, 1),
    sharpe_text:            s.sharpe.toFixed(2),
    monthly_win_text_short: s.monthly_win_rate.toFixed(0) + "%",
    mdd_text:               s.max_drawdown.toFixed(1) + "%",
    excess_pp:              (s.excess >= 0 ? "+" : "") + s.excess.toFixed(1) + " pp",
    monthly_win_text:       `${s.monthly_win_rate.toFixed(0)}% (${monthsWon}/${monthsTotal})`,
    monthly_won_text:       `${monthsTotal} 个月中 ${monthsWon} 个月跑赢`,
    monthly_won_count:      `${monthsWon} / ${monthsTotal}`,
    months_total:           monthsTotal,
    period_range:           `${s.start || "—"} → ${s.asof || "—"}`,
    start_date:             s.start || "—",
    trading_days:           tradingDays,
    benchmark_cum:          (s.benchmark_cum >= 0 ? "+" : "") + (s.benchmark_cum || 0).toFixed(1) + "%",
  };
  document.querySelectorAll("[data-tpl]").forEach(el => {
    const v = TPL[el.dataset.tpl];
    if (v != null) el.textContent = v;
  });

  // Scorecard summary stats
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

  // sc-days header counter
  const scDays = document.getElementById("sc-days");
  if (scDays && sc.n_days_total != null) scDays.textContent = sc.n_days_total;

  // sc-best
  if (sc.best_day) {
    const bestEl = document.getElementById("sc-best");
    const bestDEl = document.getElementById("sc-best-d");
    if (bestEl) bestEl.textContent = (sc.best_day.ret >= 0 ? "+" : "") + sc.best_day.ret.toFixed(2) + "%";
    if (bestDEl) bestDEl.textContent = sc.best_day.d;
  }
}
