"""update_daily.py — 基于仓库自有 preds.parquet **完全重建** docs/data/data.json。

设计原则（2026-05-31 重写）：
  · 仓库 100% 自洽：不再读 MASTER seed，所有展示数据 = m2alpha.pt 推理 + 仓库策略回测。
  · 策略与 MASTER 比赛配置一致：行业分散 top-10 + 滞后带（持仓掉出 top-50 才换）。
  · open(D+1) → open(D+2) 计算每日收益（T+1，开盘价成交）。
  · 未结算预测日（缺 sell_d 开盘价）标记 pending，picks 仍展示。

依赖前置脚本:
  1. python build/fetch_data.py --start 2025-06-15 --end <today>
  2. python build/inference.py
  3. python build/update_daily.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from strategy import simulate

ROOT = HERE.parent
CACHE = HERE / "cache"
DATA_JSON = ROOT / "docs" / "data" / "data.json"
PANEL = CACHE / "panel.parquet"
PREDS = CACHE / "preds.parquet"
CSI300 = CACHE / "csi300.parquet"
BASIC = CACHE / "basic.csv"

INITIAL_NAV = 1_000_000.0
N_HOLD = 10
MAX_PER_INDUSTRY = 2
HOLD_THRESHOLD = 50      # 持仓掉出 top-50 才换
START_SIGNAL_DATE = "20250710"   # 网站展示起点（业绩历史从此日 +1 开始算）


def main():
    t0 = datetime.now()
    print(f"[update_daily] {t0.strftime('%Y-%m-%d %H:%M:%S')}  (重建模式)")

    preds = pd.read_parquet(PREDS)
    panel = pd.read_parquet(PANEL)
    csi300 = pd.read_parquet(CSI300)
    basic = pd.read_csv(BASIC, dtype=str)
    preds["trade_date"] = preds["trade_date"].astype(str)
    panel["trade_date"] = panel["trade_date"].astype(str)
    csi300["trade_date"] = csi300["trade_date"].astype(str)

    print(f"  preds: {len(preds)} rows, "
          f"{preds.trade_date.nunique()} dates "
          f"[{preds.trade_date.min()} → {preds.trade_date.max()}]")
    print(f"  panel: {len(panel)} rows, {panel.ts_code.nunique()} tickers")
    print(f"  basic: {len(basic)} tickers, {basic.industry.nunique()} industries")

    # 跑模拟
    result = simulate(
        preds_df=preds,
        basic_df=basic,
        panel_df=panel,
        csi300_df=csi300,
        initial_nav=INITIAL_NAV,
        n_hold=N_HOLD,
        max_per_industry=MAX_PER_INDUSTRY,
        hold_threshold=HOLD_THRESHOLD,
        start_signal_date=START_SIGNAL_DATE,
    )

    scorecard_by_date = result["scorecard"]
    equity = result["equity"]
    monthly = result["monthly"]
    summary = result["summary"]
    holdings_now = result["holdings_now"]

    n_pending = sum(1 for sc in scorecard_by_date.values() if sc.get("pending"))
    n_realized = len(scorecard_by_date) - n_pending
    print(f"  simulation: {len(scorecard_by_date)} signal days "
          f"({n_realized} realized, {n_pending} pending)")
    if equity:
        print(f"  equity: {len(equity)} pts, "
              f"{equity[0]['d']} → {equity[-1]['d']}, "
              f"cum={summary['cum_return']:.2f}% (bench {summary['benchmark_cum']:.2f}%), "
              f"sharpe={summary['sharpe']:.2f}, mdd={summary['max_drawdown']:.2f}%")

    # —— 聚合：行业权重 & 高频持仓（基于 scorecard.picks）——
    ind_count = Counter()
    ticker_count = Counter()
    ticker_info: dict[str, dict] = {}
    total_picks = 0
    for sc in scorecard_by_date.values():
        for p in sc.get("picks", []):
            ind = p.get("ind", "—")
            ind_count[ind] += 1
            ticker_count[p["ts"]] += 1
            total_picks += 1
            if p["ts"] not in ticker_info:
                ticker_info[p["ts"]] = {"name": p.get("name", p["ts"]),
                                         "industry": p.get("ind", "—")}
    n_days = len(scorecard_by_date)
    industry_avg = [
        {"industry": k, "weight": round(v / total_picks * 100, 2)}
        for k, v in ind_count.most_common(12)
    ] if total_picks else []
    top_held = [
        {"ts": ts, "name": ticker_info[ts]["name"],
         "industry": ticker_info[ts]["industry"],
         "days": days,
         "pct": round(days / n_days * 100, 1)}
        for ts, days in ticker_count.most_common(15)
    ]

    # —— scorecard wrap ——
    dates_sorted = sorted(scorecard_by_date.keys())
    all_dates = [{
        "d": d,
        "avg": scorecard_by_date[d]["avg_ret"],
        "bench": scorecard_by_date[d]["bench_ret"],
        "excess": scorecard_by_date[d]["excess"],
        "hit": scorecard_by_date[d]["hit_rate"],
    } for d in dates_sorted]
    recent = [scorecard_by_date[d] for d in dates_sorted[-10:]]

    # summary 里展开 scorecard 子统计
    sc_summary = {
        "n_days_total": summary["n_realized"],
        "n_pending": summary["n_pending"],
        "model_avg_daily": summary["model_avg_daily"],
        "bench_avg_daily": summary["bench_avg_daily"],
        "excess_avg": summary["excess_avg"],
        "win_rate_vs_bench_daily": summary["win_rate_vs_bench_daily"],
        "avg_hit_rate": summary["avg_hit_rate"],
        "best_day": summary["best_day"],
        "worst_day": summary["worst_day"],
    }

    # —— 拼装最终 data.json ——
    data = {
        "summary": {
            "asof": summary["asof"],
            "start": summary["start"],
            "n_days": summary["n_days"],
            "starting_nav": summary["starting_nav"],
            "final_nav": summary["final_nav"],
            "cum_return": summary["cum_return"],
            "benchmark_cum": summary["benchmark_cum"],
            "excess": summary["excess"],
            "sharpe": summary["sharpe"],
            "max_drawdown": summary["max_drawdown"],
            "monthly_win_rate": summary["monthly_win_rate"],
            # 兼容现有前端字段命名
            "computed_cum_return": summary["cum_return"],
            "computed_sharpe": summary["sharpe"],
            "computed_max_drawdown": summary["max_drawdown"],
        },
        "equity_curve": equity,
        "monthly_returns": monthly,
        "current_holdings": holdings_now,
        "top_held": top_held,
        "industry_avg": industry_avg,
        "scorecard": {
            "summary": sc_summary,
            "all_dates": all_dates,
            "recent": recent,
            "by_date": scorecard_by_date,
        },
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    dt = (datetime.now() - t0).total_seconds()
    print(f"[OK] saved → {DATA_JSON}  ({dt:.1f}s)")


if __name__ == "__main__":
    main()
