"""Label construction for dense next-day cross-sectional supervision."""

from __future__ import annotations

import pandas as pd


def make_next_open_return(panel: pd.DataFrame) -> pd.Series:
    """open[s+2] / open[s+1] - 1 for signal day s."""
    df = panel.sort_values(["ts_code", "trade_date"]).copy()
    grp = df.groupby("ts_code", sort=False)["open"]
    label = grp.shift(-2) / grp.shift(-1) - 1.0
    label.name = "label_raw"
    return label


def make_next_close_return(panel: pd.DataFrame) -> pd.Series:
    """close[s+2] / close[s+1] - 1 for signal day s."""
    df = panel.sort_values(["ts_code", "trade_date"]).copy()
    grp = df.groupby("ts_code", sort=False)["close"]
    label = grp.shift(-2) / grp.shift(-1) - 1.0
    label.name = "label_raw"
    return label


def cross_sectional_zscore_label(
    panel_with_label: pd.DataFrame,
    label_col: str = "label_raw",
) -> pd.Series:
    """Convert raw future returns to per-day cross-sectional z-scores."""
    df = panel_with_label[["trade_date", label_col]].copy()

    def _z(s: pd.Series) -> pd.Series:
        mean = s.mean()
        std = s.std()
        if std == 0 or pd.isna(std):
            return s * 0
        return (s - mean) / std

    z = df.groupby("trade_date", sort=False)[label_col].transform(_z)
    z.name = "label"
    return z
