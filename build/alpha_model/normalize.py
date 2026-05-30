"""截面 robust z-score — 每个交易日截面内做（不跨日，天然防泄漏）。

(x - median) / mad 比标准 z-score 对极端值更鲁棒。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_sectional_robust_zscore(
    panel: pd.DataFrame,
    feature_cols: list[str],
    clip: float = 5.0,
) -> pd.DataFrame:
    """对每个 trade_date 截面，对每个特征做 robust z-score 并裁剪。"""
    out = panel.copy()
    feats = out[feature_cols].astype(float).to_numpy()
    dates = out["trade_date"].to_numpy()

    df_for_stats = pd.DataFrame(feats, columns=feature_cols)
    df_for_stats["__date__"] = dates
    med = df_for_stats.groupby("__date__")[feature_cols].transform("median")
    abs_dev = (df_for_stats[feature_cols] - med).abs()
    abs_dev["__date__"] = dates
    mad = abs_dev.groupby("__date__")[feature_cols].transform("median")

    std_est = (mad * 1.4826).replace(0, np.nan)
    z = (df_for_stats[feature_cols] - med) / std_est
    z = z.clip(-clip, clip).fillna(0.0)

    out[feature_cols] = z.to_numpy()
    return out
