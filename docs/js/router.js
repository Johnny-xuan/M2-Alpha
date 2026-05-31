/* ────────────────────────────────────────────────────────────
   router.js — tab switching + URL hash sync + deep-link 锚点支持

   合法 hash:
     #picks  #scorecard  #backtest  #about
     #about-overview  #about-model  #about-features ...
     (about tab 子区 hash: 切到 about + 滚到对应 section id)
   ──────────────────────────────────────────────────────────── */
import { $, $$ } from "./utils.js";

const VALID = new Set(["picks", "scorecard", "backtest", "about"]);
const DEFAULT_TAB = "picks";

let _onChange = null;

export function initRouter(onTabChange) {
  _onChange = onTabChange;

  document.body.addEventListener("click", (e) => {
    const link = e.target.closest("[data-tab-link]");
    if (!link) return;
    const tab = link.dataset.tabLink;
    if (!VALID.has(tab)) return;
    e.preventDefault();
    const href = link.getAttribute("href") || `#${tab}`;
    // 允许 data-tab-link 带子锚点: href="#about-strategy"
    setHash(href.replace(/^#/, ""));
  });

  window.addEventListener("hashchange", () => applyHash(location.hash));
  applyHash(location.hash);
}

export function setTab(tab) {
  setHash(VALID.has(tab) ? tab : DEFAULT_TAB);
}

function setHash(h) {
  const full = `#${h}`;
  if (location.hash !== full) location.hash = full;
  else applyHash(full);
}

function applyHash(hash) {
  const raw = (hash || "").replace(/^#/, "");
  const [tab, ...rest] = raw.split("-");
  const validTab = VALID.has(tab) ? tab : DEFAULT_TAB;
  const sectionId = rest.length ? raw : null;     // e.g. "about-strategy"
  show(validTab, sectionId);
}

function show(tab, sectionId) {
  $$('.tab-panel').forEach(p => {
    p.hidden = p.dataset.tabPanel !== tab;
  });
  $$('.nav-tab').forEach(t => {
    t.classList.toggle("nav-tab--active", t.dataset.tabLink === tab);
  });
  if (_onChange) _onChange(tab);

  // 滚动：有 sectionId 就滚到那个元素，否则回到顶部
  if (sectionId) {
    const el = document.getElementById(sectionId);
    if (el) {
      // 让 panel 切换 + 内容渲染先完成
      requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }));
      return;
    }
  }
  window.scrollTo({ top: 0, behavior: "instant" });
}
