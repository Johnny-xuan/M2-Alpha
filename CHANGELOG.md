# Changelog

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
- Removed the scheduled daily update workflow from the release surface.
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
