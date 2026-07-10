# Maintaining M2-Alpha

This guide is for maintainers of the M2-Alpha repository. It covers operational tasks: rebuilding public site data, regenerating predictions, and auditing data sources.

## Public Site Data

The repository no longer ships a scheduled tracking workflow. The public site is maintained as:

- `M-0-M`: stable public baseline payload in `docs/data/data.json`;
- `M-1-M`: frozen full-factor 3-block historical research curve;
- `M-2-M`: frozen full-factor 5-block historical research curve.

The manual rebuild entrypoint is:

```bash
python build/update_backtest_site.py
```

This uses the same audited historical benchmark generator as the public reproduction path.

For a full rebuild, provide a compatible panel and benchmark cache:

```bash
python build/update_backtest_site.py \
  --panel /path/to/panel_top1000.parquet \
  --benchmark-index /path/to/csi300.parquet \
  --industry-file /path/to/basic.csv \
  --model all \
  --start 20250710 \
  --n-hold 5 \
  --pool-rank 100 \
  --sell-rank 200 \
  --max-industry-frac 0.2 \
  --exec-price open \
  --fee-rate 0.0013
```

Review `docs/data/data.json` after generation. The file should remain schema version 3, preserve `M-0-M` as the baseline model, and include only `M-1-M` and `M-2-M` under `backtest_curves`.

## Data Source Boundaries

The public/open-data utilities must remain runnable without private credentials. BaoStock is the stable historical base source; AKShare and efinance are public enrichment sources for snapshot fields, source cross-checks, and best-effort enrichment. Historical `volume_ratio` can be filled by a transparent public proxy, while full historical money-flow and free-float turnover parity may require a user-supplied research panel.

Full historical training and exact frozen benchmark replication require a richer compatible panel. The source tiers and caveats are documented in [DATA_SOURCES.md](DATA_SOURCES.md). If enrichment behavior or feature availability changes, regenerate predictions, rerun the benchmark/payload build, and relabel the affected metrics.

Before changing or promoting a data source, audit the candidate panel against the current field contract:

```bash
python scripts/audit_data_source_fields.py \
  --panel baostock=build/cache/panel.parquet \
  --panel candidate=/path/to/candidate_panel.parquet
```

Do not treat a source as equivalent just because it has the right column names. The audit should show active `volume_ratio`, free-float turnover, valuation fields, and money-flow inputs over the intended date range.

Reusable raw provider responses, when present, are stored under `build/cache/source_raw/` and should stay local/ignored unless an upstream license explicitly permits redistribution.

Do not commit:

- raw third-party historical panels unless redistribution is clearly allowed;
- local experiment inventories;
- local workflow state;
- private paths, tokens, or server names;
- one-off notebooks or scratch outputs that are not part of the public reproduction path.

## Checkpoint Policy

The public website has three named lines:

| Public line | Repository role |
|---|---|
| M-0-M | Stable public baseline inherited from the current public page. |
| M-1-M | Frozen 3-block full-factor research curve, backed by `ml/m2alpha-m1m.pt`. |
| M-2-M | Frozen 5-block full-factor research curve, backed by `ml/m2alpha-m2m.pt`. |

The 4-block depth ablation can remain in report results, but it is not shipped as a public checkpoint line on the site.

To replace a public research checkpoint:

1. Replace the matching file under `ml/`.
2. Recompute the SHA-256 hash:

   ```bash
   shasum -a 256 ml/m2alpha-m2m.pt
   ```

3. Update `build/model_versions.py`.
4. Update [model_registry.yml](../model_registry.yml).
5. Rebuild predictions and the website payload:

   ```bash
   python build/inference.py --device cpu
   python build/update_backtest_site.py --panel /path/to/panel_top1000.parquet --benchmark-index /path/to/csi300.parquet --industry-file /path/to/basic.csv
   ```

6. Update docs that name the checkpoint result basis, usually [MODEL_ZOO.md](MODEL_ZOO.md), [MODEL_CARD.md](MODEL_CARD.md), [RESULTS.md](RESULTS.md), [REPRODUCTION.md](REPRODUCTION.md), and the technical report if reported numbers changed.

Checkpoint replacement changes the public evidence trail. Keep the old and new metric bases explicit.

## Technical Report

The canonical PDF report is built from `docs/report/M2Alpha_Technical_Report.tex`:

```bash
docs/report/build.sh
```

Commit the `.tex` source and `docs/report/M2Alpha_Technical_Report.pdf`. Do not commit LaTeX auxiliary files such as `.aux`, `.out`, `.toc`, `.log`, or `.synctex.gz`.

If the report changes tables, model roles, source caveats, or strategy metrics, mirror the same public facts in the Markdown docs and website copy.

## Release Checks

Before publishing a release update, run at least:

```bash
git diff --check
python -m compileall -q build m2alpha scripts
python build/inference.py --model M-2-M --out /tmp/M-2-M_predictions.parquet --device cpu
python scripts/benchmark_research.py --self-test --out-dir /tmp/m2alpha_benchmark_selftest
python scripts/train_baseline.py --smoke --out /tmp/m2alpha_smoke.pt --device cpu
```

If docs or website files changed, also serve both language entries locally:

```bash
cd docs
python3 -m http.server 8765
```

Check:

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/en.html
```

If the report changed, rebuild the PDF with `docs/report/build.sh`.

After validation, review `git status --short` and confirm every tracked change belongs to the public release. Do not commit or push ignored local workflow files.

## Troubleshooting

BaoStock update fails: rerun later before changing code. Public data providers can be temporarily unavailable.

AKShare/efinance enrichment fails: inspect `build/cache/source_enrichment.json` and rerun `python build/enrich_data.py`. The enrichment layer is best-effort; persistent failures should be documented, not hidden as model regressions.

Website payload looks stale: verify `docs/data/data.json` changed, then serve the local `docs/` directory and inspect both language entries.

Historical curve rebuild is much weaker than expected: first check that the panel has at least 60 trading days of warmup before the benchmark window and that the critical full-factor fields are active. Then confirm the strategy parameters match [REPRODUCTION.md](REPRODUCTION.md).

PDF build fails: confirm `xelatex` is installed, then rebuild from the repository root with `docs/report/build.sh`.
