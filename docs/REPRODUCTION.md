# Reproduction Guide

M2-Alpha has several reproduction paths. They should stay separate because they answer different questions: serving the static website, rebuilding the historical website payload, reproducing the research benchmark, rerunning checkpoint inference, and smoke-testing training code are not the same task.

## 1. Static Website

The public website is a static GitHub Pages surface. It can be served directly from the committed `docs/` directory:

```bash
cd docs
python3 -m http.server 8765
```

Then open:

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/en.html
```

The page reads `docs/data/data.json`. That payload currently contains:

- `M-0-M`: the trading-day refreshed public baseline shown in the picks, review, and baseline backtest curve;
- `M-1-M`: a frozen full-factor 3-block historical research curve;
- `M-2-M`: a frozen full-factor 5-block historical research curve.

`M-1-M` and `M-2-M` are not daily updated recommendations.

## 2. M-0-M Trading-Day Refresh

Only M-0-M has an automated public update path. The workflow runs after close on
weekdays, checks BaoStock's A-share trading calendar, and exits successfully on
weekends and China-market holidays. It also refuses to publish when the fetched
panel does not end on the validated trading session.

The updater calls `m2alpha.benchmark.run_research_backtest` directly. M-0-M
uses its selected public strategy: `n_hold=7`, `pool_rank=100`, `sell_rank=35`,
and at most three names per industry. Previous-date signal lag, share/cash accounting, open
execution/open NAV, and `fee_rate=0.0013` use the same audited benchmark engine.
The public baseline uses a BaoStock CSI300 panel; the frozen research curves use
their own selected parameters on the richer external top1000 panel described below.

The local equivalent is:

```bash
python build/trading_calendar.py --date 2025-10-01
python build/m0_inference.py
python build/update_m0_baseline.py \
  --expected-trade-date 20260710 \
  --next-trading-day 20260713
```

`build/update_m0_baseline.py` updates only the root M-0-M fields and the M-0-M
chart entry in `docs/data/data.json`; it preserves the frozen M-1-M/M-2-M
research curves.

For a non-publishing GitHub Actions check of the whole path, dispatch a dry run
with an already available trading session. `session_date` is rejected unless
`dry_run=true`, so it cannot be used to backdate a scheduled publication:

```bash
gh workflow run m0-baseline-update.yml -f dry_run=true -f session_date=2026-07-10
```

## 3. Website Payload Rebuild

The website payload entrypoint is:

```bash
python build/update_backtest_site.py
```

It rebuilds the historical website payload through the audited benchmark-data generator and expects a compatible panel plus benchmark cache under:

```text
build/cache/panel.parquet
build/cache/csi300.parquet
build/cache/basic.csv
build/cache/preds_m1m.parquet
build/cache/preds_m2m.parquet
```

The script keeps the current `M-0-M` baseline fields from the existing `docs/data/data.json` when available, then replaces the frozen `M-1-M` and `M-2-M` research curves with freshly generated benchmark curves.

The explicit command is:

```bash
python build/update_backtest_site.py \
  --panel build/cache/panel.parquet \
  --benchmark-index build/cache/csi300.parquet \
  --industry-file build/cache/basic.csv \
  --model all \
  --start 20250710 \
  --n-hold 5 \
  --pool-rank 100 \
  --sell-rank 200 \
  --max-industry-frac 0.2 \
  --exec-price open \
  --fee-rate 0.0013
```

For exact research-curve reproduction, `build/cache/panel.parquet` must be a compatible full-factor top1000 panel. The small public/open-data cache is useful for code checks, but it is not guaranteed to reproduce the full-factor research curves.

## 4. Research Benchmark

This is the main benchmark/reproduction path for the report-level numbers. It runs the same audited research backtest semantics: previous prediction date drives the next trade date, open execution/open NAV, share/cash accounting, and fee rate `0.0013`. The published fixed-protocol comparison uses `n_hold=5`, `pool_rank=100`, `sell_rank=200`, and industry cap 20%.

Keep two evaluation questions distinct. A fixed protocol compares model
architectures under identical portfolio rules. A release/capability curve may
use checkpoint-specific strategy parameters selected in a declared historical
sweep. M-1-M selects Top-5/sell-200/maximum-one-per-industry; M-2-M selects
Top-5/sell-50/maximum-three-per-industry; M-0-M selects a third rule on its
public CSI300 panel.

Quick code-path self-test:

```bash
python scripts/benchmark_research.py \
  --self-test \
  --out-dir /tmp/m2alpha_benchmark_selftest
