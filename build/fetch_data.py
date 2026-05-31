"""fetch_data.py — 用 BaoStock 拉沪深 300 当日成分股最近 N 天的量价 + 基本面。

BaoStock 优势：
  · 完全免费，无 token，无频次限制
  · 走自家 TCP 协议（data.baostock.com:31322），不依赖东财 / 雪球 / 深交所
  · 直接返回 peTTM / pbMRQ / psTTM / turn 等关键基本面（一次 query 拿齐）

输出:
  build/cache/panel.parquet — 成分股 panel: ts_code, trade_date, OHLCV, pre_close,
    pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f, pe_ttm, pb,
    ps_ttm, volume_ratio, net_mf_amount, buy/sell_(sm|md|lg|elg)_amount
  build/cache/csi300.parquet — 沪深 300 指数日线
  build/cache/basic.csv — 成分股代码 + 名称 + 行业映射

依赖: pip install baostock pandas pyarrow
"""

from __future__ import annotations
import argparse, re, sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)


def _bs_code_to_ts(bs_code: str) -> str:
    """Convert 'sh.600519' → '600519.SH'."""
    if "." not in bs_code:
        return bs_code
    mkt, code = bs_code.split(".")
    return f"{code}.{mkt.upper()}"


def _ts_to_bs_code(ts_code: str) -> str:
    """Convert '600519.SH' → 'sh.600519'."""
    if "." not in ts_code:
        return ts_code
    code, mkt = ts_code.split(".")
    return f"{mkt.lower()}.{code}"


def _date_to_compact(d: str) -> str:
    """'2026-05-29' → '20260529'."""
    return d.replace("-", "")


def _bs_query_to_df(rs) -> pd.DataFrame:
    rows = []
    while (rs.error_code == "0") & rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


def shorten_industry(s: str) -> str:
    """Normalize 证监会行业分类长名 → 短名 (用于 UI 显示)。

    Examples:
      'C39计算机、通信和其他电子设备制造业' → '计算机'
      'C38电气机械和器材制造业'             → '电气机械'
      'J66货币金融服务'                    → '货币金融'
      'C32有色金属冶炼和压延加工业'         → '有色金属冶炼'
      ''                                  → '—'
    """
    if not s or not isinstance(s, str):
        return "—"
    # Strip leading "C39" / "J66" 等代码前缀
    s = re.sub(r'^[A-Z]\d+', '', s).strip()
    # 按"、和及与"切第一个名词块
    for sep in ['、', '和', '及', '与']:
        if sep in s:
            s = s.split(sep)[0]
            break
    # 去常见后缀
    for suffix in ['制造业', '服务业', '加工业', '业', '服务']:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    return s.strip() or "—"


def get_csi300_components(bs) -> pd.DataFrame:
    """获取沪深 300 成分股清单 + 行业。"""
    print("[1/4] 拉取沪深 300 成分股 ...")
    rs = bs.query_hs300_stocks()
    comps = _bs_query_to_df(rs)
    comps["ts_code"] = comps["code"].apply(_bs_code_to_ts)
    print(f"  → {len(comps)} 只成分股")

    print("  补充行业分类 ...")
    rs = bs.query_stock_industry()
    ind = _bs_query_to_df(rs)
    ind["ts_code"] = ind["code"].apply(_bs_code_to_ts)
    ind_map = dict(zip(ind["ts_code"], ind["industry"]))
    comps["industry"] = comps["ts_code"].map(ind_map).fillna("").apply(shorten_industry)
    comps["name"] = comps["code_name"]
    return comps[["ts_code", "name", "industry"]]


