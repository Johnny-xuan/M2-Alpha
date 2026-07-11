"""Refresh only the M-0-M website baseline with the audited benchmark engine.

The public M-0-M checkpoint uses the audited research engine with its selected
Top-7 / sell-rank-35 / max-three-per-industry strategy. Signal lag, share/cash
accounting, fees, and tradability match the benchmark engine. Frozen M-1-M and
M-2-M research curves are preserved byte-for-byte at JSON value level.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from m2alpha.benchmark import (
    BenchmarkConfig,
    ResearchTopNStrategy,
    build_tradability_map,
    load_industry_map,
    run_research_backtest,
    summarize_backtest,
)
from update_backtest_site import (
    build_equity,
    build_scorecard,
    load_security_metadata,
    monthly_returns,
)

CACHE = HERE / "cache"
DATA_JSON = ROOT / "docs" / "data" / "data.json"
PANEL = CACHE / "panel.parquet"
PREDS = CACHE / "preds_m0m.parquet"
CSI300 = CACHE / "csi300.parquet"
BASIC = CACHE / "basic.csv"
INDUSTRY_MAP = HERE / "industry_map.csv"

START_DATE = "20250710"
INITIAL_NAV = 1_000_000.0


def compact_date(value: str) -> str:
    return str(value).replace("-", "")[:8]


def display_date(value: str | None) -> str | None:
    if not value:
        return None
    value = compact_date(value)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def read_existing_payload() -> dict:
    if not DATA_JSON.exists():
        return {}
    try:
        return json.loads(DATA_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"existing website payload is not valid JSON: {DATA_JSON}") from exc


def build_next_target(
    result,
    strategy: ResearchTopNStrategy,
    preds: pd.DataFrame,
    panel: pd.DataFrame,
    name_map: dict[str, str],
    industry_map: dict[str, str],
) -> list[dict]:
    """Build the next-session target from the latest close signal."""
    latest = str(preds["trade_date"].max())
    day_panel = panel[panel["trade_date"] == latest].set_index("ts_code")
    scores = dict(
        zip(
            preds.loc[preds["trade_date"] == latest, "ts_code"],
            preds.loc[preds["trade_date"] == latest, "pred"],
        )
    )
    held = result.holdings[result.holdings["trade_date"] == latest]
    portfolio = dict(zip(held["ts_code"], held["shares"]))
    target = strategy.decide(
        latest,
        portfolio,
        scores,
        build_tradability_map(day_panel),
    )
    ranked = sorted(target, key=lambda ts: (-float(scores.get(ts, -1e9)), ts))
    rows = []
    for rank, ts in enumerate(ranked, 1):
        px = 0.0
        if ts in day_panel.index and "close" in day_panel.columns:
            px = float(day_panel.loc[ts, "close"])
        rows.append({
            "rank": rank,
            "ts": ts,
            "name": name_map.get(ts, ts),
            "industry": industry_map.get(ts, "NA"),
            "score": round(float(scores.get(ts, 0.0)), 3),
            "close": round(px, 2),
            "weight": round(float(target[ts]) * 100, 1),
        })
    return rows


def replace_m0_curve(existing: dict, summary: dict, equity: list, monthly: list) -> list[dict]:
    curve = {
        "key": "m0m",
        "label": "M-0-M",
        "title": "M-0-M · trading-day public baseline",
        "kind": "public_baseline",
        "source_model": "M-0-M public baseline checkpoint",
        "cutoff_note": "Updated after each validated A-share trading session.",
        "strategy": "CSI300 · top7 · sell_rank=35 · max 3 names/industry · open execution · fee_rate=0.0013",
        "summary": summary,
        "equity_curve": equity,
        "monthly_returns": monthly,
    }
    research = [item for item in existing.get("backtest_curves", []) if item.get("key") != "m0m"]
    return [curve, *research]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the M-0-M baseline with the research benchmark engine."
    )
    parser.add_argument(
        "--expected-trade-date",
        default=None,
        help="Fail unless panel and predictions end on this YYYYMMDD session.",
    )
    parser.add_argument(
        "--next-trading-day",
        default=None,
        help="Validated next A-share session for the public navigation label.",
    )
    args = parser.parse_args()

    t0 = datetime.now()
    print(f"[M-0-M baseline] {t0:%Y-%m-%d %H:%M:%S}  (benchmark engine)")

    preds = pd.read_parquet(PREDS)
    panel = pd.read_parquet(PANEL)
    benchmark = pd.read_parquet(CSI300)
    for frame in (preds, panel, benchmark):
        frame["trade_date"] = frame["trade_date"].astype(str)
    preds["ts_code"] = preds["ts_code"].astype(str)
    panel["ts_code"] = panel["ts_code"].astype(str)

    if args.expected_trade_date:
        expected = compact_date(args.expected_trade_date)
        panel_max = compact_date(panel["trade_date"].max())
        preds_max = compact_date(preds["trade_date"].max())
        if panel_max != expected or preds_max != expected:
            raise ValueError(
                "refusing stale baseline update: "
                f"expected {expected}, panel={panel_max}, predictions={preds_max}"
            )

    end = str(preds["trade_date"].max())
    preds = preds[(preds["trade_date"] >= START_DATE) & (preds["trade_date"] <= end)].copy()
    config = BenchmarkConfig(
        start=START_DATE,
        end=end,
        n_hold=7,
        pool_rank=100,
        sell_rank=35,
        max_industry_frac=3 / 7,
        fee_rate=0.0013,
        lot_size=100,
        exec_price="open",
        nav_price="open",
        init_cash=INITIAL_NAV,
    )
    config.validate()

    primary_names, primary_industry = load_security_metadata(panel, INDUSTRY_MAP)
    names, metadata_industry = load_security_metadata(panel, BASIC)
    name_map = {**primary_names, **names}
    industry_map = {
        **primary_industry,
        **load_industry_map(panel, INDUSTRY_MAP),
        **metadata_industry,
        **load_industry_map(panel, BASIC),
    }
    strategy = ResearchTopNStrategy(
        n_hold=config.n_hold,
        pool_rank=config.pool_rank,
        sell_rank=config.sell_rank,
        industry_map=industry_map,
        max_industry_frac=config.max_industry_frac,
    )
    result = run_research_backtest(
        preds,
        panel,
        strategy,
        init_cash=config.init_cash,
        fee_rate=config.fee_rate,
        lot_size=config.lot_size,
        exec_price=config.exec_price,
        nav_price=config.nav_price,
    )
    research_summary = summarize_backtest(result)
    equity = build_equity(result, benchmark, config)
    monthly = monthly_returns(equity)
    scorecard = build_scorecard(
        result,
        preds,
        panel,
        benchmark,
        name_map,
        industry_map,
        config,
    )
    current_holdings = build_next_target(
        result,
        strategy,
        preds,
        panel,
        name_map,
        industry_map,
    )

    holdings = result.holdings.copy()
    held_count = holdings["ts_code"].value_counts()
    n_holding_days = max(1, holdings["trade_date"].nunique())
    top_held = [
        {
            "ts": ts,
            "name": name_map.get(ts, ts),
            "industry": industry_map.get(ts, "NA"),
            "days": int(days),
            "pct": round(float(days) / n_holding_days * 100, 1),
        }
        for ts, days in held_count.head(15).items()
    ]
    industry_count = holdings["ts_code"].map(lambda ts: industry_map.get(ts, "NA")).value_counts()
    total_industry = max(1, int(industry_count.sum()))
    industry_avg = [
        {"industry": industry, "weight": round(int(count) / total_industry * 100, 2)}
        for industry, count in industry_count.head(12).items()
    ]

    bench_cum = equity[-1]["bret"] if equity else 0.0
    cum_return = float(research_summary["cum_return_pct"])
    months_won = sum(1 for row in monthly if (row.get("excess") or 0) > 0)
    monthly_win = months_won / len(monthly) * 100 if monthly else 0.0
    summary = {
        "asof": display_date(research_summary["end"]),
        "start": display_date(research_summary["start"]),
        "n_days": int(research_summary["n_days"]),
        "starting_nav": INITIAL_NAV,
        "final_nav": round(float(research_summary["final_nav"]), 2),
        "cum_return": round(cum_return, 2),
        "benchmark_cum": round(float(bench_cum), 2),
        "excess": round(cum_return - float(bench_cum), 2),
        "sharpe": round(float(research_summary["sharpe"]), 2),
        "max_drawdown": round(float(research_summary["max_drawdown_pct"]), 2),
        "monthly_win_rate": round(float(monthly_win), 1),
        "computed_cum_return": round(cum_return, 2),
        "computed_sharpe": round(float(research_summary["sharpe"]), 2),
        "computed_max_drawdown": round(float(research_summary["max_drawdown_pct"]), 2),
        "turnover": round(float(research_summary["turnover"]), 4),
        "n_trades": int(len(result.trades)),
        "total_fee": round(float(result.trades["fee"].sum()), 2) if not result.trades.empty else 0.0,
    }

    existing = read_existing_payload()
    data = dict(existing)
    data.update({
        "summary": summary,
        "equity_curve": equity,
        "monthly_returns": monthly,
        "current_holdings": current_holdings,
        "top_held": top_held,
        "industry_avg": industry_avg,
        "scorecard": scorecard,
    })
    data["schema_version"] = 3
    data["surface"] = "public_baseline_with_research_backtests"
    data["model"] = {
        "key": "m0m",
        "label": "M-0-M",
        "title": "M-0-M · current public baseline",
        "role": "trading-day refreshed public baseline",
    }
    data["backtest_curves"] = replace_m0_curve(existing, summary, equity, monthly)
    data["backtest_curve_order"] = [
        "m0m",
        *[curve["key"] for curve in data["backtest_curves"] if curve["key"] != "m0m"],
    ]
    next_trade_day = display_date(args.next_trading_day) or existing.get("next_trading_day")
    if next_trade_day:
        data["next_trading_day"] = next_trade_day
    data["baseline_update"] = {
        "label": "M-0-M trading-day baseline",
        "asof": summary["asof"],
        "next_trading_day": next_trade_day,
        "engine": "m2alpha.benchmark.run_research_backtest",
    }
    data["public_baseline"] = {
        "universe": "CSI300",
        "portfolio_size": 7,
        "pool_rank": 100,
        "sell_rank": 35,
        "max_industry_frac": 3 / 7,
        "max_per_industry": 3,
        "signal": "D close",
        "execution": "D+1 open",
        "nav_price": "open",
        "fee_rate": 0.0013,
    }
    sources = dict(existing.get("data_sources") or {})
    sources["m0m"] = "BaoStock public CSI300 panel through the latest validated A-share session"
    data["data_sources"] = sources
    existing_strategy = existing.get("strategy") or {}
    if existing_strategy.get("name") == "model_specific_selected_strategies":
        data["research_strategy"] = existing_strategy
    elif existing.get("research_strategy"):
        data["research_strategy"] = existing["research_strategy"]
    data["strategy"] = {
        "name": "m0_top7_industry3_lag35",
        "universe": "CSI300 public baseline panel",
        "n_hold": 7,
        "pool_rank": 100,
        "sell_rank": 35,
        "max_industry_frac": 3 / 7,
        "max_per_industry": 3,
        "execution": "prediction date D, trade at next session open through prev_pred signal lag",
        "costs": "fee_rate=0.0013",
        "nav_price": "open",
    }
    data["strategy_policy"] = {
        "shared_contract": (
            "m2alpha.benchmark.run_research_backtest; D signal to D+1 open; "
            "open NAV; equal weight; fee_rate=0.0013"
        ),
        "selection": (
            "portfolio size, sell band, and industry constraint are "
            "checkpoint-level hyperparameters selected on declared historical sweeps"
        ),
        "models": {
            "m0m": {
                "n_hold": 7,
                "pool_rank": 100,
                "sell_rank": 35,
                "max_per_industry": 3,
                "universe": "CSI300 public baseline panel",
            },
            "m1m": {
                "n_hold": 5,
                "pool_rank": 100,
                "sell_rank": 200,
                "max_industry_frac": 0.2,
                "universe": "compatible full-factor top1000 panel",
            },
            "m2m": {
                "n_hold": 5,
                "pool_rank": 100,
                "sell_rank": 50,
                "max_industry_frac": 0.6,
                "max_per_industry": 3,
                "universe": "compatible full-factor top1000 panel",
            },
        },
    }

    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"  {research_summary['start']}->{research_summary['end']} "
        f"cum={research_summary['cum_return_pct']:+.2f}% "
        f"sharpe={research_summary['sharpe']:.3f} "
        f"mdd={research_summary['max_drawdown_pct']:+.2f}% "
        f"next_target={len(current_holdings)}"
    )
    print(f"[OK] saved {DATA_JSON} ({(datetime.now() - t0).total_seconds():.1f}s)")


if __name__ == "__main__":
    main()
