# Data Sources

M2-Alpha separates the public/open-data pipeline from research-grade historical reproduction. This distinction matters because the model uses more than daily OHLCV: several of its 35 features depend on free-float turnover, volume ratio, valuation fields, and order-size money-flow inputs.

## Source Tiers

| Tier | Role | Current status |
|---|---|---|
| Public/open-data base source | Provides the stable historical cache without private credentials. | BaoStock |
| Public/open-data enrichment | Adds no-secret public enrichment, historical `volume_ratio` proxy fill, and source metadata that BaoStock does not expose. | AKShare + efinance + derived public proxy |
| Research-grade panel | Reproduces full training and frozen benchmark conditions when the user supplies a richer historical panel. | User supplied |

The committed repository includes enough cache state to rebuild the dashboard, rerun public checkpoint inference, and smoke-test the training loop. It does not include the full historical research panel.

## Public/Open-Data Source: BaoStock + AKShare + efinance

The public/open-data path is a no-secret hybrid pipeline:

1. BaoStock provides the stable CSI300 constituent list, historical daily OHLCV, turnover, and valuation-style base cache.
2. `build/enrich_data.py` fills historical `volume_ratio` with a transparent volume-derived proxy when vendor-style `daily_basic` volume ratio is absent.
3. AKShare provides a latest-date A-share snapshot through `stock_zh_a_spot_em`, including fields such as `量比`, PB, dynamic PE, market cap, float market cap, and turnover when the endpoint is available.
4. efinance provides a second Eastmoney-backed snapshot through `ef.stock.get_realtime_quotes()` and `ef.stock.get_base_info(...)`, including `量比`, PB, industry, market cap, ROE, and profitability-style fields where available.
5. Eastmoney-style historical money-flow endpoints are attempted as a best-effort fill through a direct request path and an efinance `get_history_bill` fallback. Successful direct responses are cached under the local raw-cache directory for replay, while coverage and failures are written to source metadata rather than silently changing the data contract.

This design deliberately keeps BaoStock as the base source because it is simple, auditable, and can run on GitHub Actions without secrets.

The hybrid public/open-data path is suitable for:

- daily OHLCV and amount updates;
- turnover, trading status, ST status, and valuation-style fields available through the BaoStock K-line interface;
- historical `volume_ratio` proxy fill plus valuation/market-cap snapshots from AKShare/efinance;
- raw-response replay for intermittent Eastmoney money-flow responses when a previous successful pull exists;
- industry fallback from efinance base info when the committed industry map and BaoStock fallback are missing;
- CSI300 constituent tracking used by the public baseline dashboard;
- deterministic public cache updates.

It is not a full replacement for the richer research panel. The public pipeline can activate `volume_ratio`, but it does so through a transparent proxy rather than vendor-identical `daily_basic`; `turnover_rate_f` may remain a proxy; and the public/open-data cache still does not provide a fully audited historical order-size money-flow panel equivalent to the research data. This is why public-baseline metrics and full-factor research benchmark metrics should not be mixed without naming the data basis.

## Research-Grade Panel

Full training and frozen benchmark replication require a historical A-share panel matching [DATA_SCHEMA.md](DATA_SCHEMA.md). The important extra fields are:

| Feature family | Expected columns |
|---|---|
| Free-float turnover and volume ratio | `turnover_rate_f`, `volume_ratio` |
| Valuation | `pe_ttm`, `pb`, `ps_ttm` |
| Money flow | `net_mf_amount`, `buy_sm_amount`, `buy_lg_amount`, `buy_elg_amount` |

Tushare Pro-style data is the closest public API shape for this contract: `daily_basic` covers volume ratio, free-float turnover, and valuation fields, while `moneyflow` covers small, medium, large, extra-large order amounts and net money flow. However, Tushare Pro requires a user token and API permissions. For that reason it is appropriate as a user-supplied research input, not as the default anonymous public/open-data source.

This repository does not redistribute a full raw historical A-share panel. Users are responsible for their own data access rights, API credentials, rate limits, and redistribution constraints.

## Free Enrichment Sources Used In The Public/Open-Data Pipeline

AKShare and efinance are part of the public/open-data enrichment code path. They are still handled as an enrichment layer rather than a silent replacement for BaoStock, because website-backed endpoints can be rate-limited or changed without notice.

The practical read is:

