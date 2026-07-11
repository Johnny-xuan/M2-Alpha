"""Sweep checkpoint-level portfolio parameters on a fixed prediction cache.

Generate the historical predictions once with ``scripts/benchmark_research.py``
and pass the resulting parquet here. The model weights, predictions, panel,
engine, execution, NAV accounting, and fees remain fixed; only portfolio
construction parameters change.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from m2alpha.benchmark import (  # noqa: E402
    ResearchTopNStrategy,
    load_industry_map,
    run_research_backtest,
    summarize_backtest,
)


def parse_int_list(value: str) -> list[int]:
    values = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    if not values or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("expected a comma-separated list of positive integers")
    return values


def parse_max_per_list(value: str) -> list[int | str]:
    values: list[int | str] = []
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if item in {"all", "none", "no-cap"}:
            values.append("all")
            continue
        parsed = int(item)
        if parsed <= 0:
            raise argparse.ArgumentTypeError("industry limits must be positive or 'all'")
        values.append(parsed)
    if not values:
        raise argparse.ArgumentTypeError("expected industry limits such as 1,2,3,all")
    return values


def read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype={"trade_date": str, "ts_code": str})
    else:
        frame = pd.read_parquet(path)
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame["ts_code"] = frame["ts_code"].astype(str)
    return frame


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def max_fraction(n_hold: int, max_per_industry: int) -> float:
    fraction = max_per_industry / n_hold
    if int(n_hold * fraction) != max_per_industry:
        fraction = (max_per_industry + 1e-9) / n_hold
    return fraction


def candidate_key(row: dict) -> tuple[int, int, int]:
    return int(row["n_hold"]), int(row["sell_rank"]), int(row["max_per_industry"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep model-specific portfolio parameters on fixed predictions."
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--industry-file", type=Path, required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--n-holds", type=parse_int_list, default=parse_int_list("5,7,10,15,30"))
    parser.add_argument("--sell-ranks", type=parse_int_list, default=parse_int_list("20,35,50,100,200"))
    parser.add_argument(
        "--max-per-industry",
        type=parse_max_per_list,
        default=parse_max_per_list("1,2,3,4,5,all"),
    )
    parser.add_argument(
        "--pool-rank",
        type=int,
        default=100,
        help="recorded for historical compatibility; current engine ranks the full tradable list",
    )
    parser.add_argument("--fee-rate", type=float, default=0.0013)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--exec-price", choices=["open", "close"], default="open")
    parser.add_argument("--nav-price", choices=["open", "close"], default="open")
    parser.add_argument("--init-cash", type=float, default=1_000_000.0)
    args = parser.parse_args()

    panel = read_frame(args.panel)
    predictions = read_frame(args.predictions)
    start = str(args.start or predictions["trade_date"].min())
    end = str(args.end or predictions["trade_date"].max())
    panel = panel[(panel["trade_date"] >= start) & (panel["trade_date"] <= end)].copy()
    predictions = predictions[
        (predictions["trade_date"] >= start) & (predictions["trade_date"] <= end)
    ].copy()
    if panel.empty or predictions.empty:
        raise ValueError(f"empty panel or predictions in {start}..{end}")

    industry_map = load_industry_map(panel, args.industry_file)
    payload = {
        "model_label": args.model_label,
        "panel": str(args.panel),
        "predictions": str(args.predictions),
        "industry_file": str(args.industry_file),
        "window": {"start": start, "end": end},
        "fixed_contract": {
            "engine": "m2alpha.benchmark.run_research_backtest",
            "pool_rank": args.pool_rank,
            "pool_rank_semantics": (
                "recorded for compatibility; the current research strategy ranks "
                "the full tradable list"
            ),
            "exec_price": args.exec_price,
            "nav_price": args.nav_price,
            "fee_rate": args.fee_rate,
            "lot_size": args.lot_size,
            "init_cash": args.init_cash,
        },
        "selection_note": (
            "Historical best among tested strategies; this is post-hoc strategy "
            "selection, not untouched out-of-sample evidence."
        ),
        "results": [],
    }
    if args.out.exists():
        existing = json.loads(args.out.read_text(encoding="utf-8"))
        if existing.get("model_label") != args.model_label:
            raise ValueError("refusing to resume a sweep for a different model label")
        payload["results"] = list(existing.get("results", []))

    completed = {candidate_key(row) for row in payload["results"]}
    candidates: list[tuple[int, int, int]] = []
    for n_hold in args.n_holds:
        limits = {
            n_hold if item == "all" else int(item)
            for item in args.max_per_industry
            if item == "all" or int(item) <= n_hold
        }
        for sell_rank in args.sell_ranks:
            for max_per in sorted(limits):
                key = (n_hold, sell_rank, max_per)
                if key not in completed:
                    candidates.append(key)

    total = len(completed) + len(candidates)
    print(
        f"[{args.model_label}] completed={len(completed)} pending={len(candidates)} "
        f"window={start}..{end}",
        flush=True,
    )
    for index, (n_hold, sell_rank, max_per) in enumerate(candidates, len(completed) + 1):
        max_industry_frac = max_fraction(n_hold, max_per)
        strategy = ResearchTopNStrategy(
            n_hold=n_hold,
            pool_rank=args.pool_rank,
            sell_rank=sell_rank,
            industry_map=industry_map,
            max_industry_frac=max_industry_frac,
        )
        if strategy.max_per_industry != max_per:
            raise AssertionError((n_hold, max_per, strategy.max_per_industry))
        result = run_research_backtest(
            predictions,
            panel,
            strategy,
            init_cash=args.init_cash,
            fee_rate=args.fee_rate,
            lot_size=args.lot_size,
            exec_price=args.exec_price,
            nav_price=args.nav_price,
        )
        summary = summarize_backtest(result)
        payload["results"].append({
            "n_hold": n_hold,
            "pool_rank": args.pool_rank,
            "sell_rank": sell_rank,
            "max_industry_frac": max_industry_frac,
            "max_per_industry": max_per,
            "cum_return_pct": summary["cum_return_pct"],
            "sharpe": summary["sharpe"],
            "max_drawdown_pct": summary["max_drawdown_pct"],
            "turnover": summary["turnover"],
            "n_trades": len(result.trades),
            "start": summary["start"],
            "end": summary["end"],
        })
        payload["results"].sort(
            key=lambda row: (row["cum_return_pct"], row["sharpe"]), reverse=True
        )
        payload["best_by_cumulative_return"] = payload["results"][0]
        atomic_write_json(args.out, payload)
        if index % 10 == 0 or index == total:
            best = payload["best_by_cumulative_return"]
            print(
                f"[{args.model_label}] {index:3d}/{total} "
                f"best={best['cum_return_pct']:+.2f}% n={best['n_hold']} "
                f"sell={best['sell_rank']} max_per={best['max_per_industry']}",
                flush=True,
            )

    if not payload["results"]:
        raise ValueError("strategy grid produced no candidates")
    best = payload["results"][0]
    if not math.isfinite(float(best["cum_return_pct"])):
        raise ValueError("best strategy has a non-finite cumulative return")
    print(json.dumps(best, ensure_ascii=False, indent=2))
    print(f"[OK] saved {args.out}")


if __name__ == "__main__":
    main()
