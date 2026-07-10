/* ────────────────────────────────────────────────────────────
   scorecard.js — Section 02
     · summary stats wiring (via data-count-to in HTML)
     · 60-day excess bar chart
     · date range picker + chips + recent days list
   ──────────────────────────────────────────────────────────── */
import { $, $$, svg, fmtPct } from "./utils.js";
import { t } from "./i18n.js?v=20260709-bilingual1";

const PAGE_SIZE = 10;
let _scState = null;     // { dates: [...], page: N }

/* ─── populate scorecard sub-header stats (best day) ─── */
export function renderScorecardSummary(data) {
  const sc = data.scorecard?.summary;
  if (!sc) return;
  $("#sc-days").textContent = sc.n_days_total;
  if (sc.best_day) {
    $("#sc-best").textContent = fmtPct(sc.best_day.ret);
    $("#sc-best-d").textContent = sc.best_day.d;
  }
}

/* ─── 60-day excess bar chart ─── */
export function renderExcessChart(data) {
  const svgEl = $("#excess-chart");
  if (!svgEl) return;
  const all = data.scorecard.all_dates;
  const series = all.slice(-60);
  if (!series.length) return;

  const W = 1400, H = 280;
  const padL = 56, padR = 24, padT = 24, padB = 36;
  const w = W - padL - padR, h = H - padT - padB;
  const n = series.length;

  const vals = series.map(d => d.excess || 0);
  const absMax = Math.max(...vals.map(Math.abs), 0.5) * 1.1;

  const xAt = (i) => padL + (i + 0.5) * (w / n);
  const yMid = padT + h / 2;
  const yScale = (v) => yMid - (v / absMax) * (h / 2);
  const barW = Math.max(2, w / n - 2);

  svgEl.innerHTML = "";
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);

  // grid + labels
  for (let k = -2; k <= 2; k++) {
    const yy = yMid + (k / 2) * (h / 2);
    svgEl.appendChild(svg("line", {
      x1: padL, x2: W - padR, y1: yy, y2: yy,
      class: k === 0 ? "axis-zero" : "grid-line",
    }));
    const lab = svg("text", { x: padL - 10, y: yy + 3, "text-anchor": "end", class: "axis-label" });
    lab.textContent = (k * absMax / 2 > 0 ? "+" : "") + (k * absMax / 2).toFixed(1) + "%";
    svgEl.appendChild(lab);
  }

  // x-axis date ticks
  const nTicks = 6;
  for (let k = 0; k <= nTicks; k++) {
    const i = Math.round(k / nTicks * (n - 1));
    const lab = svg("text", { x: xAt(i), y: H - 12, "text-anchor": "middle", class: "axis-label" });
    lab.textContent = series[i].d.slice(2, 7);
    svgEl.appendChild(lab);
  }

  // bars
  series.forEach((d, i) => {
    if (d.excess == null) return;
    const v = d.excess;
    const x = xAt(i) - barW / 2;
    const y = v >= 0 ? yScale(v) : yMid;
    const ht = Math.abs(yScale(v) - yMid);
    const rect = svg("rect", {
      x, y, width: barW, height: Math.max(1, ht), rx: 1,
      fill: v >= 0 ? "#ff6b3c" : "#c8f93d",
    });
    rect.style.opacity = "0";
    rect.style.animation = `fade-up 0.4s ${0.005 * i}s forwards cubic-bezier(0.22, 0.61, 0.36, 1)`;
    if (v >= 0) rect.setAttribute("filter", "drop-shadow(0 0 3px rgba(255, 107, 60, 0.36))");
    svgEl.appendChild(rect);
  });
}

