# Results

M2-Alpha results are split into two families:

1. **Public baseline display**: the current static GitHub Pages payload, centered on M-0-M.
2. **Full-factor research benchmark**: historical curves for M-1-M and M-2-M on a compatible research panel.

They answer different questions and should not be mixed without naming the data, universe, execution, and fee basis.

## Public Site Baseline

Source: `docs/data/data.json`

The public site keeps M-0-M as the current stable baseline. It shows daily picks, daily review records, and the baseline NAV curve for the current public payload. This page is useful as an inspectable public baseline, not as a trading recommendation service.

The public payload also contains frozen research curves for M-1-M and M-2-M on the backtest page. Those curves are explicitly historical/research evidence and are not daily recommendations.

## Full-Factor Research Benchmark

The benchmark curve basis used for the public research display:

- compatible full-factor dynamic top1000 A-share panel;
- `n_hold=5`;
- `pool_rank=100`;
- `sell_rank=200`;
- `max_industry_frac=0.2`;
- open execution / open NAV;
- `fee_rate=0.0013`;
- realized window after trading-calendar alignment: 2025-07-10 to 2026-05-21.

| Public line | Checkpoint | Cumulative return | Sharpe | Max drawdown |
|---|---|---:|---:|---:|
| M-1-M | seed42 ep13, 3-block | +239.12% | 3.40 | -15.43% |
| M-2-M | seed2024 ep20, 5-block | +354.34% | 3.99 | -17.68% |

The M-2-M result is the main research highlight shown on the public site. It demonstrates the ability of the deeper 5-block Micro/Macro line under the complete-factor benchmark.

## Why The 4-Block Ablation Is Not A Public Main Line

The 4-block checkpoint remains useful as ablation evidence. Under the same public benchmark runner, it produced:

| Ablation | Cumulative return | Sharpe | Max drawdown |
|---|---:|---:|---:|
| 4-block seed42 ep17 | +147.38% | 1.93 | -30.14% |

Because the latest release decision favors a clearer public story, the 4-block ablation is not shown as M-1-M/M-2-M main-line content. The public page keeps M-0-M as the baseline and uses M-1-M/M-2-M as the two research curves.

## Report Ablation Context

The technical report still contains broader ablations:

- depth scaling across 3/4/5 stacked M² Blocks;
- objective and checkpoint-selection studies;
- strategy sweeps over holding count and industry caps;
- data-source and factor-completeness caveats;
- comparisons with representative sequence and cross-sectional baselines.

Those tables are retained in the PDF and technical docs to explain the research process. They are not all promoted to public model lines.

## Strategy Sweep Used For The Public Research Highlight

The concentrated `n=5` strategy was selected because it asks whether the model can make a small number of high-conviction selections. The same M-2-M checkpoint remains strong under alternative settings, but the public site uses the `n=5, cap20` result as its main capability line.

| Model | n=5 cap20 | n=10 base | n=30 cap20 | n=10 no cap | n=10 cap10 |
|---|---:|---:|---:|---:|---:|
| 4-block ablation seed42 ep17 | +147.21% | +224.12% | +107.46% | +215.79% | +172.03% |
| M-2-M seed2024 ep20 | +354.59% | +235.33% | +113.26% | +253.00% | +196.96% |

This sweep uses the research top1000 universe and report-style open execution with fees. It is evidence for strategy choice, not the same basis as the public M-0-M baseline display.

## Data Caveat

The research benchmark assumes complete factor construction. The open/free public data route can approximate many fields with BaoStock, AKShare, and efinance, but it may miss or neutralize:

- historical true volume ratio;
- free-float turnover;
- valuation fields for some symbols/dates;
- order-size money-flow fields;
- consistent industry and market-cap snapshots.

This is why the public docs separate full-factor research curves from public baseline display. Better data completeness can materially change model rankings.

## Financial Boundary

All numbers here are historical simulations or static public payload evidence. They do not imply future returns, do not include every real trading cost or execution constraint, and are not investment advice.
