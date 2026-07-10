# Method

M2-Alpha models daily stock selection as a cross-sectional ranking problem. For a trading day, it reads a dense panel of stocks over a short lookback window and predicts which stocks should rank higher relative to peers.

The design is built around a simple trading intuition: a useful stock score needs two views at once.

- Micro view: how this stock has behaved over its own recent path.
- Macro view: where this stock sits relative to other stocks on the same day.

The model alternates between those views instead of collapsing the panel into a single sequence or a single cross-section.

## Data Flow

The public baseline takes a long-table daily panel and converts it into:

```text
raw panel
  -> 35 daily features
  -> per-day cross-sectional robust z-score normalization
  -> dense stock x time windows
  -> next-day cross-sectional z-score labels
```

The default window length is `tau=8`. Each sample is one trading day containing all valid stocks for that day.

The full schema is documented in [DATA_SCHEMA.md](DATA_SCHEMA.md). The baseline code supports both open-to-open and close-to-close next-day labels. `configs/baseline.json` defaults to open labels for a practical next-session ranking setup; the frozen research protocol used close-to-close labels and records that mismatch as an evaluation caveat.

## Feature Set

The default public path uses 35 features:

| Group | Count | Examples |
|---|---:|---|
| Multi-scale returns | 8 | `f_ret_1`, `f_ret_5`, `f_ret_60` |
| Moving-average deviation | 5 | `f_close_ma_5`, `f_close_ma_60` |
| Volatility | 5 | rolling standard deviation of one-day return |
| Candlestick shape | 4 | body, range, upper shadow, lower shadow |
| Volume and amount | 5 | volume ratios, one-day volume/amount changes |
| Daily basic fields | 6 | turnover, PE, PB, PS, volume ratio |
| Money-flow structure | 2 | net money-flow ratio, large-vs-small buy imbalance |

Features are computed within each stock's history, then normalized within each trading day's cross-section. This avoids fitting global statistics over future dates.

## Architecture

The model keeps a tensor of shape `(stocks, time, hidden)` through the whole stack.

1. Feature projection maps the 35 raw features to hidden size 128.
2. Sinusoidal time position encoding is added.
3. A stack of M2 blocks alternates three sublayers:
   - Micro: causal time-axis self-attention within each stock.
   - Macro: cross-stock self-attention at each time step.
   - FFN: position-wise feed-forward network.
4. A shared linear head emits one score per stock per time step.

The Micro layer uses a causal mask so each time step can only attend to current and previous inputs. It also adds a Gaussian recency bias with `sigma=4.0`, nudging attention toward nearby historical days.

The Macro layer uses no external industry graph. Each stock attends to the other stocks in the same day's cross-section, letting the model learn soft peer groups from data.

## Dense Supervision

M2-Alpha predicts the whole `(stocks, time)` score grid during training:

```text
loss = mean((prediction[s, t] - label[s, t]) ** 2)
```

At inference time, only the last time step is used as the trading signal.

This is different from models that collapse the time dimension and supervise only the final state. The dense-supervision ablation kept the architecture fixed and changed only supervision density. Dense supervision beat last-step-only supervision under both validation-selected and oracle-best checkpoint readings.

## Training

The public baseline trains one trading day at a time:

- optimizer: AdamW;
- learning rate: `1e-5`;
- weight decay: `1e-4`;
- gradient clipping: norm 5.0;
- max epochs: 40;
- early stopping metric: validation IC;
- default seed: 42.

The original research report used seeds 42, 123, and 2024 to expose seed variance. The public script supports a single-seed baseline path by default; multi-seed runs should be launched explicitly by changing the config seed.

## Relationship To The Runtime And Benchmark Code

There are two code paths:

- `build/`: runtime utilities for factor enrichment, checkpoint inference, and website payload generation.
- `m2alpha/`: cleaned public baseline package for training and research reproduction.

They intentionally serve different roles. `build/` keeps the public-site and released-checkpoint utilities runnable. `m2alpha/` is the readable research implementation that explains how a compatible model can be trained.

The checkpoint format is shared: checkpoints produced by `scripts/train_baseline.py` can be loaded through the same model-key structure used by the inference and benchmark paths.

## Design Takeaways

The strongest research claims are not simply that one backtest number is high. The more portable claims are:

- both time-axis and cross-stock-axis modeling mattered in ablations;
- dense supervision gave a clear advantage over last-step-only supervision;
- validation IC was not a reliable checkpoint-selection rule in this low signal-to-noise setting;
- Macro attention behaved like a learned cross-sectional denoiser in the available diagnostics, though this remains an interpretation rather than a causal proof.