```

Research benchmark command:

```bash
python scripts/benchmark_research.py \
  --panel /path/to/panel_top1000.parquet \
  --industry-file /path/to/basic.csv \
  --model all \
  --start 20250701 \
  --end 20260612 \
  --n-hold 5 \
  --pool-rank 100 \
  --sell-rank 200 \
  --max-industry-frac 0.2 \
  --exec-price open \
  --fee-rate 0.0013 \
  --out-dir outputs/benchmark
```

With the compatible local research top1000 panel, the fixed-protocol runner produced:

| Public line | Checkpoint | Realized window | Cumulative return | Sharpe | Max drawdown |
|---|---|---|---:|---:|---:|
| M-1-M | seed42 ep13, 3-block | 2025-07-10 to 2026-06-10 | +242.07% | 3.24 | -15.43% |
| M-2-M | seed2024 ep20, 5-block | 2025-07-10 to 2026-06-10 | +383.31% | 3.11 | -31.10% |

The benchmark writes predictions, NAV, trades, holdings, and summary JSON files. Its alignment audit is documented in [BENCHMARK_AUDIT.md](BENCHMARK_AUDIT.md).

Use those fixed prediction caches for checkpoint-level portfolio tuning:

```bash
python scripts/sweep_strategy.py \
  --panel /path/to/panel_top1000.parquet \
  --predictions outputs/benchmark/predictions_m2m.parquet \
  --industry-file /path/to/basic.csv \
  --model-label M-2-M \
  --out outputs/benchmark/strategy_sweep_m2m.json
```

The registered M-2-M selected strategy is Top 5, sell rank 50, maximum three
names per industry; it produces +443.01%, Sharpe 3.99, and -13.86% maximum
drawdown through 2026-06-10. The sweep output labels this as historical best
among tested strategies rather than untouched OOS evidence.

## 5. Checkpoint Inference

This reruns a public research checkpoint on a panel and writes predictions.

```bash
python build/inference.py \
  --panel build/cache/panel.parquet \
  --model M-2-M \
  --out /tmp/M-2-M_predictions.parquet \
  --device cpu
```

The command accepts only the current public research names, `M-1-M` and `M-2-M`, plus `all` for both research curves. Older public-development aliases are intentionally not supported.

To rebuild the committed research prediction caches for both public research curves:

```bash
python build/inference.py --device cpu
```

## 6. Baseline Training

The public training implementation is in `m2alpha/` and is driven by `scripts/train_baseline.py`.

Smoke test on committed cache data:

```bash
python scripts/train_baseline.py \
  --smoke \
  --out /tmp/m2alpha_smoke.pt \
  --device cpu
```

Full baseline command:

```bash
python scripts/train_baseline.py \
  --config configs/baseline.json \
  --panel /path/to/historical_panel.parquet \
  --out outputs/checkpoints/m2alpha_baseline.pt
```

The full command expects a historical A-share panel matching [DATA_SCHEMA.md](DATA_SCHEMA.md).

## What Is Reproducible From This Repository Alone

- The static Chinese and English pages can be served locally.
- The committed website payload can be inspected without external data.
- The public checkpoint inference code can be run on any compatible panel.
- The training loop can be smoke-tested on committed cache data.
- The research benchmark command can be self-tested on a synthetic panel.

## What Requires External Data

- Full historical training.
- Exact frozen research benchmark replication for `M-1-M` and `M-2-M`.
- Multi-seed and ablation tables from the technical report.

Those require a compatible historical A-share panel with the schema in [DATA_SCHEMA.md](DATA_SCHEMA.md). The original research work used richer historical A-share data that is not redistributed in this repository. See [DATA_SOURCES.md](DATA_SOURCES.md) for source tiers and caveats.

## Verification Run For This Release

These commands are the intended release checks:

```bash
python -m compileall -q build m2alpha scripts
python scripts/train_baseline.py --smoke --out /tmp/m2alpha_smoke.pt --device cpu
python scripts/benchmark_research.py --self-test --out-dir /tmp/m2alpha_benchmark_selftest
```

The smoke tests are code-path checks, not performance claims. Performance claims require the compatible full-factor panel and the benchmark command above.
