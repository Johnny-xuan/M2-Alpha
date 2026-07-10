<p align="center">
  <img src="docs/favicon.svg" alt="M²-Alpha logo" width="96">
</p>

<h1 align="center">M²-Alpha</h1>

<p align="center">
  <a href="https://johnny-xuan.github.io/M2-Alpha"><b>Live site</b></a>
  ·
  <a href="https://johnny-xuan.github.io/M2-Alpha/en.html"><b>English site</b></a>
  ·
  <a href="docs/report/M2Alpha_Technical_Report.pdf"><b>Report (中文)</b></a>
  ·
  <a href="docs/report/M2Alpha_Technical_Report_EN.pdf"><b>Report (EN)</b></a>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-c8f93d.svg">
  <img alt="Models" src="https://img.shields.io/badge/Models-M--0--M%20%7C%20M--1--M%20%7C%20M--2--M-1f232c.svg">
  <img alt="Domain" src="https://img.shields.io/badge/Market-A--share-5a8f18.svg">
</p>

**M²-Alpha** is a deep-learning alpha model for daily A-share stock selection, released as a research repository: model code, three trained checkpoints, factor definitions, a reproducible benchmark, a bilingual technical report, and a static site.

The design takes after how a trader works a name — and a trader does not read the two views once and stop. Reading one stock's own path and comparing it to today's cross-section depend on each other: "down 5% last week" means one thing in a risk-on tape and another in a selloff; "expensive today" means one thing after a steady climb and another after a spike. So a trader iterates between the two views until the ranking feels grounded. The **M² Block** encodes one round of that iteration as two attention passes:

- **Micro attention** reads one stock's own recent path along the time axis.
- **Macro attention** compares that stock against the cross-section of the market on the same day.

Stack several of these blocks and the two views refine each other in depth (the public **M-1-M** uses 3, **M-2-M** uses 5). Training uses dense supervision over the whole stock-time grid; at inference the last time step is read off as a ranking score. The input is a `stocks × lookback × factors` tensor with lookback `T = 8` and `F = 35` daily factors.

On the public research benchmark — a full-factor dynamic top-1000 A-share panel, open-execution, fees included, 2025-07 → 2026-05 — the deepest released line **M-2-M (5 blocks)** reaches **+354% cumulative return, Sharpe ≈ 4**, and the compact **M-1-M (3 blocks)** reaches **+239%, Sharpe 3.4**. Basis and caveats are documented in [docs/RESULTS.md](docs/RESULTS.md).

Nothing in this repository is investment advice, and the public site is not a trading service.

## Architecture

M²-Alpha turns daily stock selection into a cross-sectional ranking problem. For each trading day it reads a tensor of shape:

```text
stocks × lookback × factors   =   S × 8 × 35
```

Each factor is computed from an individual stock's history, then robust-z-scored against the cross-section of the same trade date, so a model input always describes relative, not absolute, market state.

The backbone then repeats an **M² Block**:

1. **Micro attention** along the time axis — each stock attends to its own recent trajectory. This is where short-horizon patterns (momentum, reversal, volatility regime) get read.
2. **Macro attention** along the stock axis — each stock attends to its peers on the same date. This is where cross-sectional structure (which names are cheap/expanded/under pressure today) gets read.
3. A residual mix keeps both views available to the next block.

More blocks mean more rounds of this mutual refinement. Training uses dense supervision over the full stock-time grid so every timestep contributes signal, not just the final ranking step; at inference only the last timestep is used to rank the next-day universe.

Architecture figures, attention visualizations, and the full ablation grid (depth scaling, objective studies, strategy sweeps, baseline comparisons) are in [docs/METHOD.md](docs/METHOD.md) and the technical report.

## Data and Factors

The model reads 35 daily factors, grouped as:

- momentum returns
- moving-average deviation
- realized volatility
- candlestick shape
- volume activity
- turnover and volume ratio
- valuation
- money-flow structure

The **open/free public-data route** reconstructs these from BaoStock (stable historical base) plus AKShare and efinance (snapshot enrichment). It can recover most fields, but three families are hard to reconstruct exactly from public sources alone: **historical true volume ratio, free-float turnover, and order-size money-flow fields**. The released research curves assume a compatible full-factor panel; the open-data route is best-effort. This boundary is documented honestly in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) and [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md).

## Released Models

The public site and the checkpoints share one naming scheme:

| Name | What it is | Checkpoint |
|---|---|---|
| **M-0-M** | Stable public-baseline page line. Smooth inspectable line on the live site, not the strongest research curve. | `ml/m2alpha.pt` |
| **M-1-M** | Frozen 3-block research curve (compact Micro/Macro main line). | `ml/m2alpha-m1m.pt` |
| **M-2-M** | Frozen 5-block research curve (deeper line, main research highlight). | `ml/m2alpha-m2m.pt` |

Seed, epoch, depth, and benchmark metadata for each checkpoint live in [model_registry.yml](model_registry.yml).

## Reproduce

Install:

```bash
git clone https://github.com/Johnny-xuan/M2-Alpha.git
cd M2-Alpha
pip install -r requirements.txt
```

Smoke-test the readable training implementation (CPU, a few steps):

```bash
python scripts/train_baseline.py --smoke --out /tmp/m2alpha_smoke.pt --device cpu
```

