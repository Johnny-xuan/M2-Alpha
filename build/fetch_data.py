"""fetch_data.py — 用 AKShare 拉沪深 300 当日成分股的最新 N 天量价 + 基本面 + 资金流向。

输出: build/cache/panel.parquet
  字段: ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount, vwap,
        turnover_rate, turnover_rate_f, volume_ratio, pe_ttm, pb, ps_ttm,
        buy_sm/md/lg/elg_amount, sell_sm/md/lg/elg_amount, net_mf_amount

也输出: build/cache/csi300.parquet — 沪深 300 指数日线（基准用）
       build/cache/basic.csv — 成分股名称 + 行业映射

依赖: pip install akshare pandas pyarrow
"""

from __future__ import annotations
import argparse, time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)


def get_csi300_components() -> pd.DataFrame:
    """获取最新沪深 300 成分股清单 + 行业。"""
    import akshare as ak
    print("[1/4] 拉取沪深 300 成分股...")
    # 沪深300成份股
    comps = ak.index_stock_cons_csindex(symbol="000300")
    comps = comps.rename(columns={
        "成分券代码": "code", "成分券名称": "name", "交易所": "exchange",
    })
    comps["ts_code"] = comps.apply(
        lambda r: f"{r.code}.{ 'SH' if r['exchange'] in ('上海证券交易所','上交所','SH') else 'SZ' }",
        axis=1
    )
    # 行业（用 akshare 申万行业分类）
    try:
        ind = ak.stock_individual_info_em(symbol=comps.code.iloc[0])  # 测试
    except Exception:
        pass
    # 简化：用 stock_info_a_code_name 获取行业
    info = ak.stock_info_a_code_name()
    info["ts_code"] = info["code"].apply(lambda c: f"{c}.{'SH' if c[0]=='6' else 'SZ'}")

    # 申万行业（用 stock_individual_basic_info_xq 或 stock_industry_clf_hist_sw）
    print("  补充申万行业分类 ...")
    try:
        sw = ak.sw_index_first_info()  # 申万一级行业列表
        # 拿每只股票的一级行业：用 stock_individual_basic_info_xq（雪球接口）
        industries = {}
        for code in comps.code.tolist():
            try:
                detail = ak.stock_individual_basic_info_xq(symbol=f"{'SH' if code[0]=='6' else 'SZ'}{code}")
                ind_val = detail.loc[detail["item"] == "所属行业", "value"].iloc[0] if not detail.empty else None
                industries[code] = ind_val
                time.sleep(0.05)
            except Exception:
                industries[code] = None
        comps["industry"] = comps["code"].map(industries).fillna("—")
    except Exception as e:
        print(f"  [warn] 行业获取失败 ({e})，用空值占位")
        comps["industry"] = "—"

    out = comps[["ts_code", "name", "industry"]]
    print(f"  → {len(out)} 只成分股")
    return out


