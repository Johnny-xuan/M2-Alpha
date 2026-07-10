# Contributing

M2-Alpha is a research-to-reproduction repository. Contributions are welcome when they improve reproducibility, documentation clarity, data-source transparency, or the public benchmark pipeline.

This project is not a stock recommendation service. Please do not open issues asking for trading advice, portfolio allocation, or predictions for a specific account.

## Good Contribution Areas

- Reproduction fixes for documented commands.
- Documentation improvements that clarify method, data, model, or metric basis.
- Data-source audits or optional adapters that make feature coverage more explicit.
- Bug fixes in the benchmark pipeline, static website, model loading, or baseline training path.
- Small tests or scripts that make the public release easier to verify.

## Data And Privacy

Do not submit private data, API tokens, local file paths, server names, or raw third-party historical panels unless redistribution is clearly allowed.

For optional data-source work, first build a candidate panel and run:

```bash
python scripts/audit_data_source_fields.py \
  --panel baostock=build/cache/panel.parquet \
  --panel candidate=/path/to/candidate_panel.parquet
```

Column names alone are not enough. The audit should show whether `volume_ratio`, free-float turnover, valuation fields, and money-flow inputs are active over the intended date range.

## Local Checks

For documentation-only changes:

```bash
git diff --check
```

For code or pipeline changes:

```bash
python -m compileall -q build m2alpha scripts
python build/inference.py --model M-2-M --out /tmp/M-2-M_predictions.parquet --device cpu
python build/update_backtest_site.py
python scripts/train_baseline.py --smoke --out /tmp/m2alpha_smoke.pt --device cpu
```

If you change the technical report, rebuild it with:

```bash
docs/report/build.sh
```

## Pull Request Notes

In a pull request, describe:

- what changed;
- which commands you ran;
- whether public metrics, model checkpoints, data-source fields, or report numbers changed;
- any remaining caveats.

Keep changes scoped. Avoid submitting local notebooks, scratch outputs, ignored workflow state, or unrelated refactors.