Run the research benchmark with a compatible full-factor panel:

```bash
python scripts/benchmark_research.py \
  --panel /path/to/panel_top1000.parquet \
  --industry-file /path/to/basic.csv \
  --model all \
  --start 20250710 --end 20260521 \
  --n-hold 5 --pool-rank 100 --sell-rank 200 \
  --max-industry-frac 0.2 --exec-price open --fee-rate 0.0013
```

The benchmark uses one fixed strategy so model rankings are comparable on the same basis:

| Rule | Value |
|---|---|
| Universe | dynamic top-1000, sampled by free-float market cap when available |
| Selection | top `pool_rank=100` scores |
| Holdings | `n_hold=5`, equal weight |
| Industry cap | 20% |
| Sell rule | drop out below `sell_rank=200` |
| Execution | open price / open NAV |
| Fee | `fee_rate=0.0013` |

Preview the site locally:

```bash
python3 -m http.server 8765 --directory docs
# http://127.0.0.1:8765/        Chinese
# http://127.0.0.1:8765/en.html  English
```

The committed public cache (`build/cache/`) is enough to inspect the site and run smoke tests. It is **not** enough to reproduce the multi-year research training run — full reproduction needs a compatible historical A-share factor panel matching [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md). Tiered reproduction instructions are in [docs/REPRODUCTION.md](docs/REPRODUCTION.md).

### Reproduce with a coding agent

If you delegate reproduction to a coding agent, this prompt is self-contained and mirrors the quick-start prompt on the site:

```text
You are my coding agent. Set up and exercise the M2-Alpha repository (github.com/Johnny-xuan/M2-Alpha).

1. Clone it, then read README.md, docs/METHOD.md, docs/DATA_SOURCES.md,
   docs/REPRODUCTION.md, and model_registry.yml before changing anything.
2. Create a Python env and install requirements.txt. Do not modify the
   released checkpoints in ml/.
3. Smoke-test the training implementation on CPU:
   python scripts/train_baseline.py --smoke --out /tmp/m2alpha_smoke.pt --device cpu
4. Serve the site and confirm the backtest + about pages load:
   python3 -m http.server 8765 --directory docs
5. Three public lines — keep them distinct:
   - M-0-M: stable public-baseline page line.
   - M-1-M: 3-block research curve (ml/m2alpha-m1m.pt).
   - M-2-M: 5-block research curve (ml/m2alpha-m2m.pt).
6. Data boundary (important): the committed cache in build/cache/ only supports
   the site and smoke tests. The strong research curves assume a compatible
   full-factor dynamic top-1000 panel with all 35 factors (volume ratio,
   free-float turnover, valuation, money-flow). BaoStock + AKShare + efinance
   alone CANNOT reproduce M-1-M/M-2-M. If I did not hand you such a panel, run
   only the open-data baseline path and say so explicitly.
7. If I provide a compatible panel, run the benchmark on the unified strategy
   and report the numbers:
   n_hold=5, pool_rank=100, sell_rank=200, max_industry_frac=0.2,
   exec-price=open, fee_rate=0.0013. Entry point: scripts/benchmark_research.py.
8. Report back: commands run, data paths used, outputs, and exactly which parts
   are not reproducible from public data alone.
```

## Repository Layout

```text
M2-Alpha/
├── m2alpha/            readable Micro/Macro research model code
├── build/              data fetching, enrichment, inference, site-data utilities
├── scripts/            train / benchmark / data-audit entrypoints
├── configs/            baseline training configuration
├── ml/                 released checkpoints (m2alpha.pt, m2alpha-m1m.pt, m2alpha-m2m.pt)
├── docs/               GitHub Pages site, public docs, and LaTeX/PDF report
│   ├── index.html      Chinese site
│   ├── en.html         English site
│   ├── data/data.json  static site payload
│   └── report/         technical report (.tex + .pdf, CN + EN)
├── model_registry.yml  machine-readable model lineage
├── CITATION.cff
├── CONTRIBUTING.md
├── LICENSE             Apache 2.0
└── README.md
```

Where to read next:

- [docs/METHOD.md](docs/METHOD.md) — architecture and training method
- [docs/MODEL_CARD.md](docs/MODEL_CARD.md) — model card
- [docs/MODEL_ZOO.md](docs/MODEL_ZOO.md) — released checkpoint lineage
- [docs/RESULTS.md](docs/RESULTS.md) — benchmark and ablation results
- [docs/REPRODUCTION.md](docs/REPRODUCTION.md) — reproduction tiers
- [docs/BENCHMARK_AUDIT.md](docs/BENCHMARK_AUDIT.md) — benchmark integrity audit
- [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md) / [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — panel schema and data-source policy
- [docs/MAINTAINING.md](docs/MAINTAINING.md) — maintainer workflow

## Limits

- Full-factor reproduction needs an external A-share panel that is not bundled here; the public cache only supports inspection and smoke tests.
- Public data sources (BaoStock, AKShare, efinance, Eastmoney) can change, fail, or carry redistribution limits, and some factor families are only approximately recoverable.
- The open-data baseline page and the full-factor research curves answer different questions — do not compare them without naming the data and strategy basis.
- All numbers are historical simulations. They are not future guarantees and not investment advice.

## License

[Apache License 2.0](LICENSE). Commercial use is allowed under the license terms.
