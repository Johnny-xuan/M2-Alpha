/* ────────────────────────────────────────────────────────────
   hero.js — featured Top-3 cards + count-up animation
   ──────────────────────────────────────────────────────────── */
import { $, $$ } from "./utils.js";

export function renderFeatured(data) {
  const top3 = data.current_holdings.slice(0, 3);
  $("#featured-cards").innerHTML = top3.map((p, idx) => `
    <a class="fcard" href="#picks" style="animation: fade-up 0.55s ${0.35 + 0.07 * idx}s backwards cubic-bezier(0.22, 0.61, 0.36, 1)">
      <div class="fcard__rk">0${idx + 1}</div>
      <div class="fcard__body">
        <div class="fcard__name">${p.name}</div>
        <div class="fcard__meta">${p.ts} · <em>${p.industry}</em></div>
      </div>
      <div class="fcard__score">+${p.score.toFixed(2)}</div>
    </a>
  `).join("");
}

/** animate every element with data-count-to from 0 to target */
export function startCountUps() {
  const els = $$('[data-count-to]');
  const dur = 1400;
  const start = performance.now();
  const ease = t => 1 - Math.pow(1 - t, 3);

  function tick(now) {
    const k = Math.min(1, (now - start) / dur);
    const e = ease(k);
    els.forEach(el => {
      const to = parseFloat(el.dataset.countTo);
      const v = to * e;
      const suffix = el.dataset.suffix || "";
      const decimals = (suffix === "x" || Math.abs(to) < 10) ? 2 : 2;
      let prefix = "";
      if (el.dataset.prefix) prefix = el.dataset.prefix;
      else if (to > 0 && (suffix === "%" || suffix === "pp")) prefix = "+";
      el.textContent = prefix + v.toFixed(decimals) + suffix;
    });
    if (k < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
