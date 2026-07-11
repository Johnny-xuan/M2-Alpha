# Model Zoo

M2-Alpha does not publish the whole development checkpoint pool. The public surface is intentionally small:

| Public line | Public role | Underlying evidence |
|---|---|---|
| M-0-M | Trading-day refreshed public baseline page | Current public checkpoint and baseline updater; it refreshes only after a validated A-share session. |
| M-1-M | Historical 3-block research curve | Released 3-block full-factor checkpoint, shown as a frozen benchmark curve. |
| M-2-M | Historical 5-block research curve | Released 5-block full-factor checkpoint, shown as the main research highlight curve. |

A 4-block depth ablation remains useful evidence in the technical report, but it is not a public model line on the website.

## Shared Architecture

| Field | Value |
|---|---:|
| Architecture | M2-Alpha Micro-Macro stack |
| Lookback window | 8 trading days |
| Feature count | 35 |
| Hidden size | 128 |
| Micro attention heads | 4 |
| Macro attention heads | 2 |
| Dropout | 0.1 |
| Gaussian time-bias sigma | 4.0 |
| Market gating | Off |

M-0-M and M-1-M are compact 3-block lines. M-2-M is the deeper 5-block iterative line. The model design difference is depth and repeated Micro/Macro refinement, not a different feature contract.

## Public Lines

### M-0-M

M-0-M is the trading-day refreshed CSI300 public baseline currently shown on GitHub Pages. It uses the audited research backtest engine with its selected Top-7, sell-rank 35, maximum-three-per-industry strategy. Signal lag, next-open execution, open NAV, share/cash accounting, and fees remain aligned with the research engine. The workflow skips weekends, China-market holidays, calendar failures, and stale panel data. Its role is to make the repository usable as a public baseline, not to claim the strongest research result.

### M-1-M

M-1-M is the canonical 3-block research line. It demonstrates the compact M² Block design under a full-factor research panel.
Its displayed Top-5/sell-200/maximum-one-per-industry portfolio rule was selected from its own strategy sweep.

### M-2-M

M-2-M is the deeper 5-block research line. It adds more iterative Micro/Macro refinement and is the strongest public research highlight under its selected concentrated strategy.
Its independent sweep selects Top-5/sell-50/maximum-three-per-industry, rather than inheriting M-1-M's portfolio rule.

## Research Benchmark Snapshot

The public backtest page shows M-1-M and M-2-M as historical research curves. They are not updated as daily recommendations.

| Public line | Checkpoint | Benchmark basis | Cumulative return | Sharpe | Max drawdown |
|---|---|---|---:|---:|---:|
| M-1-M | seed42 ep13, 3-block | full-factor top1000, Top 5/sell 200/max 1 per industry, open, 0.13% fee | +242.07% | 3.24 | -15.43% |
| M-2-M | seed2024 ep20, 5-block | full-factor top1000, Top 5/sell 50/max 3 per industry, open, 0.13% fee | +443.01% | 3.99 | -13.86% |

These numbers require a compatible full-factor historical panel. The public/open data route may miss or approximate volume ratio, free-float turnover, valuation, industry, or money-flow inputs, so it should be treated as a weaker open-data baseline rather than a full reproduction of the research curves.

## Storage Policy

The repository keeps the release assets needed to inspect the architecture and reproduce the documented benchmark paths. Public assets use the M-0-M/M-1-M/M-2-M contract directly.

Do not commit:

- full research checkpoint pools;
- seed packs and raw epoch grids;
- resume `.last.pt` states;
- unrelated ablation checkpoints;
- local development inventories.

If a future release changes a model weight, update this page, [model_registry.yml](../model_registry.yml), [RESULTS.md](RESULTS.md), and the public site data together.
