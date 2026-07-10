"""Cross-sectional robust z-score normalization."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_sectional_robust_zscore(
    panel: pd.DataFrame,
    feature_cols: list[str],
    clip: float = 5.0,
) -> pd.DataFrame:
    """Normalize feature columns within each trade_date cross-section."""
    out = panel.copy()
    feats = out[feature_cols].astype(float).to_numpy()
    dates = out["trade_date"].to_numpy()

    stats = pd.DataFrame(feats, columns=feature_cols)
    stats["__date__"] = dates
    med = stats.groupby("__date__")[feature_cols].transform("median")
    abs_dev = (stats[feature_cols] - med).abs()
    abs_dev["__date__"] = dates
    mad = abs_dev.groupby("__date__")[feature_cols].transform("median")

    std_est = (mad * 1.4826).replace(0, np.nan)
    z = (stats[feature_cols] - med) / std_est
    out[feature_cols] = z.clip(-clip, clip).fillna(0.0).to_numpy()
    return out