/* ─── date range picker ─── */
export function initDateRange(data) {
  const allDates = Object.keys(data.scorecard.by_date).sort();
  if (!allDates.length) return;
  const minD = allDates[0];
  const maxD = allDates[allDates.length - 1];

  const startEl = $("#date-start");
  const endEl = $("#date-end");
  startEl.min = endEl.min = minD;
  startEl.max = endEl.max = maxD;
  startEl.value = allDates[Math.max(0, allDates.length - 10)];
  endEl.value = maxD;

  $$('.sc-chip-btn').forEach(btn => {
    btn.onclick = () => {
      $$('.sc-chip-btn').forEach(b => b.classList.remove("sc-chip-btn--active"));
      btn.classList.add("sc-chip-btn--active");
      applyPreset(data, btn.dataset.preset, allDates);
    };
  });

  $("#date-apply").onclick = () => {
    $$('.sc-chip-btn').forEach(b => b.classList.remove("sc-chip-btn--active"));
    applyRange(data, startEl.value, endEl.value, allDates);
  };
  [startEl, endEl].forEach(el => {
    el.onchange = () => {
      $$('.sc-chip-btn').forEach(b => b.classList.remove("sc-chip-btn--active"));
    };
    el.onkeydown = (e) => {
      if (e.key === "Enter") $("#date-apply").click();
    };
  });
  $("#sc-pager-prev").onclick = () => goPage(data, -1);
  $("#sc-pager-next").onclick = () => goPage(data, +1);

  applyPreset(data, "10", allDates);
}

function goPage(data, delta) {
  if (!_scState) return;
  const totalPages = Math.max(1, Math.ceil(_scState.dates.length / PAGE_SIZE));
  _scState.page = Math.min(totalPages - 1, Math.max(0, _scState.page + delta));
  renderSCDaysVisible(data);
}

function applyPreset(data, preset, allDates) {
  const startEl = $("#date-start"), endEl = $("#date-end");
  let dates;
  if (preset === "all") dates = allDates.slice();
  else dates = allDates.slice(-parseInt(preset, 10));
  startEl.value = dates[0];
  endEl.value = dates[dates.length - 1];
  renderDateRange(data, dates);
}

function applyRange(data, startD, endD, allDates) {
  if (!startD || !endD) return;
  const snap = (d, dir) => {
    if (allDates.includes(d)) return d;
    if (dir === "down") {
      for (let i = allDates.length - 1; i >= 0; i--) if (allDates[i] <= d) return allDates[i];
      return allDates[0];
    } else {
      for (let i = 0; i < allDates.length; i++) if (allDates[i] >= d) return allDates[i];
      return allDates[allDates.length - 1];
    }
  };
  const s = snap(startD, "up");
  const e = snap(endD, "down");
  if (s > e) { renderDateRange(data, []); return; }
  const dates = allDates.filter(d => d >= s && d <= e);
  $("#date-start").value = s;
  $("#date-end").value = e;
  renderDateRange(data, dates);
}

function renderDateRange(data, dates) {
  const sorted = dates.slice().sort().reverse();
  _scState = { dates: sorted, page: 0 };

  const titleEl = $("#sc-detail-title");
  const counterEl = $("#sc-counter");
  if (sorted.length === 0) {
    titleEl.textContent = t("score.noData");
    counterEl.innerHTML = "";
  } else if (sorted.length === 1) {
    titleEl.textContent = t("score.dailyReview", { date: sorted[0] });
    counterEl.innerHTML = "";
  } else {
    titleEl.textContent = `${sorted[sorted.length - 1]} → ${sorted[0]}`;
    const stats = aggregateRange(data, sorted);
    const avgHtml = `<em class="${stats.avg_excess >= 0 ? 'gain' : 'loss'}">${fmtPct(stats.avg_excess, 2)}</em>`;
    counterEl.innerHTML = t("score.counter", { days: sorted.length, avgHtml, winDays: stats.win_days });
  }
  renderSCDaysVisible(data);
}

function aggregateRange(data, dates) {
  let totEx = 0, winDays = 0, n = 0;
  dates.forEach(d => {
    const day = data.scorecard.by_date[d];
    if (!day || day.excess == null) return;
    totEx += day.excess; n++;
    if (day.excess > 0) winDays++;
  });
  return { avg_excess: n ? totEx / n : 0, win_days: winDays };
}