| Question | AKShare | efinance | M2-Alpha implication |
|---|---|---|---|
| Package cost/license | Free Python package; MIT-licensed project. | Free Python package; MIT-licensed project. | Both can be optional code dependencies if their transitive dependencies stay acceptable. |
| Credential requirement | Many endpoints work without a token. | Many endpoints work without a token. | Both are more public-pipeline-friendly than token-gated APIs, at least operationally. |
| Upstream style | Aggregates public website endpoints such as Eastmoney/Sina/Xueqiu and official exchange pages. | Primarily wraps Eastmoney-style structured endpoints. | Website-derived endpoints can be rate-limited or changed without notice. |
| Historical OHLCV and turnover | Available through A-share historical quote interfaces. | Available through `get_quote_history`. | Either could replace or cross-check part of BaoStock's price/volume path. |
| Volume ratio and valuation | Realtime quote/basic endpoints expose fields such as `volume_ratio`, PE, and PB; full historical `daily_basic` parity is not proven. | Realtime quotes and base info expose `量比`, dynamic PE, PB, and related fields; full historical `pe_ttm/pb/ps_ttm` parity is not proven. | The current runtime fills historical `volume_ratio` from BaoStock volume as an explicit proxy, then uses AKShare/efinance snapshots where available. |
| Free-float turnover | No audited full-history replacement for `turnover_rate_f` is documented in this repo. | No audited full-history replacement for `turnover_rate_f` is documented in this repo. | This is still one of the critical gaps. |
| Money flow | Eastmoney money-flow endpoints expose main/large/small style net inflow fields and rankings. | `get_history_bill` exposes historical net inflow by order-size buckets. | The runtime now tries both direct Eastmoney and efinance fallback paths and maps net inflow buckets into the M2 money-flow columns. This is still an approximation, not audited parity with the research panel's buy/sell amount schema. |
| Public-pipeline role | Primary snapshot enrichment source for volume ratio, valuation, market cap, and OHLCV cross-checks. | Secondary snapshot enrichment source and industry/base-info fallback. | Both are enabled as no-secret enrichment sources; BaoStock remains the base cache source and derived volume ratio fills the historical gap. |

AKShare is used through `build/enrich_data.py` as a primary public enrichment source. Its stock data documentation includes historical A-share quotes, realtime quote fields such as volume ratio and valuation, and Eastmoney-style money-flow interfaces. It should still be treated carefully because many endpoints are website-derived, can be rate-limited, and may not provide the same historical depth or field definitions as the research panel. AKShare's own documentation also frames the data interfaces as academic/research oriented and warns about commercial/data risk, so this repository should avoid treating AKShare-fetched raw data as freely redistributable by default.

efinance is used through `build/enrich_data.py` as the secondary enrichment and base-info source. It is useful for realtime quote snapshots, PB, industry, market cap, ROE, and profitability fields. However, its project documentation states a learning/research-use boundary, and its maintainer has discussed Eastmoney IP-rate-limit pressure for daily K-line and realtime quote access. That makes it appropriate as a best-effort enrichment layer, not as the only anonymous public/open-data source.

AData is another free/open-source A-share candidate worth watching. It focuses on A-share quantitative trading data and exposes historical market data, index constituents, industry mappings, and daily capital-flow style interfaces through a multi-source aggregation layer. Its practical position is similar to AKShare: useful for adapter experiments, but not a drop-in research-panel replacement until field definitions, history depth, retry behavior, and redistribution constraints are audited.

### Local Validation Probe

A local validation probe compared AKShare and efinance against the committed BaoStock cache on a small sample. It used five liquid A-share examples (`000001.SZ`, `000063.SZ`, `000333.SZ`, `600519.SH`, `300750.SZ`) over the latest four overlapping BaoStock dates (`20260701`, `20260702`, `20260703`, `20260706`).

The stable part was basic price and volume data. AKShare's Tencent historical quote interface returned all 20 expected sample rows. After normalizing volume from hands to shares, open, high, low, and close matched BaoStock exactly; volume differed only by lot-size rounding, with max relative error about `0.13` basis points in the sample. This supports using AKShare as a cross-check for basic OHLCV integrity.

The useful-but-risky part was enrichment data. efinance successfully returned one full realtime A-share snapshot during the probe, including `量比`, turnover, dynamic PE, volume, amount, and latest trade date for the sample names; `get_base_info` also returned PB, industry, market-cap, ROE, and profitability fields for the same names. Those fields are directly relevant to the current BaoStock public-cache gaps.

