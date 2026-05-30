/* ────────────────────────────────────────────────────────────
   holdings.js — industry distribution + most-held tickers
   ──────────────────────────────────────────────────────────── */
import { $ } from "./utils.js";

export function renderHoldingsPanel(data) {
  const ind = data.industry_avg.slice(0, 10);
  const maxW = Math.max(...ind.map(i => i.weight));

  $("#industry-bars").innerHTML = ind.map((i, idx) => {
    const w = (i.weight / maxW) * 100;
    return `
      <div class="ib-row" style="animation: fade-up 0.45s ${0.03 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
        <div class="ib-row__name">${i.industry}</div>
        <div class="ib-row__bar"><i style="width: ${w}%"></i></div>
        <div class="ib-row__v">${i.weight.toFixed(1)}%</div>
      </div>
    `;
  }).join("");

  const held = data.top_held.slice(0, 12);
  $("#top-held").innerHTML = held.map((h, idx) => `
    <li class="th-row" style="animation: fade-up 0.45s ${0.025 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
      <div class="th-row__rk">${String(idx + 1).padStart(2, "0")}</div>
      <div class="th-row__name">
        <div class="th-row__n">${h.name}</div>
        <div class="th-row__c">${h.ts} <em>· ${h.industry}</em></div>
      </div>
      <div class="th-row__pct">${h.pct}%<span class="pct-sub">·${h.days}天</span></div>
    </li>
  `).join("");
}
