/* ────────────────────────────────────────────────────────────
   equity-chart.js — pure NAV chart renderer (range comes from outside)
   ──────────────────────────────────────────────────────────── */
import { $, svg, fmtPct } from "./utils.js";
import { t } from "./i18n.js?v=20260711-strategy-v2";

/** Draw equity chart for a given slice, or a multi-curve payload. */
export function drawEquityChart(input) {
  const svgEl = $("#equity-chart");
  if (!svgEl || !input) return;
  const tooltip = $("#equity-tooltip");

  const normalizeSeries = (series) => {
    if (Array.isArray(series)) return series;
    if (Array.isArray(series?.equity_curve)) return series.equity_curve;
    return [];
  };
  const curves = Array.isArray(input)
    ? [{ key: "model", label: "M²-Alpha", series: input }]
    : (input.curves || []);
  const visibleCurves = curves
    .map(c => ({ ...c, series: normalizeSeries(c.series || c.equity_curve).filter(Boolean) }))
    .filter(c => c.series.length >= 2);
  if (!visibleCurves.length) return;

  const W = 1400, H = 420;
  const padL = 64, padR = 24, padT = 24, padB = 40;
  const w = W - padL - padR, h = H - padT - padB;

  const primary = visibleCurves[0].series;
  const allDates = Array.from(new Set(
    visibleCurves.flatMap(c => c.series.map(d => d.d))
  )).sort();
  const dateIndex = new Map(allDates.map((d, i) => [d, i]));
  const n = allDates.length;

  const navValues = visibleCurves.flatMap(c => c.series.map(d => d.nav));
  const benches = primary.map(d => d.bench).filter(v => v != null);
  const minY = Math.min(...navValues, ...benches);
  const maxY = Math.max(...navValues, ...benches);
  const yPad = 0.04;
  const yMin = minY - (maxY - minY) * yPad;
  const yMax = maxY + (maxY - minY) * yPad;

  const xAt = (i) => padL + (i / (n - 1)) * w;
  const xAtDate = (d) => xAt(dateIndex.get(d) ?? 0);
  const yAt = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * h;

  const buildPath = (rows, valueKey = "nav") => {
    let path = "";
    rows.forEach((row, i) => {
      const cmd = i === 0 ? "M" : "L";
      path += `${cmd} ${xAtDate(row.d)} ${yAt(row[valueKey])} `;
    });
    return path.trim();
  };

  const primaryNavs = primary.map(d => d.nav);
  const benchRows = primary.filter(d => d.bench != null);
  const benchPath = buildPath(benchRows, "bench");

  let areaPath = "";
  if (primary.length >= 2) {
    areaPath = `M ${xAtDate(primary[0].d)} ${H - padB} L ${xAtDate(primary[0].d)} ${yAt(primary[0].nav)}`;
    for (let i = 1; i < primary.length; i++) areaPath += ` L ${xAtDate(primary[i].d)} ${yAt(primary[i].nav)}`;
    areaPath += ` L ${xAtDate(primary[primary.length - 1].d)} ${H - padB} Z`;
  }

  const yTicks = [];
  for (let k = 0; k <= 4; k++) {
    const v = yMin + ((yMax - yMin) * k) / 4;
    yTicks.push({ y: yAt(v), v });
  }
  const xTicks = [];
  const nTicks = Math.min(8, Math.max(3, Math.floor(n / 10)));
  for (let k = 0; k <= nTicks; k++) {
    const i = Math.round((k / nTicks) * (n - 1));
    xTicks.push({ x: xAt(i), d: allDates[i] });
  }

  let runMax = primaryNavs[0], inDD = false, ddStart = 0;
  let ddRegions = [];
  for (let i = 1; i < primaryNavs.length; i++) {
    if (primaryNavs[i] >= runMax) {
      if (inDD) { ddRegions.push([ddStart, i]); inDD = false; }
      runMax = primaryNavs[i];
    } else if (!inDD) { ddStart = i; inDD = true; }
  }
  if (inDD) ddRegions.push([ddStart, primaryNavs.length - 1]);
  ddRegions = ddRegions.filter(([a, b]) => {
    if (b - a < 5) return false;
    const peak = Math.max(...primaryNavs.slice(Math.max(0, a - 1), a + 1));
    const trough = Math.min(...primaryNavs.slice(a, b + 1));
    return (peak - trough) / peak > 0.025;
  });

  while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const gradient = svg("linearGradient", { id: "lime-gradient", x1: 0, y1: 0, x2: 0, y2: 1 });
  gradient.appendChild(svg("stop", { offset: "0%", "stop-color": "#c8f93d", "stop-opacity": "0.30" }));
  gradient.appendChild(svg("stop", { offset: "100%", "stop-color": "#c8f93d", "stop-opacity": "0" }));
  defs.appendChild(gradient);
  svgEl.appendChild(defs);

  const startNav = primary[0].nav;
  yTicks.forEach(t => {
    svgEl.appendChild(svg("line", { x1: padL, x2: W - padR, y1: t.y, y2: t.y, class: "grid-line" }));
    const lab = svg("text", { x: padL - 10, y: t.y + 3, "text-anchor": "end", class: "axis-label" });
    const pctFromStart = ((t.v / startNav) - 1) * 100;
    lab.textContent = (pctFromStart >= 0 ? "+" : "") + pctFromStart.toFixed(0) + "%";
    svgEl.appendChild(lab);
  });
  xTicks.forEach(t => {
    const lab = svg("text", { x: t.x, y: H - 14, "text-anchor": "middle", class: "axis-label" });
    lab.textContent = t.d.slice(2, 7);
    svgEl.appendChild(lab);
  });

  ddRegions.forEach(([a, b]) => {
    svgEl.appendChild(svg("rect", {
      x: xAtDate(primary[a].d),
      y: padT,
      width: xAtDate(primary[b].d) - xAtDate(primary[a].d),
      height: h,
      class: "dd-region",
    }));
  });

  svgEl.appendChild(svg("path", { d: benchPath, class: "bench-line" }));
  if (areaPath) svgEl.appendChild(svg("path", { d: areaPath, class: "model-area" }));
  const lineEls = [];
  visibleCurves.forEach((curve) => {
    const line = svg("path", {
      d: buildPath(curve.series),
      class: `model-line model-line--${curve.key}`,
    });
    svgEl.appendChild(line);
    lineEls.push(line);
  });

  requestAnimationFrame(() => {
    lineEls.forEach((line) => {
      let len = 4000;
      try {
        len = line.getTotalLength ? line.getTotalLength() : 4000;
      } catch (e) {
        len = 4000;
      }
      line.style.strokeDasharray = len;
      line.style.strokeDashoffset = len;
      line.style.transition = "stroke-dashoffset 1.2s cubic-bezier(0.22, 0.61, 0.36, 1)";
      line.style.strokeDashoffset = 0;
    });
  });

  // crosshair + tooltip
  const crossV = svg("line", { y1: padT, y2: H - padB, class: "crosshair" });
  const crossH = svg("line", { x1: padL, x2: W - padR, class: "crosshair" });
  const dot = svg("circle", { r: 4, class: "hover-dot" });
  svgEl.appendChild(crossV);
  svgEl.appendChild(crossH);
  svgEl.appendChild(dot);

  const host = svgEl.parentElement;
  function hide() {
    crossV.classList.remove("show"); crossH.classList.remove("show"); dot.classList.remove("show");
    if (tooltip) tooltip.hidden = true;
  }
  svgEl.onmousemove = (ev) => {
    const rect = svgEl.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * W;
    if (px < padL || px > W - padR) return hide();
    const ratio = (px - padL) / w;
    const idx = Math.min(n - 1, Math.max(0, Math.round(ratio * (n - 1))));
    const date = allDates[idx];
    const d = nearestRow(primary, date);
    if (!d) return hide();
    const xv = xAt(idx), yv = yAt(d.nav);

    crossV.setAttribute("x1", xv); crossV.setAttribute("x2", xv);
    crossH.setAttribute("y1", yv); crossH.setAttribute("y2", yv);
    dot.setAttribute("cx", xv); dot.setAttribute("cy", yv);
    crossV.classList.add("show"); crossH.classList.add("show"); dot.classList.add("show");

    const pctFromStart = ((d.nav / startNav) - 1) * 100;
    const benchPctFromStart = ((d.bench / primary[0].bench) - 1) * 100;
    const curveRows = visibleCurves.map(curve => {
      const row = nearestRow(curve.series, date);
      if (!row) return "";
      const pct = ((row.nav / curve.series[0].nav) - 1) * 100;
      return `<div class="tt-row"><span class="tt-k">${curve.label}</span><span class="tt-v tt-v--${curve.key} ${pct >= 0 ? "gain" : "loss"}">${fmtPct(pct)}</span></div>`;
    }).join("");
    if (!tooltip) return;
    tooltip.hidden = false;
    tooltip.innerHTML = `
      <div class="tt-d">${date}</div>
      ${curveRows}
      <div class="tt-row"><span class="tt-k">${t("chart.benchmark")}</span><span class="tt-v ${benchPctFromStart >= 0 ? "gain" : "loss"}">${fmtPct(benchPctFromStart)}</span></div>
    `;
    const hostRect = host.getBoundingClientRect();
    const tx = ev.clientX - hostRect.left + 16;
    const ty = ev.clientY - hostRect.top - 20;
    const ttRect = tooltip.getBoundingClientRect();
    const maxX = hostRect.width - ttRect.width - 8;
    tooltip.style.left = Math.min(maxX, tx) + "px";
    tooltip.style.top = ty + "px";
  };
  svgEl.onmouseleave = hide;
}

function nearestRow(rows, date) {
  if (!rows?.length) return null;
  let lo = 0, hi = rows.length - 1, best = null;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (rows[mid].d <= date) {
      best = rows[mid];
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best;
}
