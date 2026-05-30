/* ────────────────────────────────────────────────────────────
   scorecard.js — Section 02
     · summary stats wiring (via data-count-to in HTML)
     · 60-day excess bar chart
     · date range picker + chips + recent days list
   ──────────────────────────────────────────────────────────── */
import { $, $$, svg, fmtPct } from "./utils.js";

let _scState = null;     // { dates: [...], visible: N }

/* ─── populate scorecard sub-header stats (best day) ─── */
export function renderScorecardSummary(data) {
  const sc = data.scorecard?.summary;
  if (!sc) return;
  $("#sc-days").textContent = sc.n_days_total;
  $("#sc-best").textContent = fmtPct(sc.best_day.ret);
  $("#sc-best-d").textContent = sc.best_day.d;
}

/* ─── 60-day excess bar chart ─── */
export function renderExcessChart(data) {
  const svgEl = $("#excess-chart");
  if (!svgEl) return;
  const all = data.scorecard.all_dates;
  const series = all.slice(-60);

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
      fill: v >= 0 ? "#c8f93d" : "#ff6b3c",
    });
    rect.style.opacity = "0";
    rect.style.animation = `fade-up 0.4s ${0.005 * i}s forwards cubic-bezier(0.22, 0.61, 0.36, 1)`;
    if (v >= 0) rect.setAttribute("filter", "drop-shadow(0 0 3px rgba(200, 249, 61, 0.4))");
    svgEl.appendChild(rect);
  });
}

/* ─── date range picker ─── */
export function initDateRange(data) {
  const allDates = Object.keys(data.scorecard.by_date).sort();
  const minD = allDates[0];
  const maxD = allDates[allDates.length - 1];

  const startEl = $("#date-start");
  const endEl = $("#date-end");
  startEl.min = endEl.min = minD;
  startEl.max = endEl.max = maxD;
  startEl.value = allDates[Math.max(0, allDates.length - 10)];
  endEl.value = maxD;

  $$('.sc-chip-btn').forEach(btn => {
    btn.addEventListener("click", () => {
      $$('.sc-chip-btn').forEach(b => b.classList.remove("sc-chip-btn--active"));
      btn.classList.add("sc-chip-btn--active");
      applyPreset(data, btn.dataset.preset, allDates);
    });
  });

  $("#date-apply").addEventListener("click", () => {
    $$('.sc-chip-btn').forEach(b => b.classList.remove("sc-chip-btn--active"));
    applyRange(data, startEl.value, endEl.value, allDates);
  });
  [startEl, endEl].forEach(el => {
    el.addEventListener("change", () => {
      $$('.sc-chip-btn').forEach(b => b.classList.remove("sc-chip-btn--active"));
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") $("#date-apply").click();
    });
  });
  $("#sc-loadmore-btn").addEventListener("click", () => loadMore(data));

  applyPreset(data, "10", allDates);
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
  _scState = { dates: sorted, visible: Math.min(10, sorted.length) };

  const titleEl = $("#sc-detail-title");
  const counterEl = $("#sc-counter");
  if (sorted.length === 0) {
    titleEl.textContent = "无 数 据";
    counterEl.innerHTML = "";
  } else if (sorted.length === 1) {
    titleEl.textContent = `${sorted[0]} · 当 日 复 盘`;
    counterEl.innerHTML = "";
  } else {
    titleEl.textContent = `${sorted[sorted.length - 1]} → ${sorted[0]}`;
    const stats = aggregateRange(data, sorted);
    counterEl.innerHTML = `
      共 <em>${sorted.length}</em> 天 · 平 均 超 额
      <em class="${stats.avg_excess >= 0 ? 'gain' : 'loss'}">${fmtPct(stats.avg_excess, 2)}</em>
      · 跑 赢 <em>${stats.win_days}</em>/<em>${sorted.length}</em>
    `;
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
  const lm = $("#sc-loadmore");
  if (!_scState) return;
  const dates = _scState.dates.slice(0, _scState.visible);

  host.innerHTML = dates.map((d, idx) => {
    const day = data.scorecard.by_date[d];
    if (!day) return "";
    const picksHtml = day.picks.map(p => {
      if (p.ret == null) return "";
      const cls = (day.bench_ret != null && p.ret > day.bench_ret) ? "gain" : "loss";
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
          <div class="sc-day__d-sub">买 ${day.buy_d.slice(5)} → 卖 ${day.sell_d.slice(5)}</div>
        </div>
        <div class="sc-day__chips">${picksHtml}</div>
        <div class="sc-day__summary">
          <div class="sc-day__sum-r ${cls}">${fmtPct(day.avg_ret, 2)}</div>
          <div class="sc-day__sum-vs">vs 沪深300 <em class="${excessCls}">${fmtPct(day.excess || 0, 2)}</em></div>
          <div class="sc-day__sum-vs">命中 <em>${day.hits}/${day.n}</em></div>
        </div>
      </div>
    `;
  }).join("");

  if (_scState.visible < _scState.dates.length) {
    lm.hidden = false;
    $("#sc-loadmore-btn").textContent = `显 示 更 多 (剩 ${_scState.dates.length - _scState.visible} 天) →`;
  } else {
    lm.hidden = true;
  }
}

function loadMore(data) {
  if (!_scState) return;
  _scState.visible = Math.min(_scState.dates.length, _scState.visible + 20);
  renderSCDaysVisible(data);
}
