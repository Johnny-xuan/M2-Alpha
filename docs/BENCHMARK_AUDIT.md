# Benchmark Audit

This note records the practical time-alignment audit for the M2-Alpha research
benchmark pipeline. It is meant to keep the benchmark credible without turning
the release into an endless microstructure exercise.

## Two Evidence Surfaces

M2-Alpha has two first-class evidence surfaces:

- Research benchmark: historical reproduction on a user-supplied research-grade
  panel. It tests model ability under a controlled protocol.
- Public baseline: the static open/free public-data payload shown on the site.
  It keeps the repository inspectable without claiming full research-panel
  parity.

The two surfaces answer different questions and must not share a headline
number without naming the basis.

## Current Audit Reading

The original M2 research engine has been ported as the public benchmark path
with explicit checks.

What passes:

- Signal lag: predictions stamped on date `t` are used for trading on the next
  benchmark trade date through `prev_pred`, so same-day close-derived features
  are not traded at the same-day open.
- Feature timing: the 35 public factors are current-or-past daily factors, then
  normalized within the same date cross-section. No future date is used for
  feature normalization.
- Micro attention: the released model uses causal time-axis attention with a
  Gaussian recency bias, so the last-step trading score cannot attend to future
  time steps inside the input window.
- Historical prediction trimming: supervised historical prediction requires
  finite future labels for the tau-window. This trims the tail of the benchmark
  period and should be reported as realized NAV dates, not hidden.

Important caveats:

- The released research checkpoints do not store label-basis metadata. Local
  training evidence indicates the depth-line checkpoints used close-based dense
  labels, while the high-conviction benchmark uses open execution. This is not
  a lookahead leak, but documentation should describe it as an open-execution
  backtest of a close-label-trained ranking model unless contrary metadata is
  found.
- Execution-day tradability uses daily `pct_chg` to approximate limit-up,
  limit-down, and suspension constraints. For an open-execution benchmark this
  is a coarse proxy, usually conservative, not an exchange-level simulator.
- Top1000 membership and industry labels must be supplied from data available
  at or before the benchmark date. The public runner accepts a prebuilt panel
  and optional industry map; the caller is responsible for the research-grade
  universe construction.

## Public Port Contract

The public benchmark command should make these facts visible:

- checkpoint version, seed, and epoch;
- panel path and date range;
- prediction date range and realized NAV date range;
- universe basis, usually top1000 research panel;
- strategy knobs: `n_hold`, `pool_rank`, `sell_rank`, industry cap, weighting;
- execution and NAV price, fee rate, and lot size;
- label basis used for historical date filtering;
- separation from the public baseline display.

The command added for this purpose is:

```bash
python scripts/benchmark_research.py \
  --panel /path/to/research_panel_top1000.parquet \
  --industry-file /path/to/basic.csv \
  --model all \
  --start 20250701 \
  --end 20260525 \
  --n-hold 5 \
  --pool-rank 100 \
  --sell-rank 200 \
  --max-industry-frac 0.2 \
  --exec-price open \
  --fee-rate 0.0013 \
  --out-dir outputs/benchmark
```

The output directory is ignored by Git. It contains predictions, NAV, trades,
holdings, and JSON summaries.

## Release Verification

During release preparation, this public command was run on the local compatible
research top1000 panel for the two public research curves:

| Public line | Checkpoint | Realized NAV dates | Cumulative return | Sharpe | Max drawdown |
|---|---|---|---:|---:|---:|
| M-1-M | seed42 ep13, 3-block | 2025-07-10 to 2026-06-10 | +242.07% | 3.24 | -15.43% |
| M-2-M | seed2024 ep20, 5-block | 2025-07-10 to 2026-06-10 | +383.31% | 3.11 | -31.10% |

The 4-block depth ablation was also checked under the same runner and produced
+147.38%, Sharpe 1.93, max drawdown -30.14%. It is not a public main line.

The M-2-M run was repeated after the deterministic trade-order fix; the summary,
NAV, and trades files matched byte-for-byte across repeated processes. Its
alignment summary reported first prediction date `20250710`, first trade date
`20250711`, and `signal_lag_checked=true`.

These are fixed-protocol integrity references. The public M-2-M capability
curve uses its separately documented Top5/sell50/max-three-per-industry
strategy and reaches +443.01%; strategy selection does not alter the alignment
audit above.