function renderSCDaysVisible(data) {
  const host = $("#sc-days-list");
  const pager = $("#sc-pager");
  if (!_scState) return;
  const totalPages = Math.max(1, Math.ceil(_scState.dates.length / PAGE_SIZE));
  if (_scState.page >= totalPages) _scState.page = totalPages - 1;
  const start = _scState.page * PAGE_SIZE;
  const dates = _scState.dates.slice(start, start + PAGE_SIZE);

  host.innerHTML = dates.map((d, idx) => {
    const day = data.scorecard.by_date[d];
    if (!day) return "";

    const top30Btn = day.top30?.length
      ? `<button class="sc-day__top30-btn" data-sc-top30="${d}" title="${t("score.top30Title")}">Top 30 ↗</button>`
      : "";

    // —— Pending：未结算（picks 存在但实际涨幅未知）——
    if (day.pending) {
      const picksHtml = day.picks.map(p => `
        <span class="sc-chip sc-chip--pending">
          <span class="sc-chip__n">${p.name}</span>
          <span class="sc-chip__r" style="color:var(--ink-mute)">+${p.score.toFixed(2)}</span>
        </span>
      `).join("");
      return `
        <div class="sc-day sc-day--pending" style="animation: fade-up 0.4s ${0.03 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
          <div class="sc-day__date">
            <div class="sc-day__d-main">${day.d}</div>
            <div class="sc-day__d-sub">${t("score.buySell", { buy: shortTradeDate(day.buy_d), sell: shortTradeDate(day.sell_d) })}</div>
            ${top30Btn}
          </div>
          <div class="sc-day__chips">${picksHtml}</div>
          <div class="sc-day__summary">
            <div class="sc-day__sum-pending">${t("score.pending")}</div>
            <div class="sc-day__sum-vs">${t("score.waitOpenSell", { sell: shortTradeDate(day.sell_d, t("score.nextTradeDay")) })}</div>
          </div>
        </div>
      `;
    }

    // —— 已结算 ——
    // 着色约定：单只股票实际涨幅 > 0 = 红，< 0 = 绿（A 股习惯）
    const picksHtml = day.picks.map(p => {
      if (p.ret == null) return "";
      const cls = p.ret >= 0 ? "gain" : "loss";
      return `<span class="sc-chip ${cls}">
        <span class="sc-chip__n">${p.name}</span>
        <span class="sc-chip__r ${cls}">${fmtPct(p.ret, 1)}</span>
      </span>`;
    }).join("");

    const cls = day.avg_ret >= 0 ? "gain" : "loss";
    const excessCls = (day.excess || 0) >= 0 ? "gain" : "loss";

    return `
      <div class="sc-day" style="animation: fade-up 0.4s ${0.03 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
        <div class="sc-day__date">
          <div class="sc-day__d-main">${day.d}</div>
          <div class="sc-day__d-sub">${t("score.buySell", { buy: day.buy_d.slice(5), sell: day.sell_d.slice(5) })}</div>
          ${top30Btn}
        </div>
        <div class="sc-day__chips">${picksHtml}</div>
        <div class="sc-day__summary">
          <div class="sc-day__sum-r ${cls}">${fmtPct(day.avg_ret, 2)}</div>
          <div class="sc-day__sum-vs">${t("score.vsBenchmark")} <em class="${excessCls}">${fmtPct(day.excess || 0, 2)}</em></div>
          <div class="sc-day__sum-vs">${t("score.hit")} <em>${day.hits}/${day.n}</em></div>
        </div>
      </div>
    `;
  }).join("");

  host.onclick = (e) => {
    const btn = e.target.closest("[data-sc-top30]");
    if (!btn) return;
    openTop30Modal(data, btn.dataset.scTop30);
  };

  // pager visibility + state
  if (totalPages > 1) {
    pager.hidden = false;
    $("#sc-pager-info").innerHTML = t("score.pager", { page: _scState.page + 1, totalPages, days: _scState.dates.length });
    $("#sc-pager-prev").disabled = _scState.page === 0;
    $("#sc-pager-next").disabled = _scState.page >= totalPages - 1;
  } else {
    pager.hidden = true;
  }
}

