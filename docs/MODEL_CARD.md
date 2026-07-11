# Model Card

## Model Identity

M2-Alpha is a daily A-share cross-sectional alpha model. It scores stocks relative to peers, then the benchmark layer turns those scores into a fixed top-N portfolio rule.

The public-facing model lines are:

| Public line | Role |
|---|---|
| M-0-M | Trading-day refreshed public baseline currently shown on the site. |
| M-1-M | 3-block historical research curve. |
| M-2-M | 5-block historical research curve and current research highlight. |

The public contract uses these names only. The 4-block depth ablation is retained as technical-report evidence, not as a shipped public model line.

## Intended Use

This repository is intended for:

- understanding the M2-Alpha Micro/Macro architecture;
- inspecting released model assets and benchmark rules;
- reading the public technical report;
- reproducing benchmark results with a compatible historical factor panel;
- using the static public site as a model-release presentation surface.

It is not intended for:

- investment advice;
- production portfolio management;
- claims about future returns;
- one-command reproduction of the original historical experiments without external data;
- presenting frozen research curves as daily trading recommendations.

## Inputs And Outputs

Input shape is `(S, T, F)`:

- `S`: number of valid stocks on a trading day;
- `T`: 8 trading days;
- `F`: 35 daily factors.

Output shape is `(S, T)`: one score per stock per time step. Training supervises the full grid; inference uses the last time step for cross-sectional ranking.

## Architecture

| Component | Default |
|---|---:|
| Lookback window | 8 trading days |
| Feature count | 35 |
| Hidden size | 128 |
| Micro attention heads | 4 |
| Macro attention heads | 2 |
| Dropout | 0.1 |
| Gaussian time bias sigma | 4.0 |
| Optimizer | AdamW |
| Learning rate | 1e-5 |
| Weight decay | 1e-4 |

Micro attention reads the time axis for each stock. Macro attention compares stocks on the same date. Stacked M² Blocks let those two views repeatedly refine each other.

## Data

The original research work used a richer historical A-share panel from 2017-01 to 2026-05, including price-volume fields, daily basic indicators, valuation fields, turnover, volume ratio, and money-flow fields.

That full historical dataset is not bundled in this repository. The public/open-data route uses BaoStock, AKShare, and efinance where possible, but some fields can be missing, approximated, or neutralized. Full-factor reproduction requires a compatible panel matching [DATA_SCHEMA.md](DATA_SCHEMA.md).

## Evaluation Summary

The public site separates baseline display from research evidence:

- M-0-M is the current CSI300 public baseline page, refreshes only after a validated A-share trading session, and uses the audited research backtest engine with its selected Top-7/sell-35/industry-max-3 strategy.
- M-1-M and M-2-M are frozen full-factor historical research curves.
- The backtest page labels M-2-M as a latest capability line, not as a daily updated recommendation.
- Portfolio size, sell band, and industry constraints are model-level evaluation hyperparameters. The engine, signal lag, execution, NAV accounting, and fees remain shared and audited.

Main benchmark snapshot:

| Public line | Basis | Cumulative return | Sharpe | Max drawdown |
|---|---|---:|---:|---:|
| M-1-M | full-factor top1000, Top 5/sell 200/max 1 per industry, open, fee 0.0013 | +242.07% | 3.24 | -15.43% |
| M-2-M | full-factor top1000, Top 5/sell 50/max 3 per industry, open, fee 0.0013 | +443.01% | 3.99 | -13.86% |

These are historical simulations. They do not imply future returns.

M-1-M and M-2-M use independently selected portfolio rules from the documented
145-candidate sweeps. M-0-M uses a third Top-7/sell-35/industry-max-3
configuration selected on its public CSI300 panel. These are post-hoc historical
strategy selections, not untouched OOS results.

## Limitations

- Historical full-factor reproduction depends on external A-share data.
- Public free data may miss or approximate important factors.
- Backtest results are sensitive to data source, universe, transaction-cost assumptions, and checkpoint selection.
- A-share alpha is low signal-to-noise, and learned signals can decay.
- Nothing here is financial advice.
