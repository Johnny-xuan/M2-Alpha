"""Build docs/data/data.json from the audited historical benchmark engine.

This generator is for the public historical-backtest website surface. It reuses
the same prediction, strategy, share/cash accounting, fees, and signal-lag
semantics as ``scripts/benchmark_research.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from model_versions import MODEL_VERSIONS, DEFAULT_MODEL_LABEL, get_model_version, model_keys
from m2alpha.benchmark import (
    BenchmarkConfig,
    ResearchTopNStrategy,
    historical_predict,
    load_industry_map,
    prepare_benchmark_panel,
    run_research_backtest,
    summarize_backtest,
    validate_benchmark_alignment,
)
from scripts.benchmark_research import _make_synthetic_panel


DATA_JSON = ROOT / "docs" / "data" / "data.json"
DEFAULT_PANEL = HERE / "cache" / "panel.parquet"
DEFAULT_BENCHMARK = HERE / "cache" / "csi300.parquet"
DEFAULT_INDUSTRY = HERE / "cache" / "basic.csv"
INITIAL_NAV = 1_000_000.0


def fmt_date(value: str) -> str:
    s = str(value)
    if "-" in s:
        return s[:10]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def compact_date(value: str) -> str:
    return str(value).replace("-", "")[:8]


def strategy_description(config: BenchmarkConfig) -> str:
    max_per_industry = max(1, int(config.n_hold * config.max_industry_frac))
    return (
        f"dynamic top1000 · n={config.n_hold} · "
        f"max {max_per_industry} names/industry · "
        f"pool_rank={config.pool_rank} (recorded) · "
        f"sell_rank={config.sell_rank} · {config.exec_price} execution · "
        f"fee_rate={config.fee_rate}"
    )


def read_panel(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        panel = pd.read_csv(path, dtype={"trade_date": str, "ts_code": str})
    else:
        panel = pd.read_parquet(path)
    panel["trade_date"] = panel["trade_date"].astype(str)
    if "ts_code" not in panel.columns and "code" in panel.columns:
        panel["ts_code"] = panel["code"].astype(str)
    return panel


def read_benchmark(path: Path | None, panel: pd.DataFrame) -> pd.DataFrame:
    if path and path.exists():
        if path.suffix.lower() == ".csv":
            bench = pd.read_csv(path, dtype={"trade_date": str})
        else:
            bench = pd.read_parquet(path)
        bench["trade_date"] = bench["trade_date"].astype(str)
        return bench

    # Fallback for smoke tests: equal-weight all panel names by date.
    grouped = panel.groupby("trade_date", sort=True)["open"].mean().reset_index()
    grouped["close"] = grouped["open"]
    return grouped


def load_security_metadata(panel: pd.DataFrame, industry_file: Path | None) -> tuple[dict[str, str], dict[str, str]]:
    name_map: dict[str, str] = {}
    industry_map: dict[str, str] = {}
    if industry_file and industry_file.exists():
        meta = pd.read_csv(industry_file, dtype=str)
        if "ts_code" in meta.columns:
            if "name" in meta.columns:
                name_map.update(dict(zip(meta["ts_code"], meta["name"].fillna(meta["ts_code"]))))
            if "industry" in meta.columns:
                industry_map.update(dict(zip(meta["ts_code"], meta["industry"].fillna("NA"))))
    if "name" in panel.columns:
        p = panel[["ts_code", "name"]].dropna().drop_duplicates("ts_code")
        name_map.update(dict(zip(p["ts_code"], p["name"])))
    if "industry" in panel.columns:
        p = panel[["ts_code", "industry"]].dropna().drop_duplicates("ts_code")
        industry_map.update(dict(zip(p["ts_code"], p["industry"])))
    return name_map, industry_map


def monthly_returns(equity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not equity:
        return []
    df = pd.DataFrame(equity)
    df["month"] = df["d"].str[:7]
    rows = []
    for month, grp in df.groupby("month", sort=True):
        if len(grp) < 2:
            continue
        model = grp["nav"].iloc[-1] / grp["nav"].iloc[0] - 1
        bench = grp["bench"].iloc[-1] / grp["bench"].iloc[0] - 1
        rows.append({
            "m": month,
            "model": round(float(model * 100), 2),
            "bench": round(float(bench * 100), 2),
            "excess": round(float((model - bench) * 100), 2),
        })
    return rows


def build_equity(result, benchmark_df: pd.DataFrame, config: BenchmarkConfig) -> list[dict[str, Any]]:
    nav = result.nav.dropna().astype(float)
    if nav.empty:
        return []
    bench_col = config.nav_price or config.exec_price
    if bench_col not in benchmark_df.columns:
        bench_col = "close" if "close" in benchmark_df.columns else "open"
    bench = benchmark_df.set_index("trade_date")[bench_col].astype(float)
    bench = bench.reindex(nav.index).ffill().bfill()
    bench_start = float(bench.iloc[0]) if len(bench) else 1.0
    nav_start = float(nav.iloc[0])
    rows = []
    for d, nav_value in nav.items():
        b_value = float(bench.loc[d]) / bench_start * nav_start if bench_start else nav_start
        rows.append({
            "d": fmt_date(d),
            "nav": round(float(nav_value), 2),
            "bench": round(b_value, 2),
            "ret": round(float((nav_value / nav_start - 1) * 100), 3),
            "bret": round(float((b_value / nav_start - 1) * 100), 3),
        })
    return rows


def build_holdings_payload(
    result,
    preds: pd.DataFrame,
    panel: pd.DataFrame,
    name_map: dict[str, str],
    industry_map: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    holdings = result.holdings.copy()
    if holdings.empty:
        return [], [], []

    holdings["trade_date"] = holdings["trade_date"].astype(str)
    latest = str(holdings["trade_date"].max())
    latest_holdings = holdings[holdings["trade_date"] == latest].copy()
    latest_nav = float(result.nav.loc[latest]) if latest in result.nav.index else float(result.nav.iloc[-1])
    price = panel[panel["trade_date"] == latest].set_index("ts_code")
    pred_dates = sorted(preds["trade_date"].astype(str).unique())
    score_date = pred_dates[max(0, pred_dates.index(latest) - 1)] if latest in pred_dates else pred_dates[-1]
    pred_lookup = preds[preds["trade_date"] == score_date].set_index("ts_code")["pred"].to_dict()
    latest_holdings["score"] = latest_holdings["ts_code"].map(pred_lookup).fillna(0.0)
    latest_holdings = latest_holdings.sort_values(["score", "ts_code"], ascending=[False, True])

    current = []
    for rank, row in enumerate(latest_holdings.itertuples(index=False), 1):
        ts = row.ts_code
        px = float(price.loc[ts, "close"] if ts in price.index and "close" in price.columns else 0.0)
        value = float(row.shares) * px
        current.append({
            "rank": rank,
            "ts": ts,
            "name": name_map.get(ts, ts),
            "industry": industry_map.get(ts, "NA"),
            "score": round(float(row.score), 3),
            "close": round(px, 2),
            "shares": int(row.shares),
            "weight": round(value / latest_nav * 100, 1) if latest_nav else 0.0,
        })

    held_counter = Counter(holdings["ts_code"])
    n_days = max(1, holdings["trade_date"].nunique())
    top_held = [
        {
            "ts": ts,
            "name": name_map.get(ts, ts),
            "industry": industry_map.get(ts, "NA"),
            "days": int(days),
            "pct": round(days / n_days * 100, 1),
        }
        for ts, days in held_counter.most_common(15)
    ]

    ind_counter = Counter(industry_map.get(ts, "NA") for ts in holdings["ts_code"])
    total = max(1, sum(ind_counter.values()))
    industry_avg = [
        {"industry": ind, "weight": round(count / total * 100, 2)}
        for ind, count in ind_counter.most_common(12)
    ]
    return current, top_held, industry_avg


def build_scorecard(
    result,
    preds: pd.DataFrame,
    panel: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    name_map: dict[str, str],
    industry_map: dict[str, str],
    config: BenchmarkConfig,
) -> dict[str, Any]:
    if result.holdings.empty:
        return {"summary": {}, "recent": [], "by_date": {}, "all_dates": []}

    panel_dates = sorted(panel["trade_date"].astype(str).unique())
    date_pos = {d: i for i, d in enumerate(panel_dates)}
    open_by = panel.set_index(["trade_date", "ts_code"])["open"].astype(float)
    bench_col = config.exec_price if config.exec_price in benchmark_df.columns else "open"
    bench_open = benchmark_df.set_index("trade_date")[bench_col].astype(float)
    holdings_by_date = {
        d: g[["ts_code", "shares"]].copy()
        for d, g in result.holdings.groupby("trade_date", sort=True)
    }
    pred_lookup = preds.set_index(["trade_date", "ts_code"])["pred"]
    scorecard = []

    nav_dates = [str(d) for d in result.nav.index]
    for i in range(1, len(nav_dates)):
        signal_d = nav_dates[i - 1]
        buy_d = nav_dates[i]
        if buy_d not in date_pos:
            continue
        sell_i = date_pos[buy_d] + 1
        if sell_i >= len(panel_dates):
            continue
        sell_d = panel_dates[sell_i]
        holdings = holdings_by_date.get(buy_d)
        if holdings is None or holdings.empty:
            continue

        picks = []
        returns = []
        for row in holdings.itertuples(index=False):
            ts = row.ts_code
            o1 = open_by.get((buy_d, ts))
            o2 = open_by.get((sell_d, ts))
            rr = None
            if o1 is not None and o2 is not None and o1 > 0:
                rr = (float(o2) / float(o1) - 1) * 100
                returns.append(rr)
            score = pred_lookup.get((signal_d, ts), 0.0)
            picks.append({
                "ts": ts,
                "name": name_map.get(ts, ts),
                "ind": industry_map.get(ts, "NA"),
                "score": round(float(score), 3),
                "ret": round(float(rr), 2) if rr is not None else None,
            })

        if not returns:
            continue
        bo1 = bench_open.get(buy_d)
        bo2 = bench_open.get(sell_d)
        bench_ret = (float(bo2) / float(bo1) - 1) * 100 if bo1 and bo2 else None
        avg_ret = float(np.mean(returns))
        excess = avg_ret - bench_ret if bench_ret is not None else None
        hits = sum(1 for rr in returns if bench_ret is not None and rr > bench_ret)
        portfolio_codes = set(holdings["ts_code"].astype(str))
        ranked = (
            preds[preds["trade_date"] == signal_d]
            .sort_values(["pred", "ts_code"], ascending=[False, True], kind="stable")
            .head(30)
        )
        top30 = []
        for rank, row in enumerate(ranked.itertuples(index=False), 1):
            ts = str(row.ts_code)
            o1 = open_by.get((buy_d, ts))
            o2 = open_by.get((sell_d, ts))
            raw_ret = None
            if o1 is not None and o2 is not None and o1 > 0:
                raw_ret = (float(o2) / float(o1) - 1) * 100
            top30.append({
                "rank": rank,
                "ts": ts,
                "name": name_map.get(ts, ts),
                "ind": industry_map.get(ts, "NA"),
                "score": round(float(row.pred), 3),
                "ret": round(float(raw_ret), 2) if raw_ret is not None else None,
                "in_portfolio": ts in portfolio_codes,
            })
        day = {
            "d": fmt_date(signal_d),
            "buy_d": fmt_date(buy_d),
            "sell_d": fmt_date(sell_d),
            "avg_ret": round(avg_ret, 2),
            "bench_ret": round(float(bench_ret), 2) if bench_ret is not None else None,
            "excess": round(float(excess), 2) if excess is not None else None,
            "hits": int(hits),
            "n": int(len(returns)),
            "hit_rate": round(hits / len(returns) * 100, 1),
            "picks": picks,
            "top30": top30,
            "pending": False,
        }
        scorecard.append(day)

    arr = np.array([s["avg_ret"] for s in scorecard], dtype=float)
    bench_arr = np.array([s["bench_ret"] for s in scorecard if s["bench_ret"] is not None], dtype=float)
    excess_arr = np.array([s["excess"] for s in scorecard if s["excess"] is not None], dtype=float)
    hit_arr = np.array([s["hit_rate"] for s in scorecard], dtype=float)
    summary = {
        "n_days_total": int(len(scorecard)),
        "n_pending": 0,
        "model_avg_daily": round(float(arr.mean()), 3) if len(arr) else 0.0,
        "bench_avg_daily": round(float(bench_arr.mean()), 3) if len(bench_arr) else 0.0,
        "excess_avg": round(float(excess_arr.mean()), 3) if len(excess_arr) else 0.0,
        "win_rate_vs_bench_daily": round(float((excess_arr > 0).mean() * 100), 1) if len(excess_arr) else 0.0,
        "avg_hit_rate": round(float(hit_arr.mean()), 1) if len(hit_arr) else 0.0,
        "best_day": {
            "d": scorecard[int(np.argmax(arr))]["d"],
            "ret": round(float(arr.max()), 2),
        } if len(arr) else None,
        "worst_day": {
            "d": scorecard[int(np.argmin(arr))]["d"],
            "ret": round(float(arr.min()), 2),
        } if len(arr) else None,
    }
    return {
        "summary": summary,
        "recent": scorecard[-10:],
        "by_date": {s["d"]: s for s in scorecard},
        "all_dates": [
            {
                "d": s["d"],
                "avg": s["avg_ret"],
                "bench": s["bench_ret"],
                "excess": s["excess"],
                "hit": s["hit_rate"],
            }
            for s in scorecard
        ],
    }


def build_model_payload(
    version,
    preds: pd.DataFrame,
    result,
    summary: dict[str, Any],
    panel: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    name_map: dict[str, str],
    industry_map: dict[str, str],
    config: BenchmarkConfig,
) -> dict[str, Any]:
    equity = build_equity(result, benchmark_df, config)
    monthly = monthly_returns(equity)
    current, top_held, industry_avg = build_holdings_payload(result, preds, panel, name_map, industry_map)
    scorecard = build_scorecard(result, preds, panel, benchmark_df, name_map, industry_map, config)
    bench_cum = equity[-1]["bret"] if equity else 0.0
    cum_return = float(summary["cum_return_pct"])
    months_won = sum(1 for m in monthly if (m.get("excess") or 0) > 0)
    monthly_win = months_won / len(monthly) * 100 if monthly else float(summary.get("month_win_rate", 0) * 100)
    return {
        "model": {
            **version.public_metadata(),
            "research_benchmark": {
                "label": "Research benchmark",
                "cum_pct": round(cum_return, 2),
                "sharpe": round(float(summary["sharpe"]), 3),
                "max_dd_pct": round(float(summary["max_drawdown_pct"]), 2),
                "basis": f"research engine · {strategy_description(config)}",
            },
        },
        "summary": {
            "model_key": version.key,
            "model_id": version.public_id,
            "model_label": version.label,
            "model_title": version.title,
            "asof": fmt_date(summary["end"]),
            "start": fmt_date(summary["start"]),
            "n_days": int(summary["n_days"]),
            "starting_nav": INITIAL_NAV,
            "final_nav": round(float(summary["final_nav"]), 2),
            "cum_return": round(cum_return, 2),
            "benchmark_cum": round(float(bench_cum), 2),
            "excess": round(cum_return - float(bench_cum), 2),
            "sharpe": round(float(summary["sharpe"]), 2),
            "max_drawdown": round(float(summary["max_drawdown_pct"]), 2),
            "monthly_win_rate": round(float(monthly_win), 1),
            "computed_cum_return": round(cum_return, 2),
            "computed_sharpe": round(float(summary["sharpe"]), 2),
            "computed_max_drawdown": round(float(summary["max_drawdown_pct"]), 2),
            "turnover": round(float(summary["turnover"]), 4),
            "n_trades": int(len(result.trades)),
            "total_fee": round(float(result.trades["fee"].sum()), 2) if not result.trades.empty else 0.0,
        },
        "equity_curve": equity,
        "monthly_returns": monthly,
        "current_holdings": current,
        "top_held": top_held,
        "industry_avg": industry_avg,
        "scorecard": scorecard,
        "benchmark_summary": summary,
    }


def load_existing_predictions(version, config: BenchmarkConfig) -> pd.DataFrame:
    if not version.preds_path.exists():
        raise FileNotFoundError(
            f"missing predictions for {version.label}: {version.preds_path}. "
            "Run `python build/inference.py` first or pass --historical-predict."
        )
    preds = pd.read_parquet(version.preds_path)
    preds["trade_date"] = preds["trade_date"].astype(str)
    preds["ts_code"] = preds["ts_code"].astype(str)
    preds = preds[
        (preds["trade_date"] >= config.start)
        & (preds["trade_date"] <= config.end)
    ].copy()
    if preds.empty:
        raise ValueError(f"no predictions for {version.label} in {config.start}..{config.end}")
    return preds


def run_research_backtest_set(panel: pd.DataFrame, benchmark_df: pd.DataFrame, versions, config: BenchmarkConfig,
                              industry_map: dict[str, str], name_map: dict[str, str], device: str,
                              historical_predict_mode: bool = False,
                              strategy_mode: str = "selected") -> dict[str, Any]:
    config.validate()
    base_panel = panel.copy()
    base_panel["trade_date"] = base_panel["trade_date"].astype(str)
    base_panel = base_panel[base_panel["trade_date"] <= config.end].copy()
    if historical_predict_mode:
        prepared, feature_cols = prepare_benchmark_panel(base_panel, label_basis=config.label_basis)
        seg = prepared[(prepared["trade_date"] >= config.start) & (prepared["trade_date"] <= config.end)].copy()
    else:
        prepared, feature_cols = None, []
        seg = base_panel[(base_panel["trade_date"] >= config.start) & (base_panel["trade_date"] <= config.end)].copy()

    models = {}
    for version in versions:
        version_config = (
            replace(config, **version.selected_strategy)
            if strategy_mode == "selected"
            else config
        )
        version_config.validate()
        print(f"[historical-backtest] {version.label} {version.checkpoint}")
        if historical_predict_mode:
            preds = historical_predict(
                prepared,
                feature_cols,
                version.checkpoint,
                start=version_config.start,
                end=version_config.end,
                tau=version_config.tau,
                device=device,
                min_stocks_per_day=version_config.min_stocks_per_day,
            )
            prediction_path = "m2alpha.benchmark.historical_predict"
        else:
            preds = load_existing_predictions(version, version_config)
            prediction_path = str(version.preds_path)
        strategy = ResearchTopNStrategy(
            n_hold=version_config.n_hold,
            pool_rank=version_config.pool_rank,
            sell_rank=version_config.sell_rank,
            industry_map=industry_map,
            max_industry_frac=version_config.max_industry_frac,
        )
        result = run_research_backtest(
            preds,
            seg,
            strategy,
            init_cash=version_config.init_cash,
            fee_rate=version_config.fee_rate,
            lot_size=version_config.lot_size,
            exec_price=version_config.exec_price,
            nav_price=version_config.nav_price,
        )
        summary = summarize_backtest(result)
        summary["alignment"] = validate_benchmark_alignment(preds, result)
        summary["config"] = asdict(version_config)
        summary["strategy_mode"] = strategy_mode
        summary["n_predictions"] = int(len(preds))
        summary["n_prediction_dates"] = int(preds["trade_date"].nunique())
        summary["first_prediction_date"] = str(preds["trade_date"].min())
        summary["last_prediction_date"] = str(preds["trade_date"].max())
        summary["checkpoint"] = str(version.checkpoint)
        summary["prediction_path"] = prediction_path
        summary["model"] = version.label
        summary["model_key"] = version.key
        models[version.key] = build_model_payload(
            version,
            preds,
            result,
            summary,
            base_panel,
            benchmark_df,
            name_map,
            industry_map,
            version_config,
        )
        print(
            f"  {summary['start']}->{summary['end']} "
            f"cum={summary['cum_return_pct']:+.2f}% "
            f"sharpe={summary['sharpe']:.3f} "
            f"mdd={summary['max_drawdown_pct']:+.2f}%"
        )
    return models


def build_data_json(models: dict[str, Any], args: argparse.Namespace, config: BenchmarkConfig) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if DATA_JSON.exists():
        try:
            existing = json.loads(DATA_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    fallback_model = max(models, key=lambda key: models[key]["summary"]["cum_return"])
    fallback_payload = models[fallback_model]
    baseline_keys = [
        "summary",
        "equity_curve",
        "monthly_returns",
        "current_holdings",
        "top_held",
        "industry_avg",
        "scorecard",
    ]
    baseline_payload = {
        key: existing.get(key, fallback_payload.get(key))
        for key in baseline_keys
        if existing.get(key, fallback_payload.get(key)) is not None
    }
    baseline_model = existing.get("model") or {
        "key": "m0m",
        "label": "M-0-M",
        "title": "M-0-M · current public baseline",
        "role": "stable public baseline currently shown on GitHub Pages",
    }

    curve_order = [version.key for version in MODEL_VERSIONS if version.key in models]
    backtest_curves = []
    for key in curve_order:
        payload = models[key]
        summary = dict(payload["summary"])
        curve_config = BenchmarkConfig(**payload["benchmark_summary"]["config"])
        summary["source_model"] = f"{payload['model']['label']} {payload['model']['lineage']}"
        backtest_curves.append({
            "key": key,
            "label": payload["model"]["label"],
            "title": payload["model"]["title"],
            "kind": "historical_research_curve",
            "source_model": summary["source_model"],
            "cutoff_note": "Frozen full-factor research curve; not a daily recommendation.",
            "strategy": strategy_description(curve_config),
            "summary": summary,
            "equity_curve": payload["equity_curve"],
            "monthly_returns": payload["monthly_returns"],
        })

    research_references = {
        key: {
            "model_label": payload["model"]["label"],
            "model_title": payload["model"]["title"],
            "role": payload["model"]["role"],
            **payload["model"]["research_benchmark"],
        }
        for key, payload in models.items()
    }
    highlight_key = "m2m" if "m2m" in research_references else curve_order[-1]
    highlight = research_references[highlight_key]
    return {
        **baseline_payload,
        "schema_version": 3,
        "surface": "historical_backtest",
        "model": baseline_model,
        "backtest_curves": backtest_curves,
        "backtest_curve_order": curve_order,
        "backtest_curve_note": "M-1-M and M-2-M are frozen full-factor research curves. They are not daily updated portfolio recommendations.",
        "data_sources": {
            "base_source": "local research panel",
            "panel": "local research-grade dynamic top1000 panel (not distributed in the public site payload)",
            "benchmark_index": "CSI300 benchmark series from the same local research cache" if args.benchmark_index else None,
            "industry_file": "local research basic.csv industry map" if args.industry_file else None,
            "policy": (
                "Main website metrics are generated with the audited M2 research "
                "backtest engine on the local research panel. The public repository "
                "ships the generated historical result payload; rebuilding the exact "
                "numbers requires a compatible research-grade panel."
            ),
        },
        "registry_default_model": DEFAULT_MODEL_LABEL,
        "strategy": {
            "name": (
                "model_specific_selected_strategies"
                if args.strategy_mode == "selected"
                else "fixed_protocol"
            ),
            "mode": args.strategy_mode,
            "universe": "dynamic top1000 historical panel",
            "models": {
                key: payload["benchmark_summary"]["config"]
                for key, payload in models.items()
            },
            "execution": "prediction date D, trade at next session open through prev_pred signal lag",
            "costs": f"fee_rate={config.fee_rate}",
            "nav_price": config.nav_price or config.exec_price,
            "label_basis": config.label_basis,
        },
        "research_references": research_references,
        "research_highlight": {
            "model_key": highlight_key,
            **highlight,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build website data from the historical research backtest engine.")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--benchmark-index", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--industry-file", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DATA_JSON)
    parser.add_argument("--model", default="all", choices=["all", *model_keys()])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--start", default="20250710")
    parser.add_argument("--end", default=None, help="YYYYMMDD; default uses the latest date in --panel")
    parser.add_argument("--tau", type=int, default=8)
    parser.add_argument("--label-basis", choices=["close", "open"], default="close")
    parser.add_argument("--n-hold", type=int, default=5)
    parser.add_argument("--pool-rank", type=int, default=100)
    parser.add_argument("--sell-rank", type=int, default=200)
    parser.add_argument("--max-industry-frac", type=float, default=0.2)
    parser.add_argument("--fee-rate", type=float, default=0.0013)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--exec-price", choices=["open", "close"], default="open")
    parser.add_argument("--nav-price", choices=["open", "close"], default=None)
    parser.add_argument("--min-stocks-per-day", type=int, default=30)
    parser.add_argument(
        "--strategy-mode",
        choices=["selected", "fixed"],
        default="selected",
        help=(
            "selected uses each checkpoint's registered strategy; fixed applies "
            "the CLI strategy arguments to every checkpoint"
        ),
    )
    parser.add_argument(
        "--historical-predict",
        action="store_true",
        help="recompute predictions with m2alpha.benchmark.historical_predict instead of using build/cache preds",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.self_test:
        panel = _make_synthetic_panel(n_stocks=80, n_days=55)
        args.start = "20250701"
        benchmark = read_benchmark(None, panel)
        versions = (get_model_version("M-1-M"),)
        name_map, meta_industry_map = load_security_metadata(panel, None)
        industry_map = load_industry_map(panel, None) or meta_industry_map
    else:
        if not args.panel.exists():
            raise FileNotFoundError(f"research panel not found: {args.panel}")
        panel = read_panel(args.panel)
        benchmark = read_benchmark(args.benchmark_index, panel)
        versions = MODEL_VERSIONS if args.model == "all" else (get_model_version(args.model),)
        name_map, meta_industry_map = load_security_metadata(panel, args.industry_file)
        industry_map = load_industry_map(panel, args.industry_file) or meta_industry_map

    end = args.end or str(panel["trade_date"].max())
    config = BenchmarkConfig(
        start=args.start,
        end=end,
        tau=args.tau,
        label_basis=args.label_basis,
        n_hold=args.n_hold,
        pool_rank=args.pool_rank,
        sell_rank=args.sell_rank,
        max_industry_frac=args.max_industry_frac,
        fee_rate=args.fee_rate,
        lot_size=args.lot_size,
        exec_price=args.exec_price,
        nav_price=args.nav_price,
        init_cash=INITIAL_NAV,
        min_stocks_per_day=args.min_stocks_per_day,
    )

    historical_predict_mode = args.historical_predict or args.self_test
    models = run_research_backtest_set(
        panel,
        benchmark,
        versions,
        config,
        industry_map,
        name_map,
        args.device,
        historical_predict_mode=historical_predict_mode,
        strategy_mode=args.strategy_mode,
    )
    data = build_data_json(models, args, config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] saved {args.out}")
    for key, payload in models.items():
        s = payload["summary"]
        print(f"  {payload['model']['label']}: {s['cum_return']:+.2f}% Sharpe {s['sharpe']:.2f}")


if __name__ == "__main__":
    main()