def get_daily_panel(bs, ts_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """拉每只股票日线 OHLCV + PE/PB/PS/turnover (一次 query 全拿)。"""
    print(f"[2/4] 拉取 {len(ts_codes)} 只股票 [{start_date}~{end_date}] 日线 ...")
    fields = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,peTTM,pbMRQ,psTTM"
    rows = []
    skipped = 0
    for i, ts_code in enumerate(ts_codes):
        bs_code = _ts_to_bs_code(ts_code)
        rs = bs.query_history_k_data_plus(
            bs_code, fields,
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2",   # 2 = 前复权
        )
        df = _bs_query_to_df(rs)
        if df.empty:
            skipped += 1
            continue
        df["ts_code"] = ts_code
        rows.append(df)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(ts_codes)}")

    if not rows:
        raise RuntimeError("BaoStock 没拿到任何数据")

    panel = pd.concat(rows, ignore_index=True)
    print(f"  → {len(panel)} 行 (skipped {skipped} 股)")

    # Rename to match training-time tushare schema
    panel = panel.rename(columns={
        "date": "trade_date",
        "volume": "vol",
        "turn": "turnover_rate",
        "pctChg": "pct_chg",
        "preclose": "pre_close",
        "peTTM": "pe_ttm",
        "pbMRQ": "pb",
        "psTTM": "ps_ttm",
    })
    panel["trade_date"] = panel["trade_date"].apply(_date_to_compact)

    # Cast numeric columns
    num_cols = ["open", "high", "low", "close", "pre_close", "vol", "amount",
                "turnover_rate", "pct_chg", "pe_ttm", "pb", "ps_ttm"]
    for c in num_cols:
        if c in panel.columns:
            panel[c] = pd.to_numeric(panel[c], errors="coerce")

    # Derived: vwap
    panel["vwap"] = panel["amount"] / panel["vol"].replace(0, pd.NA)

    # Stubbed fields not provided by BaoStock — features.py 用到它们会喂 0
    # （cross-sectional z-score 下 0 == neutral，不会引入虚假信号）
    panel["turnover_rate_f"] = panel["turnover_rate"]   # 自由换手率近似
    panel["volume_ratio"] = pd.NA                        # 量比，缺
    for c in ["net_mf_amount", "buy_sm_amount", "buy_md_amount",
              "buy_lg_amount", "buy_elg_amount",
              "sell_sm_amount", "sell_md_amount",
              "sell_lg_amount", "sell_elg_amount"]:
        panel[c] = 0.0
    return panel


def get_csi300_index(bs, start_date: str, end_date: str) -> pd.DataFrame:
    """获取沪深 300 指数日线作为基准。"""
    print("[3/4] 拉取沪深 300 指数日线 ...")
    rs = bs.query_history_k_data_plus(
        "sh.000300",
        "date,open,high,low,close,preclose,volume,amount,pctChg",
        start_date=start_date, end_date=end_date,
        frequency="d", adjustflag="3",   # 3 = 不复权 (指数)
    )
    df = _bs_query_to_df(rs)
    df = df.rename(columns={"date": "trade_date"})
    df["trade_date"] = df["trade_date"].apply(_date_to_compact)
    df["ts_code"] = "000300.SH"
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    print(f"  → {len(df)} 行")
    return df[["ts_code", "trade_date", "open", "high", "low", "close"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90,
                        help="往前回溯多少自然日 (默认 90, 覆盖约 60 个交易日 + 30 个 lookback)")
    args = parser.parse_args()

    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"[fetch] window: {start_date} → {end_date}")

    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")
    print(f"  baostock login ok (code={lg.error_code})")

    try:
        # 1. 成分股 + 行业
        comps = get_csi300_components(bs)
        comps.to_csv(CACHE / "basic.csv", index=False)
        print(f"  saved → {CACHE / 'basic.csv'}")

        # 2. 全成分股日线 panel
        panel = get_daily_panel(bs, comps["ts_code"].tolist(), start_date, end_date)
        panel.to_parquet(CACHE / "panel.parquet", index=False)
        print(f"  saved → {CACHE / 'panel.parquet'}  rows={len(panel)}")

        # 3. CSI 300 index
        idx = get_csi300_index(bs, start_date, end_date)
        idx.to_parquet(CACHE / "csi300.parquet", index=False)
        print(f"  saved → {CACHE / 'csi300.parquet'}  rows={len(idx)}")

        print(f"\n[4/4] all data fetched.")
    finally:
        bs.logout()


if __name__ == "__main__":
    main()
