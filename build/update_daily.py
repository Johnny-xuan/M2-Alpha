"""update_daily.py — 增量更新 docs/data/data.json 中"每日变化"的字段。

设计：每个交易日只更新以下字段，不重建历史回测部分：
  · current_holdings      — 最新 Top 10 picks
  · scorecard.by_date[D]  — 当日预测明细
  · scorecard.recent      — 最近 10 天滚动窗口
  · scorecard.all_dates   — 追加当日 (用于 60 天 excess chart)
  · scorecard.summary     — 滚动更新 (n_days_total, win_rate 等)

历史回测部分（equity_curve / monthly_returns / industry_avg / top_held）
来自初始 seed data.json，由 MASTER 项目离线生成；本脚本不动它们。

依赖前置脚本:
  1. python build/fetch_data.py        → 拉最新 panel + 指数 + basic
  2. python build/inference.py         → 跑模型出 preds.parquet
  3. python build/update_daily.py      → 增量回写 docs/data/data.json
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                # M2-Alpha/
CACHE = HERE / "cache"
DATA_JSON = ROOT / "docs" / "data" / "data.json"
PANEL = CACHE / "panel.parquet"
PREDS = CACHE / "preds.parquet"
CSI300 = CACHE / "csi300.parquet"
BASIC = CACHE / "basic.csv"


def _fmt(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def main():
    print(f"[update_daily] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Load existing data.json (seed)
    with open(DATA_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  loaded seed data.json (asof={data['summary']['asof']})")

    # 2. Load latest preds + panel + index + basic
    preds = pd.read_parquet(PREDS)
    preds["trade_date"] = preds["trade_date"].astype(str)
    panel = pd.read_parquet(PANEL)
    panel["trade_date"] = panel["trade_date"].astype(str)
    csi300 = pd.read_parquet(CSI300)
    csi300["trade_date"] = csi300["trade_date"].astype(str)
    basic = pd.read_csv(BASIC, dtype=str)
    name_map = dict(zip(basic.ts_code, basic.name))
    industry_map = dict(zip(basic.ts_code, basic.industry))

    latest_date = preds["trade_date"].max()
    print(f"  latest pred date: {latest_date}")

    # 3. Build current_holdings: Top 10 of latest date
    latest_close = panel[panel.trade_date == latest_date].set_index("ts_code")["close"]
    top10 = preds[preds.trade_date == latest_date].nlargest(10, "pred").reset_index(drop=True)
    NAV = 1_000_000  # 假设组合规模
    target_w = 1.0 / len(top10)
    holdings = []
    for i, r in top10.iterrows():
        ts = r.ts_code
        close = float(latest_close.get(ts, 0.0))
        if close <= 0:
            shares = 0
        else:
            # 整手 (100 股) 向下取整，按 10% 分配
            shares = int(NAV * target_w / close / 100) * 100
        amount = shares * close
        holdings.append({
            "rank": i + 1,
            "ts": ts,
            "name": name_map.get(ts, ts),
            "industry": industry_map.get(ts, "—"),
            "score": round(float(r.pred), 3),
            "close": round(close, 2),
            "shares": shares,
            "weight": round(amount / NAV * 100, 1),
        })
    data["current_holdings"] = holdings
    print(f"  current_holdings: {len(holdings)} picks, top = {holdings[0]['name']}")

    # 4. Update scorecard.by_date: compute realized return for each day with D+2 available
    bench_open = csi300.set_index("trade_date")["open"]
    panel_open = panel.set_index(["trade_date", "ts_code"])["open"]
    all_pred_dates = sorted(preds["trade_date"].unique())

    # CRITICAL: merge into existing by_date, don't replace.
    # First Action run only has ~60 days of preds (fetch_data --days 90);
    # the seed data.json has 11 months — must preserve old + add new.
    scorecard_by_date = data["scorecard"].get("by_date", {})
    print(f"  existing scorecard.by_date entries: {len(scorecard_by_date)}")

    new_count = 0
    for d in all_pred_dates:
        di = all_pred_dates.index(d)
        if di + 2 >= len(all_pred_dates):
            continue  # not enough future
        d1, d2 = all_pred_dates[di + 1], all_pred_dates[di + 2]
        is_new = _fmt(d) not in scorecard_by_date
        daily = preds[preds.trade_date == d].nlargest(10, "pred")
        picks_perf = []
        rets = []
        for r in daily.itertuples():
            ts = r.ts_code
            o1 = panel_open.get((d1, ts))
            o2 = panel_open.get((d2, ts))
            if o1 and o2 and o1 > 0:
                rr = (o2 / o1 - 1) * 100
                rets.append(rr)
            else:
                rr = None
            picks_perf.append({
                "ts": ts,
                "name": name_map.get(ts, ts),
                "ind": industry_map.get(ts, "—"),
                "score": round(float(r.pred), 3),
                "ret": round(rr, 2) if rr is not None else None,
            })
        if not rets:
            continue
        bo1, bo2 = bench_open.get(d1), bench_open.get(d2)
        bench_ret = (bo2 / bo1 - 1) * 100 if bo1 and bo2 else None
        avg_ret = float(np.mean(rets))
        excess = avg_ret - bench_ret if bench_ret is not None else None
        hits = sum(1 for r in rets if bench_ret is not None and r > bench_ret)

        scorecard_by_date[_fmt(d)] = {
            "d": _fmt(d), "buy_d": _fmt(d1), "sell_d": _fmt(d2),
            "avg_ret": round(avg_ret, 2),
            "bench_ret": round(bench_ret, 2) if bench_ret is not None else None,
            "excess": round(excess, 2) if excess is not None else None,
            "hits": hits, "n": len(rets),
            "hit_rate": round(hits / len(rets) * 100, 1),
            "picks": picks_perf,
        }
        if is_new:
            new_count += 1

    data["scorecard"]["by_date"] = scorecard_by_date
    print(f"  scorecard.by_date: {len(scorecard_by_date)} total (+{new_count} new)")

    # 5. Rebuild all_dates (lightweight chart series) + recent + summary
    dates_sorted = sorted(scorecard_by_date.keys())
    data["scorecard"]["all_dates"] = [
        {
            "d": d,
            "avg": scorecard_by_date[d]["avg_ret"],
            "bench": scorecard_by_date[d]["bench_ret"],
            "excess": scorecard_by_date[d]["excess"],
            "hit": scorecard_by_date[d]["hit_rate"],
        }
        for d in dates_sorted
    ]
    data["scorecard"]["recent"] = [scorecard_by_date[d] for d in dates_sorted[-10:]]

    # summary
    arr = np.array([scorecard_by_date[d]["avg_ret"] for d in dates_sorted])
    barr = np.array([scorecard_by_date[d]["bench_ret"] for d in dates_sorted if scorecard_by_date[d]["bench_ret"] is not None])
    earr = np.array([scorecard_by_date[d]["excess"] for d in dates_sorted if scorecard_by_date[d]["excess"] is not None])
    harr = np.array([scorecard_by_date[d]["hit_rate"] for d in dates_sorted])
    data["scorecard"]["summary"] = {
        "n_days_total": len(dates_sorted),
        "model_avg_daily": round(float(arr.mean()), 3),
        "bench_avg_daily": round(float(barr.mean()), 3) if len(barr) else 0.0,
        "excess_avg": round(float(earr.mean()), 3) if len(earr) else 0.0,
        "win_rate_vs_bench_daily": round(float((earr > 0).mean() * 100), 1) if len(earr) else 0.0,
        "avg_hit_rate": round(float(harr.mean()), 1),
        "best_day": {"d": dates_sorted[int(np.argmax(arr))], "ret": round(float(arr.max()), 2)},
        "worst_day": {"d": dates_sorted[int(np.argmin(arr))], "ret": round(float(arr.min()), 2)},
    }

    # 6. Recompute industry_avg + top_held from scorecard picks (live, not seed)
    ind_count = Counter()
    ticker_count = Counter()
    ticker_info = {}
    total_picks = 0
    for date_data in scorecard_by_date.values():
        for p in date_data.get("picks", []):
            ind = p.get("ind", "—")
            ind_count[ind] += 1
            ticker_count[p["ts"]] += 1
            total_picks += 1
            if p["ts"] not in ticker_info:
                ticker_info[p["ts"]] = {
                    "name": p.get("name", p["ts"]),
                    "industry": p.get("ind", "—"),
                }
    n_days = len(scorecard_by_date)

    data["industry_avg"] = [
        {"industry": k, "weight": round(v / total_picks * 100, 2)}
        for k, v in ind_count.most_common(12)
    ]
    data["top_held"] = [
        {
            "ts": ts,
            "name": ticker_info[ts]["name"],
            "industry": ticker_info[ts]["industry"],
            "days": days,
            "pct": round(days / n_days * 100, 1),
        }
        for ts, days in ticker_count.most_common(15)
    ]
    print(f"  recomputed industry_avg ({len(data['industry_avg'])} industries) + top_held ({len(data['top_held'])} tickers)")

    # 7. Update top-level summary metadata (asof + counters)
    data["summary"]["asof"] = _fmt(latest_date)
    print(f"  updated summary.asof = {data['summary']['asof']}")

    # 7. Save
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] saved → {DATA_JSON}")


if __name__ == "__main__":
    main()
