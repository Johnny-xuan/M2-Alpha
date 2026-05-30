"""Feature engineering — basic 35-feature set used by production model.

设计原则：
  1. 全部因子按 ts_code 分组后做时间序列计算，绝不跨股票
  2. 不在全局做 z-score（防泄漏）；标准化交给后续 cross-sectional normalize
  3. 输出列名以 'f_' 前缀，便于一键挑选特征矩阵
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_features(panel: pd.DataFrame) -> pd.DataFrame:
    """输入 panel（含 OHLCV + metric + moneyflow），输出 panel + f_* 列。"""
    df = panel.sort_values(["ts_code", "trade_date"]).copy()
    g = df.groupby("ts_code", group_keys=False, sort=False)
    keep_cols = ["ts_code", "trade_date", "open", "high", "low", "close",
                 "pre_close", "pct_chg", "vol", "amount", "vwap"]
    keep_cols = [c for c in keep_cols if c in df.columns]
    out = df[keep_cols].copy()

    # 1. momentum — 多尺度收益率
    for k in [1, 2, 3, 5, 10, 20, 30, 60]:
        out[f"f_ret_{k}"] = g["close"].pct_change(k)

    # 2. ma — 价格 vs 均线偏离
    for k in [5, 10, 20, 30, 60]:
        ma = g["close"].transform(lambda x: x.rolling(k, min_periods=2).mean())
        out[f"f_close_ma_{k}"] = df["close"] / ma - 1.0

    # 3. vol — 波动率
    for k in [5, 10, 20, 30, 60]:
        r1 = g["close"].pct_change(1)
        std = r1.groupby(df["ts_code"]).transform(lambda x: x.rolling(k, min_periods=3).std())
        out[f"f_vol_{k}"] = std

    # 4. kline — K 线形态
    out["f_kmid"] = (df["close"] - df["open"]) / df["open"].replace(0, np.nan)
    out["f_klen"] = (df["high"] - df["low"]) / df["open"].replace(0, np.nan)
    out["f_kup"]  = (df["high"] - np.maximum(df["open"], df["close"])) / df["open"].replace(0, np.nan)
    out["f_klow"] = (np.minimum(df["open"], df["close"]) - df["low"]) / df["open"].replace(0, np.nan)

    # 5. volume — 成交量动量与放量
    for k in [5, 10, 20]:
        vma = g["vol"].transform(lambda x: x.rolling(k, min_periods=2).mean())
        out[f"f_vol_ratio_{k}"] = df["vol"] / vma.replace(0, np.nan)
    out["f_vol_chg_1"] = g["vol"].pct_change(1).replace([np.inf, -np.inf], np.nan)
    out["f_amount_chg_1"] = g["amount"].pct_change(1).replace([np.inf, -np.inf], np.nan)

    # 6. fundamental — 换手率 / 基本面
    for col in ["turnover_rate", "turnover_rate_f", "volume_ratio", "pe_ttm", "pb", "ps_ttm"]:
        if col in df.columns:
            out[f"f_{col}"] = df[col]

    # 7. moneyflow — 资金流向
    if "net_mf_amount" in df.columns:
        amount_yuan = df["amount"] * 1000.0
        net_yuan = df["net_mf_amount"] * 10000.0
        out["f_mf_net_ratio"] = (net_yuan / amount_yuan.replace(0, np.nan)).clip(-5, 5)
    if all(c in df.columns for c in ["buy_lg_amount", "buy_elg_amount", "buy_sm_amount"]):
        big_buy = df["buy_lg_amount"].fillna(0) + df["buy_elg_amount"].fillna(0)
        small_buy = df["buy_sm_amount"].fillna(0)
        out["f_mf_big_small_diff"] = (big_buy - small_buy) / (big_buy + small_buy + 1.0)

    # 替换 inf 为 NaN
    feat_cols = [c for c in out.columns if c.startswith("f_")]
    out[feat_cols] = out[feat_cols].replace([np.inf, -np.inf], np.nan)
    return out


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("f_")]
