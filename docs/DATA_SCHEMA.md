# Data Schema

M2-Alpha expects a daily A-share panel in long-table form: one row per `(trade_date, ts_code)`. Data-source roles and source-specific caveats are documented in [DATA_SOURCES.md](DATA_SOURCES.md).

## Required Columns

These columns are required by the public baseline feature and training path:

| Column | Type | Meaning |
|---|---|---|
| `trade_date` | string-like `YYYYMMDD` | Trading date. |
| `ts_code` | string | Ticker code such as `600000.SH`. |
| `open` | float | Daily open price. |
| `high` | float | Daily high price. |
| `low` | float | Daily low price. |
| `close` | float | Daily close price. |
| `pre_close` | float | Previous close. |
| `pct_chg` | float | Daily percentage change; used by runtime data, not as a model feature. |
| `vol` | float | Volume. |
| `amount` | float | Turnover amount. |
| `vwap` | float | Volume-weighted average price. |
| `turnover_rate` | float | Turnover rate. |
| `turnover_rate_f` | float | Free-float turnover proxy. |
| `volume_ratio` | float or missing | Volume ratio. Missing values are neutralized after cross-sectional normalization. |
| `pe_ttm` | float | PE TTM. |
| `pb` | float | PB. |
| `ps_ttm` | float | PS TTM. |
| `net_mf_amount` | float | Net money-flow amount. |
| `buy_sm_amount` | float | Small-order buy amount. |
| `buy_lg_amount` | float | Large-order buy amount. |
| `buy_elg_amount` | float | Extra-large-order buy amount. |

## Optional Public-Enrichment Columns

These columns may be present in the committed public/open-data cache after `build/enrich_data.py` runs. They are useful for source audit and future feature work, but the released checkpoints still use the 35-feature contract above.

| Column | Type | Meaning |
|---|---|---|
| `market_cap` | float or missing | Latest-date total market-cap snapshot from AKShare/efinance when available. |
| `float_market_cap` | float or missing | Latest-date float market-cap snapshot from AKShare/efinance when available. |
| `pe_dynamic` | float or missing | Latest-date dynamic PE snapshot from AKShare/efinance when available. |

The public/open-data pipeline uses BaoStock as the historical base source, AKShare/efinance as public enrichment sources, and a volume-derived proxy for historical `volume_ratio` when vendor-style `daily_basic` is absent. Unavailable historical money-flow tiers are still stubbed to zero when no public source provides an audited replacement. This keeps the public pipeline auditable without private credentials, but it is not equivalent to the richer research panel used for the technical-report experiments. Full research reproduction should use a historical panel with real `daily_basic` and `moneyflow` fields when possible. See [DATA_SOURCES.md](DATA_SOURCES.md) for the recommended source tiers.

## Labels

Labels are computed by the training code, not supplied as input columns.

- Open-label mode: `open[s+2] / open[s+1] - 1`.
- Close-label mode: `close[s+2] / close[s+1] - 1`.
- The raw future returns are converted to same-day cross-sectional z-scores.
- Dense supervision uses the label for every step in the `tau=8` window.

Rows near the end of a panel naturally lack future prices and are excluded from supervised training/validation windows.

## Splits

The public baseline config uses the report-style split:

```json
"train": ["20170101", "20231231"],
"valid": ["20240101", "20250630"],
"test": ["20250701", "20260525"]
```

The committed cache in this repository is a compact public/runtime cache, not the full historical training dataset. Use `--smoke` for a local command check on committed data.
