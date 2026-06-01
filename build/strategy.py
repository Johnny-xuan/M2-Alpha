"""strategy.py — 行业分散 top-10 + 滞后带（lag-band）策略。

与 MASTER 项目参赛配置一致 (project_master_competition_config)：
  - 候选池：CSI300
  - 每日 top-10、等权满仓
  - 每行业 ≤ 2 只
  - 持仓滞后带：持仓 rank 跌出 top-50 才换；否则保留
  - 执行：信号日 D 出信号 → D+1 开盘建仓/换仓 → 在 D+2 等之后再考虑下一次换仓
  - 回测下用 open-to-open 计算每日净值

输入：
  preds_df   长表 (trade_date, ts_code, pred)，每日 N 只
  basic_df   (ts_code, name, industry)
  panel_df   长表 panel: ts_code, trade_date, open, close, ...
  csi300_df  指数 ts_code, trade_date, open, close, ...

输出：
  result = {
    "equity": [{"d": YYYY-MM-DD, "nav":..., "bench":..., "ret":..., "bret":...}],
    "scorecard": {YYYY-MM-DD: {picks, avg_ret, bench_ret, excess, hits, n, hit_rate, buy_d, sell_d, pending}},
    "monthly": [...],
    "summary": {...},
    "holdings_now": [...],
  }
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
import numpy as np
import pandas as pd


def _fmt(d: str) -> str:
    """20260529 -> 2026-05-29"""
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _next_weekday(yyyymmdd: str) -> str:
    """跳过周末（不考虑节假日）。20260529(Fri) -> 20260601(Mon)。"""
    from datetime import datetime, timedelta
    d = datetime.strptime(yyyymmdd, "%Y%m%d")
    while True:
        d += timedelta(days=1)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")


def select_diversified(scored: pd.DataFrame, industry_map: dict[str, str],
                        n: int = 10, max_per_industry: int = 2) -> list[str]:
    """从已按 pred 降序排好的 scored 表里挑出最多 n 只，且每个行业 ≤ max_per_industry。

    Args:
      scored: DataFrame with columns ts_code, pred (already sorted desc by pred)
      industry_map: ts_code -> industry string
    Returns:
      list of ts_code in selection order (up to n)
    """
    chosen: list[str] = []
    ind_count: dict[str, int] = defaultdict(int)
    for r in scored.itertuples(index=False):
        ts = r.ts_code
        ind = industry_map.get(ts, "—")
        if ind_count[ind] >= max_per_industry:
            continue
        chosen.append(ts)
        ind_count[ind] += 1
        if len(chosen) >= n:
            break
    return chosen


def simulate(preds_df: pd.DataFrame,
             basic_df: pd.DataFrame,
             panel_df: pd.DataFrame,
             csi300_df: pd.DataFrame,
             *,
             initial_nav: float = 1_000_000.0,
             n_hold: int = 10,
             max_per_industry: int = 2,
             hold_threshold: int = 50,
             start_signal_date: str | None = None) -> dict:
    """逐日模拟。

    Returns dict 见模块 docstring。
    """
    # 一致性预处理
    preds = preds_df.copy()
    preds["trade_date"] = preds["trade_date"].astype(str)
    panel = panel_df.copy()
    panel["trade_date"] = panel["trade_date"].astype(str)
    csi300 = csi300_df.copy()
    csi300["trade_date"] = csi300["trade_date"].astype(str)
    basic = basic_df.copy()
    name_map = dict(zip(basic.ts_code, basic.name))
    industry_map = dict(zip(basic.ts_code, basic.industry))

    open_by = panel.set_index(["trade_date", "ts_code"])["open"]
    bench_open = csi300.set_index("trade_date")["open"]

    signal_dates = sorted(preds["trade_date"].unique())
    if start_signal_date:
        signal_dates = [d for d in signal_dates if d >= start_signal_date]

    # 全局排序：先按 ts_code 让原始顺序稳定，否则 sort_values 在打分相同时
    # 用非稳定排序，会导致同一份 preds.parquet 两次跑出来 picks 不同。
    preds = preds.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)

    # rank 表：每日所有股票按 pred 降序排名（1=最佳，ts_code 作 tie-breaker）
    preds_ranked = preds.copy()
    preds_ranked["rank"] = preds_ranked.groupby("trade_date")["pred"].rank(
        method="first", ascending=False
    ).astype(int)
    rank_lookup = preds_ranked.set_index(["trade_date", "ts_code"])["rank"]
    pred_lookup = preds.set_index(["trade_date", "ts_code"])["pred"]

    # 输出容器
    scorecard: dict[str, dict] = {}
    equity: list[dict] = []

    nav = initial_nav
    bench_nav = initial_nav
    holdings: list[str] = []   # 当前持仓 ts_code 列表

    pending_count = 0
    realized_count = 0

    for di, d in enumerate(signal_dates):
        # —— 1) 根据 d 的信号决定 d+1 开盘的目标持仓 ——
        d_next = signal_dates[di + 1] if di + 1 < len(signal_dates) else None
        d_next2 = signal_dates[di + 2] if di + 2 < len(signal_dates) else None

        # 稳定排序 + ts_code tie-breaker，保证多次跑结果完全一致
        day_scored = (preds[preds.trade_date == d]
                      .sort_values(["pred", "ts_code"],
                                   ascending=[False, True],
                                   kind="stable")
                      .reset_index(drop=True))

        # 上一日 carry over：先看哪些持仓还在 top_hold_threshold 内
        kept = []
        for ts in holdings:
            r = rank_lookup.get((d, ts))
            if r is not None and r <= hold_threshold:
                kept.append(ts)

        # 在剩余 (10 - len(kept)) 槽位里，按行业上限填充
        n_need = n_hold - len(kept)
        new_picks: list[str] = []
        if n_need > 0:
            ind_count: dict[str, int] = defaultdict(int)
            for ts in kept:
                ind_count[industry_map.get(ts, "—")] += 1
            for r in day_scored.itertuples(index=False):
                ts = r.ts_code
                if ts in kept:
                    continue
                ind = industry_map.get(ts, "—")
                if ind_count[ind] >= max_per_industry:
                    continue
                new_picks.append(ts)
                ind_count[ind] += 1
                if len(new_picks) >= n_need:
                    break

        target_holdings = kept + new_picks
        # 兜底：如果信号过度集中导致填不满，放宽行业约束
        if len(target_holdings) < n_hold:
            ind_count = defaultdict(int)
            for ts in target_holdings:
                ind_count[industry_map.get(ts, "—")] += 1
            for r in day_scored.itertuples(index=False):
                ts = r.ts_code
                if ts in target_holdings:
                    continue
                target_holdings.append(ts)
                if len(target_holdings) >= n_hold:
                    break

        target_set = set(target_holdings)

        # —— 2) 计算"信号日 d → 实际持仓 d+1 开盘 → d+2 开盘卖出"的当日收益 ——
        if d_next is None:
            # 没有下一交易日数据 → pending；buy_d / sell_d 估算为下一/再下一交易日
            est_d1 = _next_weekday(d)
            est_d2 = _next_weekday(est_d1)
            picks_perf = _build_pending_picks(target_holdings, name_map,
                                              industry_map, pred_lookup, d)
            top30 = _build_top30(day_scored, target_set, name_map, industry_map,
                                  open_by, None, None)
            scorecard[_fmt(d)] = {
                "d": _fmt(d),
                "buy_d": _fmt(est_d1),
                "sell_d": _fmt(est_d2),
                "avg_ret": None, "bench_ret": None, "excess": None,
                "hits": None, "n": None, "hit_rate": None,
                "picks": picks_perf,
                "top30": top30,
                "pending": True,
            }
            pending_count += 1
            holdings = target_holdings
            continue

        if d_next2 is None:
            # 有 d+1 open（可建仓），但还没 d+2 open（结算）→ sell_d 估算
            est_d2 = _next_weekday(d_next)
            picks_perf = _build_pending_picks(target_holdings, name_map,
                                              industry_map, pred_lookup, d)
            top30 = _build_top30(day_scored, target_set, name_map, industry_map,
                                  open_by, d_next, None)
            scorecard[_fmt(d)] = {
                "d": _fmt(d),
                "buy_d": _fmt(d_next),
                "sell_d": _fmt(est_d2),
                "avg_ret": None, "bench_ret": None, "excess": None,
                "hits": None, "n": None, "hit_rate": None,
                "picks": picks_perf,
                "top30": top30,
                "pending": True,
            }
            pending_count += 1
            holdings = target_holdings
            continue

        # 已结算：拿 d_next, d_next2 的开盘价
        rets = []
        picks_perf = []
        for ts in target_holdings:
            o1 = open_by.get((d_next, ts))
            o2 = open_by.get((d_next2, ts))
            score = pred_lookup.get((d, ts), 0.0)
            if o1 and o2 and o1 > 0:
                rr = (o2 / o1 - 1) * 100
                rets.append(rr)
            else:
                rr = None
            picks_perf.append({
                "ts": ts,
                "name": name_map.get(ts, ts),
                "ind": industry_map.get(ts, "—"),
                "score": round(float(score), 3),
                "ret": round(rr, 2) if rr is not None else None,
            })

        top30 = _build_top30(day_scored, target_set, name_map, industry_map,
                              open_by, d_next, d_next2)

        bo1 = bench_open.get(d_next); bo2 = bench_open.get(d_next2)
        bench_ret = (bo2 / bo1 - 1) * 100 if bo1 and bo2 else None
        avg_ret = float(np.mean(rets)) if rets else None
        excess = avg_ret - bench_ret if (avg_ret is not None and bench_ret is not None) else None
        hits = sum(1 for r in rets if bench_ret is not None and r > bench_ret) if rets else None
        n_avail = len(rets)

        scorecard[_fmt(d)] = {
            "d": _fmt(d),
            "buy_d": _fmt(d_next),
            "sell_d": _fmt(d_next2),
            "avg_ret": round(avg_ret, 2) if avg_ret is not None else None,
            "bench_ret": round(bench_ret, 2) if bench_ret is not None else None,
            "excess": round(excess, 2) if excess is not None else None,
            "hits": hits, "n": n_avail,
            "hit_rate": round(hits / n_avail * 100, 1) if n_avail else None,
            "picks": picks_perf,
            "top30": top30,
            "pending": False,
        }
        realized_count += 1
        holdings = target_holdings

    # —— 3) 重新构建 equity curve（按所有交易日推进，buy_d 维度）——
    # 用 scorecard[d].avg_ret 在 d_next 这一天给 nav 加复利
    # 但要按 buy_d (= d_next) 升序处理，因为 buy_d 才是组合实际生效的天
    eq_pairs = []  # (buy_d, avg_ret, bench_ret)
    for d_iso, sc in scorecard.items():
        if sc["pending"] or sc.get("buy_d") is None or sc.get("sell_d") is None:
            continue
        eq_pairs.append((sc["buy_d"], sc["avg_ret"], sc["bench_ret"]))
    eq_pairs.sort()

    # 初始 nav 在第一个 buy_d 前一日为 initial_nav
    nav = initial_nav
    bench_nav = initial_nav
    if eq_pairs:
        # equity_curve[0] 是建仓基准日（第一个 buy_d 前一天概念上）
        first_buy_d = eq_pairs[0][0]
        equity.append({
            "d": first_buy_d, "nav": round(nav, 2), "bench": round(bench_nav, 2),
            "ret": 0.0, "bret": 0.0,
        })
        for buy_d, avg_ret, bench_ret in eq_pairs:
            if avg_ret is None: continue
            nav *= (1 + avg_ret / 100.0)
            if bench_ret is not None:
                bench_nav *= (1 + bench_ret / 100.0)
            # 此处 d 用 sell_d 表示净值结算到哪一天
            ret_pct = (nav / initial_nav - 1) * 100
            bret_pct = (bench_nav / initial_nav - 1) * 100
            # sell_d for this avg_ret
            # We need it: find by buy_d in scorecard
            sell_d = None
            for d_iso, sc in scorecard.items():
                if sc.get("buy_d") == buy_d:
                    sell_d = sc["sell_d"]; break
            equity.append({
                "d": sell_d or buy_d,
                "nav": round(nav, 2),
                "bench": round(bench_nav, 2),
                "ret": round(ret_pct, 3),
                "bret": round(bret_pct, 3),
            })

    # —— 4) 月度 & summary ——
    nav_by_month = defaultdict(list)
    bench_by_month = defaultdict(list)
    for r in equity:
        m = r["d"][:7]
        nav_by_month[m].append(r["nav"])
        bench_by_month[m].append(r["bench"])
    monthly = []
    for m in sorted(nav_by_month):
        navs_m = nav_by_month[m]; benches_m = bench_by_month[m]
        if len(navs_m) < 2: continue
        ret = (navs_m[-1] / navs_m[0] - 1) * 100
        bret = (benches_m[-1] / benches_m[0] - 1) * 100
        monthly.append({"m": m, "model": round(ret, 2),
                        "bench": round(bret, 2), "excess": round(ret - bret, 2)})

    summary = _summarize(equity, monthly, scorecard, signal_dates)

    # —— 5) holdings_now: 最近一次（包括 pending 的）目标持仓 ——
    last_sig = signal_dates[-1] if signal_dates else None
    holdings_now = []
    if last_sig:
        last_picks = scorecard.get(_fmt(last_sig), {}).get("picks", [])
        # 价格：用 last_sig 的 close 作为参考价（实际买入会在 d+1 开盘）
        close_last = panel[panel.trade_date == last_sig].set_index("ts_code")["close"]
        target_w = 1.0 / max(len(last_picks), 1)
        cur_nav = equity[-1]["nav"] if equity else initial_nav
        for i, p in enumerate(last_picks):
            ts = p["ts"]
            c = float(close_last.get(ts, 0.0))
            shares = int(cur_nav * target_w / c / 100) * 100 if c > 0 else 0
            holdings_now.append({
                "rank": i + 1,
                "ts": ts,
                "name": p["name"],
                "industry": p["ind"],
                "score": p["score"],
                "close": round(c, 2),
                "shares": shares,
                "weight": round(shares * c / cur_nav * 100, 1) if cur_nav else 0.0,
            })

    return {
        "equity": equity,
        "scorecard": scorecard,
        "monthly": monthly,
        "summary": summary,
        "holdings_now": holdings_now,
    }


def _build_pending_picks(target_holdings, name_map, industry_map, pred_lookup, d):
    out = []
    for ts in target_holdings:
        out.append({
            "ts": ts,
            "name": name_map.get(ts, ts),
            "ind": industry_map.get(ts, "—"),
            "score": round(float(pred_lookup.get((d, ts), 0.0)), 3),
            "ret": None,
        })
    return out


def _build_top30(day_scored, target_holdings_set, name_map, industry_map,
                  open_by, d_next, d_next2, n_top=30):
    """对 day_scored 取前 N 只（默认 30），逐只查 D+1→D+2 开盘价计实际收益、
    并标记是否被策略选中（in_portfolio）。"""
    out = []
    head = day_scored.head(n_top)
    for rank_i, r in enumerate(head.itertuples(index=False), 1):
        ts = r.ts_code
        rr = None
        if d_next is not None and d_next2 is not None:
            o1 = open_by.get((d_next, ts))
            o2 = open_by.get((d_next2, ts))
            if o1 and o2 and o1 > 0:
                rr = (o2 / o1 - 1) * 100
        out.append({
            "rank": rank_i,
            "ts": ts,
            "name": name_map.get(ts, ts),
            "ind": industry_map.get(ts, "—"),
            "score": round(float(r.pred), 3),
            "ret": round(rr, 2) if rr is not None else None,
            "in_portfolio": ts in target_holdings_set,
        })
    return out


def _summarize(equity, monthly, scorecard, signal_dates):
    if not equity:
        return {}
    navs = [r["nav"] for r in equity]
    benches = [r["bench"] for r in equity]
    cum = (navs[-1] / navs[0] - 1) * 100
    bench_cum = (benches[-1] / benches[0] - 1) * 100
    peak = navs[0]; mdd = 0.0
    for v in navs:
        if v > peak: peak = v
        d_pct = (v / peak - 1) * 100
        if d_pct < mdd: mdd = d_pct
    # daily returns for sharpe
    rets = np.array([navs[i] / navs[i - 1] - 1 for i in range(1, len(navs))])
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    win_months = sum(1 for x in monthly if x["excess"] > 0)
    realized = [d for d, sc in scorecard.items() if not sc["pending"]]
    pending = [d for d, sc in scorecard.items() if sc["pending"]]
    arr = np.array([scorecard[d]["avg_ret"] for d in realized])
    earr = np.array([scorecard[d]["excess"] for d in realized if scorecard[d]["excess"] is not None])
    barr = np.array([scorecard[d]["bench_ret"] for d in realized if scorecard[d]["bench_ret"] is not None])
    harr = np.array([scorecard[d]["hit_rate"] for d in realized if scorecard[d]["hit_rate"] is not None])
    best_i = int(np.argmax(arr)) if len(arr) else -1
    worst_i = int(np.argmin(arr)) if len(arr) else -1

    return {
        "asof": equity[-1]["d"],
        "start": equity[0]["d"],
        "n_days": len(equity),
        "n_signals": len(signal_dates),
        "n_realized": len(realized),
        "n_pending": len(pending),
        "starting_nav": navs[0],
        "final_nav": round(navs[-1], 2),
        "cum_return": round(cum, 2),
        "benchmark_cum": round(bench_cum, 2),
        "excess": round(cum - bench_cum, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(mdd, 2),
        "monthly_win_rate": round(win_months / max(len(monthly), 1) * 100, 1),
        "model_avg_daily": round(float(arr.mean()), 3) if len(arr) else 0.0,
        "bench_avg_daily": round(float(barr.mean()), 3) if len(barr) else 0.0,
        "excess_avg": round(float(earr.mean()), 3) if len(earr) else 0.0,
        "win_rate_vs_bench_daily": round(float((earr > 0).mean() * 100), 1) if len(earr) else 0.0,
        "avg_hit_rate": round(float(harr.mean()), 1) if len(harr) else 0.0,
        "best_day": ({"d": realized[best_i], "ret": round(float(arr.max()), 2)} if len(arr) else None),
        "worst_day": ({"d": realized[worst_i], "ret": round(float(arr.min()), 2)} if len(arr) else None),
    }
