"""Run the M2-Alpha research benchmark on a user-supplied historical panel."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "build"))

from model_versions import MODEL_VERSIONS, get_model_version, model_keys
from m2alpha.benchmark import (
    BenchmarkConfig,
    load_industry_map,
    run_benchmark_for_checkpoint,
    write_benchmark_outputs,
)


def _make_synthetic_panel(n_stocks: int = 80, n_days: int = 50) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2025-07-01", periods=n_days).strftime("%Y%m%d").tolist()
    codes = [f"{600000 + i:06d}.SH" for i in range(n_stocks)]
    industries = [f"industry_{i % 12:02d}" for i in range(n_stocks)]
    rows = []
    for code, industry in zip(codes, industries):
        price = 10.0 + rng.random() * 20
        for d in dates:
            ret = rng.normal(0.0008, 0.018)
            open_px = max(1.0, price * (1 + rng.normal(0, 0.004)))
            close = max(1.0, open_px * (1 + ret))
            high = max(open_px, close) * (1 + abs(rng.normal(0, 0.006)))
            low = min(open_px, close) * (1 - abs(rng.normal(0, 0.006)))
            vol = float(rng.integers(100_000, 5_000_000))
            amount = vol * close / 1000.0
            rows.append({
                "trade_date": d,
                "ts_code": code,
                "industry": industry,
                "open": open_px,
                "high": high,
                "low": low,
                "close": close,
                "pre_close": price,
                "pct_chg": (close / price - 1) * 100,
                "vol": vol,
                "amount": amount,
                "vwap": (open_px + high + low + close) / 4,
                "turnover_rate": rng.uniform(0.2, 5.0),
                "turnover_rate_f": rng.uniform(0.2, 5.5),
                "volume_ratio": rng.uniform(0.5, 2.5),
                "pe_ttm": rng.uniform(5, 60),
                "pb": rng.uniform(0.5, 8),
                "ps_ttm": rng.uniform(0.5, 20),
                "net_mf_amount": rng.normal(0, 500),
                "buy_sm_amount": rng.uniform(100, 2000),
                "buy_lg_amount": rng.uniform(50, 1500),
                "buy_elg_amount": rng.uniform(20, 1000),
            })
            price = close
    return pd.DataFrame(rows)


def _config_from_args(args: argparse.Namespace) -> BenchmarkConfig:
    return BenchmarkConfig(
        start=args.start,
        end=args.end,
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
        init_cash=args.init_cash,
        min_stocks_per_day=args.min_stocks_per_day,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the historical M2-Alpha research benchmark. This is not the "
            "public baseline display; it expects a research-grade panel."
        )
    )
    parser.add_argument("--panel", help="historical panel parquet/csv with DATA_SCHEMA columns")
    parser.add_argument("--industry-file", help="optional csv with ts_code and industry columns")
    parser.add_argument("--model", default="all", choices=["all", *model_keys()])
    parser.add_argument("--out-dir", default="outputs/benchmark")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--start", default="20250701")
    parser.add_argument("--end", default="20260525")
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
    parser.add_argument("--init-cash", type=float, default=1_000_000.0)
    parser.add_argument("--min-stocks-per-day", type=int, default=30)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run a synthetic smoke check using the public M-1-M checkpoint",
    )
    args = parser.parse_args()

    if args.self_test:
        panel = _make_synthetic_panel()
        args.start = "20250701"
        args.end = panel["trade_date"].max()
        args.model = "M-1-M"
    else:
        if not args.panel:
            parser.error("--panel is required unless --self-test is used")
        path = Path(args.panel)
        if path.suffix.lower() == ".csv":
            panel = pd.read_csv(path, dtype={"trade_date": str, "ts_code": str})
        else:
            panel = pd.read_parquet(path)

    panel["trade_date"] = panel["trade_date"].astype(str)
    industry_map = load_industry_map(panel, args.industry_file)
    if not industry_map:
        print("[warn] no industry map found; industry cap will relax through fallback")

    config = _config_from_args(args)
    versions = MODEL_VERSIONS if args.model == "all" else (get_model_version(args.model),)
    summaries = {}
    for version in versions:
        print(f"[benchmark] {version.label} {version.checkpoint}")
        preds, result, summary = run_benchmark_for_checkpoint(
            panel,
            version.checkpoint,
            config,
            industry_map=industry_map,
            device=args.device,
        )
        summary["model"] = version.label
        summary["model_key"] = version.key
        summaries[version.key] = summary
        write_benchmark_outputs(
            args.out_dir,
            key=version.key,
            predictions=preds,
            result=result,
            summary=summary,
        )
        print(
            "  "
            f"{summary['start']}->{summary['end']} "
            f"cum={summary['cum_return_pct']:+.2f}% "
            f"sharpe={summary['sharpe']:.3f} "
            f"mdd={summary['max_drawdown_pct']:+.2f}% "
            f"turnover={summary['turnover']:.3f}"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "summary_all.json").open("w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    print(f"[OK] benchmark outputs written to {out_dir}")


if __name__ == "__main__":
    main()
