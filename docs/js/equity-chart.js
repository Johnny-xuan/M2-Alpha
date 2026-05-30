/* ────────────────────────────────────────────────────────────
   equity-chart.js — NAV curve vs benchmark, with crosshair tooltip
   ──────────────────────────────────────────────────────────── */
import { $, svg, fmtPct, fmtInt } from "./utils.js";

export function renderEquityChart(data) {
  const svgEl = $("#equity-chart");
  if (!svgEl) return;
  const tooltip = $("#equity-tooltip");
  const series = data.equity_curve;

  const W = 1400, H = 420;
  const padL = 64, padR = 24, padT = 24, padB = 40;
  const w = W - padL - padR, h = H - padT - padB;
  const n = series.length;

  const navs = series.map(d => d.nav);
  const benches = series.map(d => d.bench);
  const minY = Math.min(...navs, ...benches);
  const maxY = Math.max(...navs, ...benches);
  const yPad = 0.04;
  const yMin = minY - (maxY - minY) * yPad;
  const yMax = maxY + (maxY - minY) * yPad;

  const xAt = (i) => padL + (i / (n - 1)) * w;
  const yAt = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * h;

  let modelPath = `M ${xAt(0)} ${yAt(navs[0])}`;
  let benchPath = `M ${xAt(0)} ${yAt(benches[0])}`;
  for (let i = 1; i < n; i++) {
    modelPath += ` L ${xAt(i)} ${yAt(navs[i])}`;
    benchPath += ` L ${xAt(i)} ${yAt(benches[i])}`;
  }
  let areaPath = `M ${xAt(0)} ${H - padB} L ${xAt(0)} ${yAt(navs[0])}`;
  for (let i = 1; i < n; i++) areaPath += ` L ${xAt(i)} ${yAt(navs[i])}`;
  areaPath += ` L ${xAt(n - 1)} ${H - padB} Z`;

  // ticks
  const yTicks = [];
  for (let k = 0; k <= 4; k++) {
    const v = yMin + ((yMax - yMin) * k) / 4;
    yTicks.push({ y: yAt(v), v });
  }
  const xTicks = [];
  const nTicks = 8;
  for (let k = 0; k <= nTicks; k++) {
    const i = Math.round((k / nTicks) * (n - 1));
    xTicks.push({ x: xAt(i), d: series[i].d });
  }

  // drawdown regions
  let runMax = navs[0], inDD = false, ddStart = 0;
  let ddRegions = [];
  for (let i = 1; i < n; i++) {
    if (navs[i] >= runMax) {
      if (inDD) { ddRegions.push([ddStart, i]); inDD = false; }
      runMax = navs[i];
    } else if (!inDD) { ddStart = i; inDD = true; }
  }
  if (inDD) ddRegions.push([ddStart, n - 1]);
  ddRegions = ddRegions.filter(([a, b]) => {
    if (b - a < 8) return false;
    const peak = Math.max(...navs.slice(Math.max(0, a - 1), a + 1));
    const trough = Math.min(...navs.slice(a, b + 1));
    return (peak - trough) / peak > 0.03;
  });

  svgEl.innerHTML = "";
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <linearGradient id="lime-gradient" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#c8f93d" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="#c8f93d" stop-opacity="0"/>
    </linearGradient>
  `;
  svgEl.appendChild(defs);

  // y-axis: percent change from start
  const startNav = navs[0];
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

  // drawdown regions
  ddRegions.forEach(([a, b]) => {
    svgEl.appendChild(svg("rect", {
      x: xAt(a), y: padT, width: xAt(b) - xAt(a), height: h, class: "dd-region",
    }));
  });

  // benchmark, then model area + line
  svgEl.appendChild(svg("path", { d: benchPath, class: "bench-line" }));
  svgEl.appendChild(svg("path", { d: areaPath, class: "model-area" }));
  const modelEl = svg("path", { d: modelPath, class: "model-line" });
  svgEl.appendChild(modelEl);

  // animate stroke draw-in
  const len = modelEl.getTotalLength ? modelEl.getTotalLength() : 4000;
  modelEl.style.strokeDasharray = len;
  modelEl.style.strokeDashoffset = len;
  requestAnimationFrame(() => {
    modelEl.style.transition = "stroke-dashoffset 1.8s cubic-bezier(0.22, 0.61, 0.36, 1)";
    modelEl.style.strokeDashoffset = 0;
  });

  // crosshair + tooltip
  const crossV = svg("line", { y1: padT, y2: H - padB, class: "crosshair" });
  const crossH = svg("line", { x1: padL, x2: W - padR, class: "crosshair" });
  const dot = svg("circle", { r: 4, class: "hover-dot" });
  svgEl.appendChild(crossV);
  svgEl.appendChild(crossH);
  svgEl.appendChild(dot);

  const host = svgEl.parentElement;
  svgEl.addEventListener("mousemove", (ev) => {
    const rect = svgEl.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * W;
    if (px < padL || px > W - padR) return hide();
    const ratio = (px - padL) / w;
    const idx = Math.min(n - 1, Math.max(0, Math.round(ratio * (n - 1))));
    const d = series[idx];
    const xv = xAt(idx), yv = yAt(d.nav);

    crossV.setAttribute("x1", xv); crossV.setAttribute("x2", xv);
    crossH.setAttribute("y1", yv); crossH.setAttribute("y2", yv);
    dot.setAttribute("cx", xv); dot.setAttribute("cy", yv);
    crossV.classList.add("show"); crossH.classList.add("show"); dot.classList.add("show");

    tooltip.hidden = false;
    tooltip.innerHTML = `
      <div class="tt-d">${d.d}</div>
      <div class="tt-row"><span class="tt-k">净 值</span><span class="tt-v">¥${fmtInt(Math.round(d.nav))}</span></div>
      <div class="tt-row"><span class="tt-k">模型涨幅</span><span class="tt-v ${d.ret >= 0 ? "gain" : "loss"}">${fmtPct(d.ret)}</span></div>
      <div class="tt-row"><span class="tt-k">沪深 300</span><span class="tt-v ${d.bret >= 0 ? "gain" : "loss"}">${fmtPct(d.bret)}</span></div>
      <div class="tt-row"><span class="tt-k">超额收益</span><span class="tt-v ${(d.ret - d.bret) >= 0 ? "gain" : "loss"}">${fmtPct(d.ret - d.bret)}</span></div>
    `;
    const hostRect = host.getBoundingClientRect();
    const tx = ev.clientX - hostRect.left + 16;
    const ty = ev.clientY - hostRect.top - 20;
    const ttRect = tooltip.getBoundingClientRect();
    const maxX = hostRect.width - ttRect.width - 8;
    tooltip.style.left = Math.min(maxX, tx) + "px";
    tooltip.style.top = ty + "px";
  });

  function hide() {
    crossV.classList.remove("show"); crossH.classList.remove("show"); dot.classList.remove("show");
    tooltip.hidden = true;
  }
  svgEl.addEventListener("mouseleave", hide);
}
