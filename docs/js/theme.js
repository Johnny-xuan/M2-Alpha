/* ────────────────────────────────────────────────────────────
   theme.js — dark / light toggle, persisted in localStorage
   ──────────────────────────────────────────────────────────── */
import { $ } from "./utils.js";

const KEY = "m2alpha-theme";

function apply(theme) {
  document.body.classList.toggle("light", theme === "light");
  document.documentElement.classList.remove("preload-light");
  const btn = $("#theme-toggle");
  if (btn) {
    btn.querySelector(".theme-toggle__icon").textContent = theme === "light" ? "☀" : "☾";
    btn.title = theme === "light" ? "切换到暗色" : "切换到亮色";
  }
}

export function initTheme() {
  let theme;
  try {
    theme = localStorage.getItem(KEY);
  } catch (e) { theme = null; }
  if (!theme) {
    theme = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  apply(theme);

  const btn = $("#theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const next = document.body.classList.contains("light") ? "dark" : "light";
    try { localStorage.setItem(KEY, next); } catch (e) {}
    apply(next);
  });
}
