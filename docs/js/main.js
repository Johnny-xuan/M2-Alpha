/* ════════════════════════════════════════════════════════════════════════
   main.js — entry point
   4 tab architecture: 今日推荐 / 每日复盘 / 回测业绩 / 关于
   ──────────────────────────────────────────────────────────────────────── */
import { $, $$, nextTradingDay } from "./utils.js";
import { LANG, t } from "./i18n.js?v=20260709-bilingual1";
import { startNavClock } from "./navbar.js?v=20260709-bilingual1";
import { initTheme } from "./theme.js?v=20260709-bilingual1";
import { initRouter } from "./router.js";
import { startCountUps } from "./hero.js";
import { renderPicksTable } from "./picks.js?v=20260709-bilingual1";
import { renderMiniExcess, renderRecentHits } from "./tab-picks.js?v=20260709-bilingual1";
import { renderScorecardSummary, renderExcessChart, initDateRange } from "./scorecard.js?v=20260709-bilingual1";
import { initSection3, refreshSection3 } from "./section3.js?v=20260709-bilingual1";

const MODEL_STORAGE_KEY = "m2alpha-model-version-v4";

let _rawData = null;
let _data = null;
const _renderedTabs = new Set(["picks"]);  // already rendered on init

(async function init() {
  initTheme();
  initLangLinks();
  try {
    const res = await fetch("data/data.json", { cache: "no-cache" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    _rawData = await res.json();
    _data = selectModelView(_rawData);
    window._data = _data;
    window._rawData = _rawData;
  } catch (e) {
    return showFatalError(e);
  }

  renderModelSwitcher(_rawData);
  populateMeta(_data);
  startNavClock();

  // Tab 1 is default - always render immediately
  renderTabPicks(_data);

  // Init router (sets initial visible tab + listens to clicks/hashchange)
  initRouter(onTabChange);
  initCopyButtons();

  startCountUps();
})();

function selectModelView(raw, forcedKey = null) {
  if (!raw.models) return raw;
  const order = raw.model_order || Object.keys(raw.models);
  const saved = readSavedModelKey();
  const key = forcedKey && raw.models[forcedKey]
    ? forcedKey
    : (saved && raw.models[saved] ? saved : (raw.default_model || order[0]));
  const selected = raw.models[key] || raw.models[order[0]];
  return {
    ...selected,
    data_sources: raw.data_sources,
    strategy: raw.strategy,
    research_references: raw.research_references,
    backtest_leader: raw.backtest_leader,
    research_highlight: raw.research_highlight || selected.model?.research_benchmark,
  };
}

function readSavedModelKey() {
  try {
    return localStorage.getItem(MODEL_STORAGE_KEY);
  } catch (e) {
    return null;
  }
}

function saveModelKey(key) {
  try {
    localStorage.setItem(MODEL_STORAGE_KEY, key);
  } catch (e) {
    // The page can still reload into the default model if storage is unavailable.
  }
}

function renderModelSwitcher(raw) {
  const host = document.getElementById("model-switcher");
  if (!host || !raw.models) return;
  const activeKey = _data?.model?.key || raw.default_model;
  const order = raw.model_order || Object.keys(raw.models);
  host.innerHTML = order.map(key => {
    const model = raw.models[key]?.model;
    if (!model) return "";
    const active = key === activeKey;
    return `
      <button class="model-switcher__btn${active ? " model-switcher__btn--active" : ""}"
              data-model-key="${key}"
              title="${model.title} · ${model.role}"
              aria-pressed="${active ? "true" : "false"}">
        ${model.label}
      </button>
    `;
  }).join("");

  host.onclick = (e) => {
    const btn = e.target.closest("[data-model-key]");
    if (!btn) return;
    const nextKey = btn.dataset.modelKey;
    if (nextKey === activeKey) return;
    switchModel(nextKey);
  };
}

function switchModel(nextKey) {
  if (!_rawData?.models?.[nextKey]) return;
  saveModelKey(nextKey);
  _data = selectModelView(_rawData, nextKey);
  window._data = _data;
  renderModelSwitcher(_rawData);
  populateMeta(_data);
  renderTabPicks(_data);
  if (_renderedTabs.has("scorecard")) renderTabScorecard(_data);
  if (_renderedTabs.has("backtest")) renderTabBacktest(_data);
  if (_renderedTabs.has("about")) initAboutDocs();
  startCountUps();
}

/** 数据加载失败时的兜底 UI */
function showFatalError(err) {
  const main = document.querySelector(".tab-area");
  if (!main) return;
  main.innerHTML = `
    <div style="
      max-width:520px; margin:80px auto; padding:32px;
      background:var(--bg-2); border:1px solid var(--coral);
      border-left:3px solid var(--coral); border-radius:6px;
      text-align:center; color:var(--ink-dim); font-size:14px; line-height:1.7;
    ">
      <h2 style="color:var(--coral); margin-bottom:14px; font-size:18px;">${t("fatal.title")}</h2>
      <p>${t("fatal.body")}</p>
      <p style="margin-top:12px; font-size:12px; color:var(--ink-mute);">
        Error: <code>${(err && err.message) || err}</code>
      </p>
      <p style="margin-top:20px;">
        <a href="https://github.com/Johnny-xuan/M2-Alpha/actions" target="_blank" rel="noopener"
           style="color:var(--lime); text-decoration:none; font-weight:600;">
          ${t("fatal.github")} →
        </a>
      </p>
    </div>
  `;
}

/* ──────────── lazy tab rendering ──────────── */
function onTabChange(tab) {
  if (tab === "about") {
    _renderedTabs.add(tab);
    initAboutDocs();
    return;
  }

  if (_renderedTabs.has(tab)) {
    // already rendered; just trigger refresh if it has charts that need resize
    if (tab === "backtest") refreshSection3();
    return;
  }
  _renderedTabs.add(tab);

  if (tab === "scorecard") renderTabScorecard(_data);
  else if (tab === "backtest") renderTabBacktest(_data);
}

/* ─── About docs: hash-driven page switch ─── */
function initAboutDocs() {
  const pages = [...document.querySelectorAll('[data-about-page]')];
  const links = [...document.querySelectorAll('.about-toc__a')];
  if (!pages.length || !links.length) return;

  const ids = new Set(pages.map(page => page.id));
  const hashId = (location.hash || "").replace(/^#/, "");
  const activeId = ids.has(hashId) ? hashId : "about-overview";

  pages.forEach(page => {
    const active = page.id === activeId;
    page.hidden = !active;
    page.classList.toggle("about-page--active", active);
    page.setAttribute("aria-hidden", active ? "false" : "true");
  });
  links.forEach(link => {
    const active = link.getAttribute("href") === `#${activeId}`;
    link.classList.toggle("about-toc__a--active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  initCopyButtons();
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

function initCopyButtons() {
  document.querySelectorAll("[data-copy-target]").forEach(btn => {
    if (btn.dataset.copyBound === "1") return;
    btn.dataset.copyBound = "1";
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      await copyFromButton(btn);
    });
  });
}

async function copyFromButton(btn) {
  const target = document.getElementById(btn.dataset.copyTarget);
  const text = target?.textContent || "";
  if (!text.trim() || btn.disabled) return;

  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = t("copy.busy");
  try {
    await copyText(text);
    btn.textContent = t("copy.done");
    btn.classList.add("code-copy--done");
  } catch (e) {
    const selected = target ? selectElementText(target) : false;
    btn.textContent = selected ? t("copy.selected") : t("copy.fail");
  } finally {
    window.setTimeout(() => {
      btn.disabled = false;
      btn.textContent = original;
      btn.classList.remove("code-copy--done");
    }, 1400);
  }
}

async function copyText(text) {
  if (copyTextWithTextarea(text)) return;

  if (navigator.clipboard?.writeText) {
    await Promise.race([
      navigator.clipboard.writeText(text),
      new Promise((_, reject) => {
        window.setTimeout(() => reject(new Error("Clipboard timeout")), 800);
      }),
    ]);
    return;
  }

  throw new Error("Clipboard API unavailable");
}

function copyTextWithTextarea(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  const selection = document.getSelection();
  const previousRange = selection && selection.rangeCount ? selection.getRangeAt(0) : null;
  textarea.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  } finally {
    textarea.remove();
    if (previousRange && selection) {
      selection.removeAllRanges();
      selection.addRange(previousRange);
    }
  }
  return ok;
}

function selectElementText(el) {
  const selection = document.getSelection();
  if (!selection || !document.createRange) return false;
  const range = document.createRange();
  range.selectNodeContents(el);
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}

/* ──────────── meta + dynamic text ──────────── */
function populateMeta(data) {
  const s = data.summary;
  const sc = data.scorecard?.summary || {};
  const months = data.monthly_returns || [];
  const model = data.model || {};
  const researchCurve = (data.backtest_curves || []).find(c => c.key === "m2m")
    || (data.backtest_curves || []).at?.(-1);
  const research = data.research_highlight || model.research_benchmark || (researchCurve ? {
    model_label: researchCurve.label,
    label: t("research.backtest"),
    cum_pct: researchCurve.summary?.cum_return,
    sharpe: researchCurve.summary?.sharpe,
    max_dd_pct: researchCurve.summary?.max_drawdown,
    basis: `${researchCurve.summary?.start || "—"} → ${researchCurve.summary?.asof || "—"} · local research top1000`,
  } : {});
  const latest = s.asof || "—";
  renderDataSourceStatus(data);

  const nextDay = nextTradingDay(latest);

  const ntd = document.getElementById("next-trading-day");
  const navNextEl = document.getElementById("nav-next-day");
  if (navNextEl) navNextEl.textContent = nextDay;
  if (ntd) ntd.textContent = nextDay;
  const picksAsof = document.getElementById("picks-asof");
  if (picksAsof) picksAsof.textContent = latest;
  const picksModel = document.getElementById("picks-model-title");
  if (picksModel) picksModel.textContent = model.title || s.model_title || "M2-Alpha";
  const aboutModel = document.getElementById("about-model-chip");
  if (aboutModel) aboutModel.textContent = "3 weights";

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
    research_metric_label:  `${research.model_label ? research.model_label + " " : ""}${research.label || t("research.backtest")}`,
    research_cum_text:      research.cum_pct != null ? fmtPctTxt(research.cum_pct, 1) : "—",
    research_sharpe_text:   research.sharpe != null ? Number(research.sharpe).toFixed(2) : "—",
    research_mdd_text:      research.max_dd_pct != null ? fmtPctTxt(research.max_dd_pct, 1) : "—",
    research_basis_text:    research.basis || "—",
    capability_basis_text:  capabilityBasisText(research.basis),
    excess_pp:              (s.excess >= 0 ? "+" : "") + s.excess.toFixed(1) + " pp",
    monthly_win_text:       `${s.monthly_win_rate.toFixed(0)}% (${monthsWon}/${monthsTotal})`,
    monthly_won_text:       t("section.monthlyWin", { months: monthsTotal, won: monthsWon }),
    monthly_won_count:      `${monthsWon} / ${monthsTotal}`,
    months_total:           monthsTotal,
    period_range:           `${s.start || "—"} → ${s.asof || "—"}`,
    start_date:             s.start || "—",
    trading_days:           tradingDays,
    benchmark_cum:          (s.benchmark_cum >= 0 ? "+" : "") + (s.benchmark_cum || 0).toFixed(1) + "%",
    worst_day_ret:          sc.worst_day ? fmtPctTxt(sc.worst_day.ret, 2) : "—",
    worst_day_d:            sc.worst_day?.d || "—",
  };
  document.querySelectorAll("[data-tpl]").forEach(el => {
    const v = TPL[el.dataset.tpl];
    if (v != null) el.textContent = v;
  });

  // 给"可正可负的数字"动态贴 gain/loss class（A 股习惯：>0 红，<0 绿）
  const SIGN_KEYS = {
    cum_return:       s.cum_return,
    excess:           s.excess,
    excess_avg:       sc.excess_avg,
  };
  document.querySelectorAll("[data-stat]").forEach(el => {
    const k = el.dataset.stat;
    if (!(k in SIGN_KEYS)) return;
    const v = SIGN_KEYS[k];
    el.classList.remove("gain", "loss");
    if (v != null) el.classList.add(v >= 0 ? "gain" : "loss");
  });
  document.querySelectorAll("[data-sc-stat]").forEach(el => {
    const k = el.dataset.scStat;
    if (!(k in SIGN_KEYS)) return;
    const v = SIGN_KEYS[k];
    el.classList.remove("gain", "loss");
    if (v != null) el.classList.add(v >= 0 ? "gain" : "loss");
  });
  // cum_return_text 是 data-tpl，单独处理
  const cumEl = document.querySelector('[data-tpl="cum_return_text"]');
  if (cumEl) {
    cumEl.classList.remove("gain", "loss");
    cumEl.classList.add(s.cum_return >= 0 ? "gain" : "loss");
  }

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

function sourceStatusClass(status) {
  if (status === "ok") return "ok";
  if (status === "partial") return "partial";
  if (status === "skipped") return "muted";
  return "warn";
}

function sourceStatusText(status) {
  const map = {
    ok: "ok",
    partial: "partial",
    skipped: "skipped",
    empty: "empty",
    error: "error",
  };
  return map[status] || "unknown";
}

function coverageText(n, d) {
  if (!d) return "—";
  return Math.round((n || 0) / d * 100) + "%";
}

function capabilityBasisText(basis) {
  if (!basis) return t("capability.basisFallback");
  const dateRange = basis.split("·")[0]?.trim();
  return t("capability.basis", { dateRange });
}

function renderDataSourceStatus(data) {
  const host = document.getElementById("data-source-inline");
  if (!host) return;
  const ds = data.data_sources || {};
  const meta = ds.metadata || {};
  if (!Object.keys(meta).length) {
    host.innerHTML = `
      <span class="data-source-inline__tag">data</span>
      <div class="data-source-inline__body">
        <div class="data-source-inline__title">
          ${t("data.baselineTitle", { asof: data.summary?.asof })}
        </div>
        <div class="data-source-inline__chips">
          <span class="ds-chip ds-chip--ok"><i></i><b>panel</b><em>dynamic top1000</em></span>
          <span class="ds-chip ds-chip--ok"><i></i><b>engine</b><em>benchmark.py</em></span>
          <span class="ds-chip ds-chip--ok"><i></i><b>strategy</b><em>top5 / pool100</em></span>
        </div>
        <div class="data-source-inline__note">
          ${data.backtest_curve_note || t("data.fallbackNote")}
        </div>
      </div>
    `;
    return;
  }
  const sources = meta.sources || {};
  const applied = meta.applied || {};
  const money = meta.applied_moneyflow || {};
  const targetRows = applied.target_rows || 0;
  const volume = sources["derived.volume_ratio_from_baostock_volume"] || {};
  const ak = sources["akshare.stock_zh_a_spot_em"] || {};
  const efRt = sources["efinance.stock.get_realtime_quotes"] || {};
  const efBase = sources["efinance.stock.get_base_info"] || {};
  const eastmoney = sources["eastmoney.moneyflow_history"] || {};
  const efBills = sources["efinance.stock.get_history_bill"] || {};

  const chips = [
    {
      label: "volume_ratio",
      value: volume.active_after ? `${volume.active_after.toLocaleString()} rows` : sourceStatusText(volume.status),
      status: sourceStatusClass(volume.status),
    },
    {
      label: "AKShare spot",
      value: sourceStatusText(ak.status),
      status: sourceStatusClass(ak.status),
    },
    {
      label: "efinance realtime",
      value: sourceStatusText(efRt.status),
      status: sourceStatusClass(efRt.status),
    },
    {
      label: "efinance base",
      value: targetRows ? coverageText(efBase.matched_target_rows, targetRows) : sourceStatusText(efBase.status),
      status: sourceStatusClass(efBase.status),
    },
    {
      label: "moneyflow",
      value: money.rows_applied ? `${money.rows_applied.toLocaleString()} rows` : sourceStatusText(eastmoney.status || money.status),
      status: sourceStatusClass(eastmoney.status || money.status),
    },
    {
      label: "efinance bills",
      value: sourceStatusText(efBills.status),
      status: sourceStatusClass(efBills.status),
    },
  ];

  host.innerHTML = `
    <span class="data-source-inline__tag">data</span>
    <div class="data-source-inline__body">
      <div class="data-source-inline__title">
        ${t("data.enrichedTitle", { asof: meta.target_date || data.summary?.asof })}
      </div>
      <div class="data-source-inline__chips">
        ${chips.map(chip => `
          <span class="ds-chip ds-chip--${chip.status}">
            <i></i><b>${chip.label}</b><em>${chip.value}</em>
          </span>
        `).join("")}
      </div>
      <div class="data-source-inline__note">
        ${t("data.note")}
      </div>
    </div>
  `;
}

function initLangLinks() {
  const links = [...document.querySelectorAll("[data-lang-link], [data-lang-target]")];
  if (!links.length) return;
  const sync = () => {
    const hash = location.hash || "#picks";
    links.forEach(link => {
      const file = link.dataset.langTarget || (link.dataset.langLink === "en" ? "en.html" : "index.html");
      const lang = link.dataset.langLink || (file.includes("en") ? "en" : "zh");
      link.href = `${file}${hash}`;
      const active = (lang === "en") === (LANG === "en");
      link.classList.toggle("lang-switcher__link--active", active);
      if (active) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  };
  sync();
  window.addEventListener("hashchange", sync);
}
