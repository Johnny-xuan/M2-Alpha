/* ────────────────────────────────────────────────────────────
   utils.js — shared DOM helpers + number formatters
   ──────────────────────────────────────────────────────────── */

export const $  = (sel, el = document) => el.querySelector(sel);
export const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

export const fmtPct = (x, d = 2) => (x > 0 ? "+" : "") + x.toFixed(d) + "%";
export const fmtNum = (x, d = 2) =>
  x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtInt = (x) => x.toLocaleString("en-US");

export const SVG_NS = "http://www.w3.org/2000/svg";

/** create SVG element with attrs */
export function svg(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}
