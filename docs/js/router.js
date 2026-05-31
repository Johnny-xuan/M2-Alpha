/* ────────────────────────────────────────────────────────────
   router.js — tab switching + URL hash sync
   ──────────────────────────────────────────────────────────── */
import { $, $$ } from "./utils.js";

const VALID = new Set(["picks", "scorecard", "backtest", "about"]);
const DEFAULT_TAB = "picks";

let _onChange = null;

export function initRouter(onTabChange) {
  _onChange = onTabChange;

  // wire all [data-tab-link] anchors to switch via JS (no scroll-anchor jump)
  document.body.addEventListener("click", (e) => {
    const link = e.target.closest("[data-tab-link]");
    if (!link) return;
    const tab = link.dataset.tabLink;
    if (!VALID.has(tab)) return;
    e.preventDefault();
    setTab(tab);
  });

  // initial: read hash
  window.addEventListener("hashchange", () => {
    const t = hashToTab(location.hash);
    show(t);
  });

  const initial = hashToTab(location.hash);
  show(initial);
}

export function setTab(tab) {
  if (!VALID.has(tab)) tab = DEFAULT_TAB;
  if (location.hash !== `#${tab}`) {
    location.hash = `#${tab}`;
  } else {
    show(tab);
  }
}

function hashToTab(hash) {
  const t = (hash || "").replace(/^#/, "");
  return VALID.has(t) ? t : DEFAULT_TAB;
}

function show(tab) {
  // toggle panels
  $$('.tab-panel').forEach(p => {
    p.hidden = p.dataset.tabPanel !== tab;
  });
  // nav active state
  $$('.nav-tab').forEach(t => {
    t.classList.toggle("nav-tab--active", t.dataset.tabLink === tab);
  });
  // notify (for charts that need to re-render after un-hide)
  if (_onChange) _onChange(tab);
  // scroll to top of tab area
  window.scrollTo({ top: 0, behavior: "instant" });
}
