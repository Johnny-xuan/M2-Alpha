# Repository Contract

This document defines the public scope of M2-Alpha: what belongs in the repository, how metrics should be labeled, and what reproduction promises are supported.

## Identity

M2-Alpha is a research-to-public repository for an A-share deep-learning alpha model:

- research: expose model design, training method, benchmark code, results, and limitations;
- public: provide readable code, released weights, documentation, and a GitHub Pages presentation site with a trading-day refreshed M-0-M baseline;
- reproducibility: make benchmark results reproducible when users provide a compatible full-factor A-share panel.

The repository is not a stock recommendation service, not an investment product, and not a raw export of the local development workspace.

## Public Surfaces

The repository contains these public surfaces:

- `README.md`: concise project entry point.
- `docs/index.html`: Chinese public site.
- `docs/en.html`: English public site.
- `docs/data/data.json`: site data payload for the refreshed public baseline and frozen research curves.
- `docs/report/`: PDF and LaTeX technical report.
- `docs/*.md`: public method, model, data, result, reproduction, and maintenance docs.
- `docs/RELEASE_MANIFEST.md`: public release-scope checklist.
- `m2alpha/`: readable Micro/Macro research implementation.
- `build/`: data, inference, enrichment, and site-data utilities.
- `scripts/`: stable training, benchmark, and audit entrypoints.
- `ml/`: released model assets needed for the documented public/research paths.
- `model_registry.yml`: machine-readable lineage and public role registry.

Local planning notes, experiment inventories, raw checkpoint pools, and unpublished development files should stay outside the public release.

## Public Model Policy

The website-facing lines are:

- `M-0-M`: current public baseline, refreshed only after a validated A-share trading session.
- `M-1-M`: historical 3-block full-factor research curve.
- `M-2-M`: historical 5-block full-factor research curve and main research highlight.

Public commands, model files, website payloads, and public docs should use these names only. The 4-block depth ablation can remain in the technical report as research evidence, but it is not a shipped public model line.

## Metrics Policy

Public metrics must name their basis.

- Public baseline metrics come from `docs/data/data.json`; its M-0-M fields refresh only when the scheduled guard confirms both an A-share trading session and fresh panel data. M-0-M calls the same audited `run_research_backtest` engine with its selected Top-7/sell-35/industry-max-3 strategy on the BaoStock CSI300 panel.
- Research benchmark metrics come from `scripts/benchmark_research.py` when a compatible historical panel is supplied.
- Frozen report metrics must stay labeled as report-derived records.
- Historical research curves must not be presented as daily recommendations.

Any metric table should state, where relevant:

- model/checkpoint;
- date window;
- universe;
- data panel basis;
- transaction-cost treatment;
- execution price;
- portfolio rule;
- whether the result is frozen research evidence or public baseline display.

## Reproduction Tiers

The release supports these tiers:

1. Static-site inspection: open `docs/index.html` or `docs/en.html`.
2. Public-cache rebuild: rebuild predictions/site data from committed cache state.
3. Research benchmark reproduction: run `scripts/benchmark_research.py` on a compatible full-factor top1000 panel.
4. Training/evaluation reproduction: use `m2alpha/`, `configs/`, and `scripts/train_baseline.py` with external historical A-share data matching [DATA_SCHEMA.md](DATA_SCHEMA.md).

Full training is not one-command reproducible from bundled data because the full historical research panel cannot be committed.

## Non-Goals

- Do not publish every local experiment, log, checkpoint, or one-off script.
- Do not promise full historical training reproduction without the required data.
- Do not mix public baseline metrics and full-factor research curves without labels.
- Do not remove data caveats to make results look cleaner.
- Do not present the static site as an active trading product.

## Maintenance Gate

Any future public update should preserve the contracts above. Before publication, verify:

- README and docs agree on M-0-M/M-1-M/M-2-M public roles;
- website Chinese/English routes render and share the same data basis;
- benchmark/reproduction commands still run or have clearly documented prerequisites;
- no private data, local paths, or raw experiment clutter enters the release;
- publication is explicitly approved by the repository owner.
