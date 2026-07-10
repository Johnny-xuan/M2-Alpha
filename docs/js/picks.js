/* ────────────────────────────────────────────────────────────
   picks.js — today's Top-5 picks table
   ──────────────────────────────────────────────────────────── */
import { $ } from "./utils.js";
import { t } from "./i18n.js?v=20260709-bilingual1";

export function renderPicksTable(data) {
  const tbody = $("#picks-table tbody");
  if (!tbody) return;
  const picks = data.current_holdings || [];
  if (!picks.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="dim">${t("table.noHoldings")}</td></tr>`;
    return;
  }
  const maxScore = Math.max(...picks.map(p => Math.abs(p.score)), 1);

  tbody.innerHTML = picks.map((p, idx) => {
    const barW = Math.max(0, Math.abs(p.score) / maxScore * 100);
    return `
      <tr style="animation: fade-up 0.45s ${0.03 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
        <td class="c-rk">${String(p.rank).padStart(2, "0")}</td>
        <td class="c-code">${p.ts}</td>
        <td class="c-name">${p.name}</td>
        <td class="c-ind">${p.industry}</td>
        <td class="c-score">+${p.score.toFixed(2)}</td>
        <td class="c-bar"><div class="score-bar"><i style="width: ${barW}%"></i></div></td>
        <td class="c-px">¥${p.close.toFixed(2)}</td>
        <td class="c-w">${p.weight.toFixed(1)}%</td>
      </tr>
    `;
  }).join("");
}
