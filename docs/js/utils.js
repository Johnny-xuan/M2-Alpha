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

/** 从给定日期算下一个交易日（仅跳过周末，未处理节假日）。
 *  dateStr: "YYYY-MM-DD" → returns "YYYY-MM-DD" */
export function nextTradingDay(dateStr) {
  if (!dateStr || dateStr === "—") return "—";
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return "—";
  do { d.setDate(d.getDate() + 1); }
  while (d.getDay() === 0 || d.getDay() === 6);   // skip Sun(0), Sat(6)
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}
