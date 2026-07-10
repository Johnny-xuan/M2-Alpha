# Model Zoo

M2-Alpha does not publish the whole development checkpoint pool. The public surface is intentionally small:

| Public line | Public role | Underlying evidence |
|---|---|---|
| M-0-M | Current stable public baseline page | Earlier single-model GitHub Pages page, preserved as the smooth public baseline. |
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

M-0-M is the stable public baseline currently shown on GitHub Pages. It keeps the public page smooth and inspectable. Its role is to make the repository usable as a public baseline, not to claim the strongest research result.

### M-1-M

M-1-M is the canonical 3-block research line. It demonstrates the compact M² Block design under a full-factor research panel.

### M-2-M

M-2-M is the deeper 5-block research line. It adds more iterative Micro/Macro refinement and is the strongest public research highlight under the concentrated benchmark strategy.

## Research Benchmark Snapshot

The public backtest page shows M-1-M and M-2-M as historical research curves. They are not updated as daily recommendations.

| Public line | Checkpoint | Benchmark basis | Cumulative return | Sharpe | Max drawdown |
|---|---|---|---:|---:|---:|
| M-1-M | seed42 ep13, 3-block | compatible full-factor top1000 panel, n=5/cap20, sell_rank=200, open execution, 0.13% fee | +239.12% | 3.40 | -15.43% |
| M-2-M | seed2024 ep20, 5-block | compatible full-factor top1000 panel, n=5/cap20, sell_rank=200, open execution, 0.13% fee | +354.34% | 3.99 | -17.68% |

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