The unstable part was Eastmoney endpoint reliability. Repeated calls to Eastmoney historical K-line, realtime quote, and money-flow endpoints intermittently failed with remote-disconnect errors from the local environment. This affected both direct endpoint calls and package wrappers. Therefore AKShare/efinance are used as best-effort adapters with retries and clear source labels, not as a silent replacement for BaoStock's default GitHub Actions path.

qstock exposes broader data and money-flow style utilities, but its sources and dependencies are more mixed. It is not a good default dependency for a minimal public release pipeline.

TDX-style clients such as pytdx or mootdx can be useful for realtime quotes, bars, minute data, or transaction-style market data. They are not a drop-in replacement for the M2-Alpha panel because they do not directly provide the historical daily-basic plus order-size money-flow contract used here. Reconstructing comparable daily money-flow factors from tick or transaction data would be a separate data-engineering project and would need a field audit before changing metrics.

zvt and similar quant frameworks are better understood as provider frameworks rather than a single source. They may route to free website providers or account-based providers, so their suitability depends on the underlying provider and exported fields.

Qlib's public China-stock data is useful for price/volume Alpha158-style experiments, but it is not a replacement for the M2-Alpha field contract because it does not provide the daily-basic plus order-size money-flow panel expected by this repository.

JoinQuant/JQData, RiceQuant/RQData, BigQuant-style platforms, and similar research data products may cover many of the missing fields. They are reasonable private research inputs if a user has access, but they are account-bound data paths rather than anonymous open defaults. They should be documented as user-supplied panels, not hidden requirements of the public/open-data pipeline.

## Field-Audit Utility

Before promoting any source to research-grade equivalence, build a candidate panel with the schema in [DATA_SCHEMA.md](DATA_SCHEMA.md) and compare it against the committed public cache:

```bash
python scripts/audit_data_source_fields.py \
  --panel baostock=build/cache/panel.parquet \
  --panel candidate=/path/to/candidate_panel.parquet
```

The audit checks more than column names. It flags empty columns, all-zero money-flow stubs, inactive `volume_ratio`, and `turnover_rate_f` values that are only a proxy for `turnover_rate`. A source should not be treated as research-grade unless the critical fields are active over the intended historical window.

For AKShare or efinance specifically, the current release uses snapshot enrichment, a derived historical `volume_ratio` proxy, direct Eastmoney historical money-flow attempts, efinance `get_history_bill` fallback, and raw-response replay for intermittent successful pulls. A stronger future step would be to build a fully audited historical enriched candidate panel over the same universe/date slice as the committed public cache, normalize column names into [DATA_SCHEMA.md](DATA_SCHEMA.md), and run the audit tool. Only after that should the repository claim research-panel equivalence.

## Source Policy

Any future data-source change should preserve these rules:

1. The default public/open-data pipeline must be runnable without private credentials.
2. Metrics must name their universe, strategy, cost assumption, and data source.
3. If feature availability changes, checkpoint predictions and displayed metrics must be regenerated and re-audited.
4. Website-backed enrichment failures should be recorded in metadata and should not silently corrupt the base BaoStock cache.
5. Source metadata such as `build/cache/source_enrichment.json` should be committed; reusable raw provider responses under `build/cache/source_raw/` should stay local unless the upstream license clearly allows redistribution.
6. Generated predictions and dashboard summaries are committed for reproducibility, but full third-party raw panels should not be redistributed unless the data license clearly allows it.

## References

- BaoStock: <https://www.baostock.com/>
- Tushare Pro: <https://tushare.pro/>
- AKShare: <https://akshare.akfamily.xyz/>
- AKShare special statement: <https://akshare.akfamily.xyz/special.html>
- AKShare GitHub: <https://github.com/akfamily/akshare>
- AData: <https://github.com/1nchaos/adata>
- efinance: <https://efinance.readthedocs.io/>
- efinance GitHub: <https://github.com/Micro-sheep/efinance>
- qstock: <https://github.com/tkfy920/qstock>
- pytdx: <https://pytdx-docs.readthedocs.io/zh-cn/latest/pytdx_hq/>
- mootdx: <https://github.com/mootdx/mootdx>
- zvt: <https://github.com/zvtvz/zvt>
- Qlib data: <https://qlib.readthedocs.io/en/v0.6.2/component/data.html>
- JQData SDK: <https://github.com/JoinQuant/jqdatasdk>
- RQData docs: <https://www.ricequant.com/doc/rqdata/python/index-rqdatac>
