/* ────────────────────────────────────────────────────────────
   monthly.js — monthly return bars (model vs benchmark)
   ──────────────────────────────────────────────────────────── */
import { $, fmtPct } from "./utils.js";

export function renderMonthlyBars(data) {
  const host = $("#monthly-bars");
  if (!host) return;
  const months = data.monthly_returns;
  const maxAbs = Math.max(...months.flatMap(m => [Math.abs(m.model), Math.abs(m.bench)])) * 1.1;

  host.innerHTML = months.map((m, idx) => {
    const modelW = (Math.abs(m.model) / maxAbs) * 50;
    const benchW = (Math.abs(m.bench) / maxAbs) * 50;
    const modelLeft = m.model >= 0 ? 50 : 50 - modelW;
    const benchLeft = m.bench >= 0 ? 50 : 50 - benchW;

    return `
      <div class="month-row" style="animation: fade-up 0.5s ${0.05 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
        <div class="month-row__m">${m.m}</div>
        <div class="month-row__bars">
          <div class="axis" style="left: 50%"></div>
          <div class="bar bar--model ${m.model < 0 ? "neg" : ""}" style="left: ${modelLeft}%; width: ${modelW}%"></div>
          <div class="bar bar--bench ${m.bench < 0 ? "neg" : ""}" style="left: ${benchLeft}%; width: ${benchW}%"></div>
        </div>
        <div class="month-row__model ${m.model < 0 ? "neg" : ""}">${fmtPct(m.model)}</div>
        <div class="month-row__bench">${fmtPct(m.bench)}</div>
      </div>
    `;
  }).join("");
}
