/* ────────────────────────────────────────────────────────────
   navbar.js — live clock, today date, scroll-spy for tabs
   ──────────────────────────────────────────────────────────── */
import { $, $$ } from "./utils.js";

const WEEKDAYS_ZH = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

export function startNavClock() {
  const dEl = $("#nav-today");
  const tEl = $("#nav-clock");
  if (!dEl || !tEl) return;
  const upd = () => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    const wd = WEEKDAYS_ZH[now.getDay()];
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    dEl.textContent = `${y}-${m}-${d} ${wd}`;
    tEl.textContent = `${hh}:${mm}:${ss}`;
  };
  upd();
  setInterval(upd, 1000);
}

export function initNavScrollSpy() {
  const tabs = $$('.nav-tab');
  const sectionMap = {};
  tabs.forEach(t => {
    const id = t.dataset.tab;
    const el = document.getElementById(id);
    if (el) sectionMap[id] = { el, tab: t };
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        tabs.forEach(t => t.classList.toggle("nav-tab--active", t.dataset.tab === id));
      }
    });
  }, { rootMargin: "-50% 0px -40% 0px", threshold: 0 });

  Object.values(sectionMap).forEach(({ el }) => observer.observe(el));
}
