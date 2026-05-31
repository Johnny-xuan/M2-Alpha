/* ────────────────────────────────────────────────────────────
   tab-picks.js — Tab 1 sidebar: mini excess chart + recent hits chips
   ──────────────────────────────────────────────────────────── */
import { $, svg, fmtPct } from "./utils.js";

/* mini 60-day excess sparkline */
export function renderMiniExcess(data) {
  const svgEl = $("#mini-excess-chart");
  if (!svgEl) return;
  const all = data.scorecard?.all_dates || [];
  const series = all.slice(-60);
  if (series.length < 2) return;

  const W = 600, H = 140;
  const padL = 8, padR = 8, padT = 8, padB = 16;
  const w = W - padL - padR, h = H - padT - padB;
  const n = series.length;

  const vals = series.map(d => d.excess || 0);
  const absMax = Math.max(...vals.map(Math.abs), 0.5) * 1.1;

  const xAt = (i) => padL + (i + 0.5) * (w / n);
  const yMid = padT + h / 2;
  const yScale = (v) => yMid - (v / absMax) * (h / 2);
  const barW = Math.max(2, w / n - 1);

  svgEl.innerHTML = "";
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svgEl.appendChild(svg("line", {
    x1: padL, x2: W - padR, y1: yMid, y2: yMid, class: "axis-zero",
  }));

  series.forEach((d, i) => {
    if (d.excess == null) return;
    const v = d.excess;
    const x = xAt(i) - barW / 2;
    const y = v >= 0 ? yScale(v) : yMid;
    const ht = Math.abs(yScale(v) - yMid);
    svgEl.appendChild(svg("rect", {
      x, y, width: barW, height: Math.max(1, ht), rx: 1,
      fill: v >= 0 ? "#c8f93d" : "#ff6b3c",
    }));
  });
}

/* 最近 7 天命中 chips list (仅显示已结算) */
export function renderRecentHits(data) {
  const host = $("#recent-hits");
  if (!host) return;
  const recent = (data.scorecard?.recent || [])
    .filter(d => !d.pending && d.avg_ret != null)
    .slice(-7).reverse();
  if (!recent.length) {
    host.innerHTML = '<div class="dim" style="font-size:12px">暂无已结算数据</div>';
    return;
  }
  host.innerHTML = recent.map(day => {
    const cls = (day.excess || 0) >= 0 ? "gain" : "loss";
    return `
      <div class="rh-row ${cls}">
        <div class="rh-row__d">${day.d.slice(5)}</div>
        <div class="rh-row__ret ${cls}">${fmtPct(day.avg_ret, 2)}</div>
        <div class="rh-row__hit">${day.hits}/${day.n}</div>
      </div>
    `;
  }).join("");
}
