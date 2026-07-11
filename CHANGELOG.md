# Changelog

## 2026-07-11 - M-0-M Trading-Day Refresh

- Restored only the M-0-M public baseline update loop on the audited
  `run_research_backtest` engine. A same-pipeline sweep selected Top 7, sell
  rank 35, and at most three names per industry for the public checkpoint.
- Added a BaoStock-backed session guard and a double post-close GitHub Actions
  schedule. Weekends, China-market holidays, calendar failures, and stale panel
  dates do not publish a new baseline payload.
- Added `preds_m0m.parquet`, the M-0-M payload merger, and an offline Golden
  Week guard test. M-1-M and M-2-M remain frozen research curves.
- Added resumable fixed-prediction strategy sweeps and registered model-specific
  portfolio rules. On the full-factor panel through 2026-06-12, M-1-M remains
  Top5/sell200/max-one-per-industry at +242.07%, while M-2-M selects
  Top5/sell50/max-three-per-industry at +443.01%, Sharpe 3.99, MaxDD -13.86%.

## 2026-07-09 - Public Research Release Candidate

This release candidate turns M2-Alpha into an open research repository with a
small public model contract, a static bilingual website, reproducible benchmark
entrypoints, and a technical report.

### Added

- Public model contract:
  - `M-0-M`: stable public baseline, backed by `ml/m2alpha.pt`;
  - `M-1-M`: released 3-block full-factor research checkpoint, backed by `ml/m2alpha-m1m.pt`;
  - `M-2-M`: released 5-block full-factor research checkpoint, backed by `ml/m2alpha-m2m.pt`.
- Public research prediction caches:
  - `build/cache/preds_m1m.parquet`;
  - `build/cache/preds_m2m.parquet`.
- Static bilingual website:
  - Chinese entry: `docs/index.html`;
  - English entry: `docs/en.html`;
  - shared data payload: `docs/data/data.json`.
- Public research implementation and reproduction utilities:
  - `m2alpha/`;
  - `configs/baseline.json`;
  - `scripts/train_baseline.py`;
  - `scripts/benchmark_research.py`;
  - `scripts/audit_data_source_fields.py`.
- Documentation set:
  - repository contract: `docs/REPOSITORY_CONTRACT.md`;
  - reproduction guide: `docs/REPRODUCTION.md`;
  - data schema and source notes;
  - model card, method note, results note, and model zoo;
  - release manifest;
  - canonical LaTeX technical report and PDF under `docs/report/`.
- Machine-readable model registry: `model_registry.yml`.

### Changed

- The public website is framed as a stable public baseline plus frozen research
  backtest display, not as an active trading service.
- The backtest page shows M-0-M, M-1-M, M-2-M, and CSI300 curves with M-1-M and
  M-2-M clearly labeled as historical full-factor research evidence.
- The public benchmark path uses the audited research-engine semantics:
  previous prediction date drives the next trade date, open execution/open NAV,
  share/cash accounting, `fee_rate=0.0013`, `n_hold=5`, `pool_rank=100`,
  `sell_rank=200`, and industry cap 20%.
- Public docs and commands use the single naming contract M-0-M/M-1-M/M-2-M.

### Removed

- Removed the old single-model prediction cache `build/cache/preds.parquet`.
- Removed the obsolete public-cache simulator and old daily wrapper entrypoint.
- Removed the old multi-model daily tracker; it is superseded by the
  M-0-M-only trading-day refresh workflow above.
- Excluded raw checkpoint pools, seed grids, resume states, ablation weights,
  local inventories, and private data paths.

### Data And Metric Notes

- The strongest research curves assume a compatible full-factor top1000 panel.
- The public/open-data route uses BaoStock as the stable base and AKShare plus
  efinance as enrichment sources where feasible, but it may miss or approximate
  fields such as historical volume ratio, free-float turnover, valuation, and
  order-size money flow.
- Public baseline metrics and full-factor research benchmark metrics answer
  different questions and should not be compared without naming data, universe,
  execution, and fee basis.
- Nothing in this repository is financial advice.