/* ─── Top 30 模型原始预测 Modal ─── */
function ensureTop30Modal() {
  let modal = document.getElementById("top30-modal");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.id = "top30-modal";
  modal.className = "t30-modal";
  modal.hidden = true;
  modal.innerHTML = `
    <div class="t30-backdrop" data-t30-close></div>
    <div class="t30-panel" role="dialog" aria-modal="true">
      <header class="t30-head">
        <div>
          <div class="t30-title"></div>
          <div class="t30-sub"></div>
        </div>
        <button class="t30-close" data-t30-close aria-label="${t("score.close")}">×</button>
      </header>
      <div class="t30-body"></div>
    </div>
  `;
  document.body.appendChild(modal);
  modal.addEventListener("click", (e) => {
    if (e.target.closest("[data-t30-close]")) closeTop30Modal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeTop30Modal();
  });
  return modal;
}

function closeTop30Modal() {
  const modal = document.getElementById("top30-modal");
  if (modal) modal.hidden = true;
  document.body.style.overflow = "";
}

function shortTradeDate(dateIso, fallback = "—") {
  return dateIso ? dateIso.slice(5) : fallback;
}

function openTop30Modal(data, dateIso) {
  const day = data.scorecard.by_date[dateIso];
  if (!day || !day.top30) return;
  const modal = ensureTop30Modal();
  const realized = !day.pending && day.top30.some(t => t.ret != null);

  modal.querySelector(".t30-title").innerHTML =
    t("score.modalTitle", { date: day.d });
  modal.querySelector(".t30-sub").innerHTML = `
    ${t("score.buySell", { buy: shortTradeDate(day.buy_d), sell: shortTradeDate(day.sell_d) })} ·
    ${day.pending ? `<span class="t30-pending">${t("score.modalPending")}</span>` :
      t("score.modalRealized", { hits: day.hits, n: day.n, avgHtml: `<em class="${day.avg_ret>=0?'gain':'loss'}">${fmtPct(day.avg_ret,2)}</em>` })}
  `;

  // build table
  let inSel = 0;
  const rowsHtml = day.top30.map(item => {
    if (item.in_portfolio) inSel++;
    const retCls = item.ret == null ? "" : item.ret >= 0 ? "gain" : "loss";
    const retTxt = item.ret == null ? '<span class="t30-pending">—</span>' : fmtPct(item.ret, 2);
    const selBadge = item.in_portfolio
      ? `<span class="t30-badge t30-badge--in" title="${t("score.selectedTitle")}">${t("score.selectedBadge")}</span>`
      : `<span class="t30-badge t30-badge--out" title="${t("score.outTitle")}">${t("score.outBadge")}</span>`;
    return `
      <tr class="${item.in_portfolio ? 't30-row--in' : ''}">
        <td class="t30-rk">${item.rank}</td>
        <td class="t30-ts mono">${item.ts}</td>
        <td class="t30-name">${item.name}</td>
        <td class="t30-ind">${item.ind}</td>
        <td class="t30-score mono">+${item.score.toFixed(3)}</td>
        <td class="t30-ret mono ${retCls}">${retTxt}</td>
        <td class="t30-sel">${selBadge}</td>
      </tr>
    `;
  }).join("");

  modal.querySelector(".t30-body").innerHTML = `
    <div class="t30-stats">
      <span>${t("score.rawCount")}</span>
      <span class="t30-sep">·</span>
      <span>${t("score.selectedCount", { count: inSel })}</span>
      <span class="t30-sep">·</span>
      <span>${realized ? t("score.realizedState") : t("score.pendingState")}</span>
    </div>
    <div class="t30-table-wrap">
      <table class="t30-table">
        <thead>
          <tr>
            <th class="t30-rk">#</th>
            <th>${t("score.thCode")}</th>
            <th>${t("score.thName")}</th>
            <th>${t("score.thIndustry")}</th>
            <th>${t("score.thScore")}</th>
            <th>${t("score.thReturn")}</th>
            <th class="t30-sel">${t("score.thStrategy")}</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;

  modal.hidden = false;
  document.body.style.overflow = "hidden";
}
