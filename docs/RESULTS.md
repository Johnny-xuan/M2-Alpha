# Results

M2-Alpha results are split into two families:

1. **Public baseline display**: the trading-day refreshed GitHub Pages payload, centered on M-0-M.
2. **Full-factor research benchmark**: historical curves for M-1-M and M-2-M on a compatible research panel.

They answer different questions and should not be mixed without naming the data, universe, execution, and fee basis.

## Public Site Baseline

Source: `docs/data/data.json`

The public site keeps M-0-M as the current stable CSI300 baseline. It shows daily picks, daily review records, and the baseline NAV curve for the current public payload. GitHub Actions refreshes it only after a validated A-share trading session; weekends, China-market holidays, unavailable calendars, and stale data result in no publication. M-0-M uses the audited `run_research_backtest` engine with its selected Top-7/sell-rank-35/industry-max-3 strategy. Signal lag, open execution/open NAV, share/cash accounting, and fees use the same engine semantics as the research curves. The frozen research curves retain their own selected parameters and richer external top1000 panel.

The M-0-M strategy was selected by a same-checkpoint, same-prediction, same-panel sweep through 2026-07-10:

| M-0-M strategy | Cumulative return | Sharpe | Max drawdown |
|---|---:|---:|---:|
| Top 7 / sell 35 / max 3 per industry | +170.92% | 2.93 | -13.16% |
| Top 9 / sell 40 / no industry cap | +160.90% | 2.93 | -12.01% |
| Top 8 / sell 30 / max 4 per industry | +160.79% | 2.85 | -12.77% |
| Top 10 / sell 50 / no industry cap | +144.67% | 2.76 | -12.22% |
| Top 5 / sell 200 / industry cap20 | +64.85% | 1.77 | -15.79% |

This is a historical strategy-selection result, not an untouched out-of-sample strategy comparison. Subsequent trading-day updates extend the selected rule forward without retuning it each day.

The public payload also contains frozen research curves for M-1-M and M-2-M on the backtest page. Those curves are explicitly historical/research evidence and are not daily recommendations.

## Full-Factor Selected-Strategy Curves

The public research curves keep one audited engine and accounting contract but
use checkpoint-specific portfolio parameters selected on a declared historical
grid:

- compatible full-factor dynamic top1000 A-share panel;
- open execution / open NAV;
- `fee_rate=0.0013`;
- realized window after label/window alignment: 2025-07-10 to 2026-06-10.

| Public line | Checkpoint | Selected strategy | Cumulative return | Sharpe | Max drawdown |
|---|---|---|---:|---:|---:|
| M-1-M | seed42 ep13, 3-block | Top 5 / sell 200 / max 1 per industry | +242.07% | 3.24 | -15.43% |
| M-2-M | seed2024 ep20, 5-block | Top 5 / sell 50 / max 3 per industry | +443.01% | 3.99 | -13.86% |

The M-2-M result is the main research highlight shown on the public site. It demonstrates the deeper 5-block Micro/Macro line under the complete-factor benchmark and its selected portfolio rule.

The portfolio rule is part of each model's released evaluation configuration.
The backtest engine, prediction/execution lag, open execution/open NAV, equal
weighting, and fees stay fixed; `n_hold`, the sell band, and the industry
constraint may be selected per checkpoint on a declared historical sweep.

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

## Strategy Sweep Used For The Public Curves

`scripts/sweep_strategy.py` fixes the checkpoint, historical prediction cache,
panel, engine, signal lag, execution, NAV accounting, and fees. It scans 145
unique combinations over `n_hold={5,7,10,15,30}`, `sell_rank={20,35,50,100,200}`,
and absolute per-industry limits `{1,2,3,4,5,no-cap}` where valid.

| Model | Candidate | Cumulative return | Sharpe | Max drawdown | Turnover |
|---|---|---:|---:|---:|---:|
| M-1-M | Top 5 / sell 200 / max 1 industry | +242.07% | 3.24 | -15.43% | 0.2916 |
| M-1-M | Top 5 / sell 200 / max 2 industry | +231.03% | 2.70 | -19.15% | 0.2965 |
| M-1-M | Top 7 / sell 200 / max 1 industry | +216.60% | 3.34 | -14.72% | 0.2965 |
| M-2-M | Top 5 / sell 50 / max 3 industry | +443.01% | 3.99 | -13.86% | 0.5502 |
| M-2-M | Top 5 / sell 50 / max 4 industry | +440.96% | 3.94 | -13.86% | 0.5536 |
| M-2-M | Top 5 / sell 20 / max 2 industry | +413.06% | 3.12 | -26.56% | 0.8496 |

`pool_rank=100` is retained in metadata for compatibility with the historical
research interface, but the current original-compatible strategy ranks the
full tradable list; it is not counted as an active sweep dimension. The selected
curves are best among tested strategies on the same historical window. This is
post-hoc strategy tuning and must not be described as untouched OOS evidence.

## Fixed-Protocol Reference

For an architecture-oriented comparison, both checkpoints can still be run
with Top 5 / sell 200 / max 1 per industry. On the same panel and window:

| Public line | Cumulative return | Sharpe | Max drawdown |
|---|---:|---:|---:|
| M-1-M | +242.07% | 3.24 | -15.43% |
| M-2-M | +383.31% | 3.11 | -31.10% |

The technical report retains its earlier report-window and five-setting tables
as research history. The website's +443.01% M-2-M curve is the later,
explicitly labeled model-specific strategy sweep result.

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