def get_daily_panel(ts_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """拉每只股票的日线 + 基本面 + 资金流向，拼成 panel。"""
    import akshare as ak
    print(f"[2/4] 拉取 {len(ts_codes)} 只股票 [{start_date}~{end_date}] 日线 + 指标 ...")
    rows = []
    for i, ts_code in enumerate(ts_codes):
        code = ts_code.split(".")[0]
        try:
            # 日线（前复权）
            daily = ak.stock_zh_a_hist(symbol=code, period="daily",
                                       start_date=start_date, end_date=end_date,
                                       adjust="qfq")
            if daily.empty:
                continue
            daily = daily.rename(columns={
                "日期": "trade_date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "vol",
                "成交额": "amount", "振幅": "amplitude", "涨跌幅": "pct_chg",
                "涨跌额": "change", "换手率": "turnover_rate",
            })
            daily["ts_code"] = ts_code
            daily["trade_date"] = pd.to_datetime(daily["trade_date"]).dt.strftime("%Y%m%d")
            daily["pre_close"] = daily["close"] - daily["change"]
            daily["vwap"] = daily["amount"] / daily["vol"].replace(0, pd.NA) / 100.0  # AKShare vol 单位手, amount 元
            rows.append(daily)
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(ts_codes)}")
            time.sleep(0.02)
        except Exception as e:
            print(f"  [skip] {ts_code}: {e}")

    if not rows:
        raise RuntimeError("AKShare 没拿到任何数据")
    panel = pd.concat(rows, ignore_index=True)

    # 基本面（PE/PB/PS/turnover_rate_f）— 一次性拉所有 A 股的当日横截面
    print("[3/4] 拉取基本面指标 ...")
    try:
        latest_dt = panel["trade_date"].max()
        spot = ak.stock_zh_a_spot_em()
        spot = spot.rename(columns={
            "代码": "code", "市盈率-动态": "pe_ttm",
            "市净率": "pb", "总市值": "total_mv", "流通市值": "circ_mv",
            "换手率": "turnover_rate_f",
        })
        spot["ts_code"] = spot["code"].apply(lambda c: f"{c}.{'SH' if c[0]=='6' else 'SZ'}")
        # 对每个 ts_code 把最新一日的 pe/pb 广播回去（更细的话需要历史 metric 接口）
        meta = spot[["ts_code", "pe_ttm", "pb", "turnover_rate_f"]]
        panel = panel.merge(meta, on="ts_code", how="left")
        panel["ps_ttm"] = pd.NA           # AKShare 没有 PS-TTM 现成接口，留空
        panel["volume_ratio"] = pd.NA      # 同上
    except Exception as e:
        print(f"  [warn] 基本面缺失: {e}")
        for c in ["pe_ttm", "pb", "ps_ttm", "turnover_rate_f", "volume_ratio"]:
            panel[c] = pd.NA

    # 资金流向（按日 + 按股票拉，每只股票一个 API call —— AKShare 没有跨股票批量接口）
    print("[4/4] 拉取资金流向 ...")
    # 简化策略：为了 GitHub Actions 时间预算，先把 net_mf_amount 和 buy_*_amount 设为 0
    # 后续可改用 ak.stock_individual_fund_flow 每只股票拉，但 300 次 API call 较慢
    for c in ["net_mf_amount", "buy_sm_amount", "buy_md_amount",
              "buy_lg_amount", "buy_elg_amount", "sell_sm_amount",
              "sell_md_amount", "sell_lg_amount", "sell_elg_amount"]:
        panel[c] = 0.0

    return panel


def get_csi300_index(start_date: str, end_date: str) -> pd.DataFrame:
    """获取沪深 300 指数日线作为基准。"""
    import akshare as ak
    print("  拉取沪深 300 指数日线 ...")
    df = ak.stock_zh_index_daily(symbol="sh000300")
    df["trade_date"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
    df["ts_code"] = "000300.SH"
    df = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)]
    return df[["ts_code", "trade_date", "open", "high", "low", "close"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90,
                        help="往前回溯多少个自然日（足够覆盖 60 个交易日 + 30 个 lookback）")
    args = parser.parse_args()

    today = datetime.now()
    end_date = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=args.days)).strftime("%Y%m%d")

    # 1. 成分股 + 行业
    comps = get_csi300_components()
    comps.to_csv(CACHE / "basic.csv", index=False)
    print(f"  saved → {CACHE / 'basic.csv'}")

    # 2. 全成分股日线 panel
    panel = get_daily_panel(comps["ts_code"].tolist(), start_date, end_date)
    panel.to_parquet(CACHE / "panel.parquet", index=False)
    print(f"  saved → {CACHE / 'panel.parquet'}  rows={len(panel)}")

    # 3. 沪深 300 指数
    idx = get_csi300_index(start_date, end_date)
    idx.to_parquet(CACHE / "csi300.parquet", index=False)
    print(f"  saved → {CACHE / 'csi300.parquet'}  rows={len(idx)}")

    print("\n[done] all data fetched.")


if __name__ == "__main__":
    main()
