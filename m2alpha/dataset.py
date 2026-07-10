"""Dense cross-sectional window dataset for public baseline training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
import torch


@dataclass
class WindowSample:
    trade_date: str
    ts_codes: np.ndarray
    x: torch.Tensor
    y: torch.Tensor


class DenseWindowDataset:
    """Each item is one trading day containing all valid stocks."""

    def __init__(
        self,
        panel: pd.DataFrame,
        feature_cols: list[str],
        tau: int,
        label_col: str = "label",
        allowed_dates: Sequence[str] | None = None,
        min_stocks_per_day: int = 30,
    ):
        self.feature_cols = feature_cols
        self.tau = int(tau)
        self.label_col = label_col
        self.allowed_dates = set(str(d) for d in allowed_dates) if allowed_dates is not None else None

        panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True).copy()
        panel["trade_date"] = panel["trade_date"].astype(str)
        self._stock_data: dict[str, pd.DataFrame] = {}
        self._stock_dates: dict[str, list[str]] = {}
        self._stock_pos: dict[str, dict[str, int]] = {}
        cols = ["trade_date", *feature_cols, label_col]
        for ts, grp in panel.groupby("ts_code", sort=False):
            g = grp[cols].set_index("trade_date")
            dates = list(g.index)
            self._stock_data[ts] = g
            self._stock_dates[ts] = dates
            self._stock_pos[ts] = {d: i for i, d in enumerate(dates)}

        self.dates: list[str] = []
        self._date_to_stocks: dict[str, list[str]] = {}
        for d in sorted(panel["trade_date"].unique()):
            if self.allowed_dates is not None and d not in self.allowed_dates:
                continue
            sub = panel[(panel["trade_date"] == d) & panel[label_col].notna()]
            stocks = sub["ts_code"].tolist()
            if len(stocks) < min_stocks_per_day:
                continue
            self.dates.append(d)
            self._date_to_stocks[d] = stocks

    def __len__(self) -> int:
        return len(self.dates)

    def __getitem__(self, idx: int) -> WindowSample:
        d = self.dates[idx]
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        codes: list[str] = []
        for ts in self._date_to_stocks[d]:
            pos = self._stock_pos[ts].get(d)
            if pos is None or pos < self.tau - 1:
                continue
            window_dates = self._stock_dates[ts][pos - self.tau + 1:pos + 1]
            frame = self._stock_data[ts].loc[window_dates]
            x = frame[self.feature_cols].to_numpy(dtype=np.float32)
            y = frame[self.label_col].to_numpy(dtype=np.float32)
            if x.shape != (self.tau, len(self.feature_cols)) or y.shape != (self.tau,):
                continue
            if not np.isfinite(x).all() or not np.isfinite(y).all():
                continue
            xs.append(x)
            ys.append(y)
            codes.append(ts)

        if not xs:
            return WindowSample(
                trade_date=d,
                ts_codes=np.array([], dtype=object),
                x=torch.empty(0, self.tau, len(self.feature_cols), dtype=torch.float32),
                y=torch.empty(0, self.tau, dtype=torch.float32),
            )

        return WindowSample(
            trade_date=d,
            ts_codes=np.array(codes, dtype=object),
            x=torch.from_numpy(np.stack(xs)),
            y=torch.from_numpy(np.stack(ys)),
        )
