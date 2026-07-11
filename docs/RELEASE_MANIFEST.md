# Release Manifest

This manifest describes the intended public release surface for M2-Alpha.
It is a scope checklist for readers, not a performance claim.

## Public Release Surface

The release includes:

- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CITATION.cff`, `LICENSE`;
- `docs/index.html`, `docs/en.html`, `docs/styles.css`, `docs/js/`,
  `docs/favicon.svg`, and OG preview assets as the static bilingual website;
- `docs/data/data.json` as the committed public baseline and research-curve payload;
- `docs/report/` as the public technical-report PDF, LaTeX source, and figures;
- `docs/*.md` for method, data, results, reproduction, audit, and maintenance notes;
- `m2alpha/` as the readable Micro/Macro research implementation;
- `.github/workflows/m0-baseline-update.yml` as the scheduled, trading-day-aware M-0-M baseline updater;
- `build/alpha_model/`, `build/fetch_data.py`, `build/enrich_data.py`,
  `build/inference.py`, `build/m0_inference.py`, `build/trading_calendar.py`, `build/update_m0_baseline.py`,
  `build/update_backtest_site.py`, `build/init.py`, and `build/industry_map.csv`
  as public data, inference, and site-data utilities;
- `scripts/train_baseline.py`, `scripts/benchmark_research.py`, `scripts/sweep_strategy.py`, `scripts/audit_data_source_fields.py`, and `scripts/test_trading_calendar.py` as public reproduction, strategy-selection, and guard checks;
- `configs/baseline.json` as the baseline training configuration;
- `model_registry.yml` as the machine-readable public model registry;
- `ml/m2alpha.pt`, `ml/m2alpha-m1m.pt`, and `ml/m2alpha-m2m.pt` as released model weights;
- `build/cache/panel.parquet`, `build/cache/csi300.parquet`, `build/cache/basic.csv`, `build/cache/preds_m0m.parquet`, `build/cache/preds_m1m.parquet`, `build/cache/preds_m2m.parquet`, and `build/cache/source_enrichment.json` as public cache artifacts.

## Public Model Contract

The public names are:

| Public name | Role |
|---|---|
| M-0-M | Trading-day refreshed public baseline shown on the site. |
| M-1-M | Frozen 3-block full-factor research curve. |
| M-2-M | Frozen 5-block full-factor research curve and main research highlight. |

Public commands, docs, registry fields, and website copy should use those names.
The 4-block depth run remains technical-report ablation evidence and is not a
released public model line.

## Removed Or Excluded

The release intentionally excludes:

- local planning and scratch files;
- local model inventories and raw experiment checkpoint pools;
- raw provider responses under `build/cache/source_raw/`;
- private data panels, private paths, server names, credentials, and local notebooks;
- obsolete public-cache simulator and old daily wrapper entrypoints;
- old single-model prediction cache `build/cache/preds.parquet`;

## Data Boundary

The committed public/open-data cache supports website inspection, smoke tests,
and code-path checks. Exact M-1-M/M-2-M research-curve reproduction requires a
compatible full-factor historical top1000 A-share panel supplied by the user.

BaoStock is the stable public base source. AKShare and efinance are public
enrichment sources. Some historical factors, especially true volume ratio,
free-float turnover, valuation coverage, and order-size money flow, may be
missing or approximated in an open/free data route.

## Reproduction Checks

Optional commands to reproduce the release:

```bash
git diff --check
python -m compileall -q build m2alpha scripts
python scripts/train_baseline.py --smoke --out /tmp/m2alpha_smoke.pt --device cpu
python scripts/benchmark_research.py --self-test --out-dir /tmp/m2alpha_benchmark_selftest
python scripts/test_trading_calendar.py
```

For docs or website changes, serve both page entries locally:

```bash
python3 -m http.server 8765 --directory docs
```

Then inspect:

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/en.html
```

Public releases are tagged on GitHub and published via GitHub Pages.
