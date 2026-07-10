"""Research benchmark utilities for M2-Alpha.

This module is the public historical reproduction path for richer user-supplied
panels, using label-filtered historical windows and a share/cash backtest
engine with one-trading-day signal lag.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch

from .dataset import DenseWindowDataset
from .features import feature_columns, make_features
from .labels import (
    cross_sectional_zscore_label,
    make_next_close_return,
    make_next_open_return,
)
from .model import load_alpha_model
from .normalize import cross_sectional_robust_zscore


@dataclass(frozen=True)
class BenchmarkConfig:
    start: str = "20250701"
    end: str = "20260525"
    tau: int = 8
    label_basis: str = "close"
    n_hold: int = 5
    pool_rank: int = 100
    sell_rank: int = 200
    max_industry_frac: float = 0.2
    weighting: str = "equal"
    fee_rate: float = 0.0013
    lot_size: int = 100
    exec_price: str = "open"
    nav_price: str | None = None
    init_cash: float = 1_000_000.0
    min_stocks_per_day: int = 30

    def validate(self) -> None:
        if self.label_basis not in {"close", "open"}:
            raise ValueError("label_basis must be 'close' or 'open'")
        if self.exec_price not in {"close", "open"}:
            raise ValueError("exec_price must be 'close' or 'open'")
        if self.nav_price is not None and self.nav_price not in {"close", "open"}:
            raise ValueError("nav_price must be None, 'close', or 'open'")
        if self.weighting != "equal":
            raise ValueError("only equal weighting is supported in the public benchmark")
        if self.n_hold <= 0:
            raise ValueError("n_hold must be positive")


@dataclass
class BacktestResult:
    nav: pd.Series
    holdings: pd.DataFrame
    trades: pd.DataFrame
    daily_summary: pd.DataFrame


class ResearchTopNStrategy:
    """Top-N strategy with a sell band and an industry cap.

    The strategy keeps existing holdings while they remain inside the sell
    band, then fills empty slots with the highest-ranked tradable names subject
    to the industry cap. If the cap prevents a full book, it relaxes the cap as
    a final fallback so the benchmark remains comparable to the original
    research run.
    """

    def __init__(
        self,
        n_hold: int,
        pool_rank: int,
        sell_rank: int,
        industry_map: dict[str, str] | None = None,
        max_industry_frac: float = 0.2,
    ):
        self.n_hold = int(n_hold)
        self.pool_rank = int(pool_rank)
        self.sell_rank = int(sell_rank)
        self.industry_map = industry_map or {}
        self.max_per_industry = max(1, int(self.n_hold * max_industry_frac))

    def decide(
        self,
        date: str,
        portfolio: dict[str, int],
        scores: dict[str, float],
        tradable: dict[str, bool],
    ) -> dict[str, float]:
        ranked = sorted(
            [(s, sc) for s, sc in scores.items() if tradable.get(s, False)],
            key=lambda x: (-x[1], x[0]),
        )
        if not ranked:
            return {}
        rank_of = {s: i for i, (s, _) in enumerate(ranked)}
        score_of = dict(ranked)
        held = list(portfolio.keys())

        stuck = [s for s in held if not tradable.get(s, False)]
        sellable_held = [s for s in held if tradable.get(s, False)]
        keep = [s for s in sellable_held if rank_of.get(s, 10**9) < self.sell_rank]
        target = list(dict.fromkeys(keep + stuck))

        if len(target) > self.n_hold:
            sellable = sorted(
                [s for s in target if s not in stuck],
                key=lambda s: (-score_of.get(s, -1e9), s),
            )
            target = stuck + sellable[: max(0, self.n_hold - len(stuck))]

        ind_count: dict[str, int] = {}
        for s in target:
            ind = self.industry_map.get(s, "NA")
            ind_count[ind] = ind_count.get(ind, 0) + 1

        for s, _ in ranked:
            if len(target) >= self.n_hold:
                break
            if s in target:
                continue
            ind = self.industry_map.get(s, "NA")
            if ind_count.get(ind, 0) >= self.max_per_industry:
                continue
            target.append(s)
            ind_count[ind] = ind_count.get(ind, 0) + 1

        if len(target) < self.n_hold:
            for s, _ in ranked:
                if len(target) >= self.n_hold:
                    break
                if s not in target:
                    target.append(s)

        if not target:
            return {}
        weight = 1.0 / len(target)
        return {s: weight for s in target}


def prepare_benchmark_panel(
    panel: pd.DataFrame,
    *,
    label_basis: str = "close",
) -> tuple[pd.DataFrame, list[str]]:
    """Build features, labels, and same-day cross-sectional normalization."""
    if label_basis not in {"close", "open"}:
        raise ValueError("label_basis must be 'close' or 'open'")
    prepared = panel.copy()
    prepared["trade_date"] = prepared["trade_date"].astype(str)
    prepared = make_features(prepared)
    feat_cols = feature_columns(prepared)
    if len(feat_cols) != 35:
        raise ValueError(f"expected the public 35-feature contract, got {len(feat_cols)}")
    if label_basis == "open":
        prepared["label_raw"] = make_next_open_return(prepared).values
    else:
        prepared["label_raw"] = make_next_close_return(prepared).values
    prepared["label"] = cross_sectional_zscore_label(prepared, "label_raw").values
    prepared = cross_sectional_robust_zscore(prepared, feat_cols)
    return prepared, feat_cols


def historical_predict(
    prepared_panel: pd.DataFrame,
    feature_cols: list[str],
    checkpoint_path: str | Path,
    *,
    start: str,
    end: str,
    tau: int = 8,
    device: str = "cpu",
    min_stocks_per_day: int = 30,
) -> pd.DataFrame:
    """Run label-filtered historical prediction for benchmark reproduction.

    This mirrors the original research evaluation semantics: the panel is first
    feature-normalized on all available dates up to `end`, then sliced to the
    requested benchmark window. The dense dataset requires finite labels across
    the entire tau-window, so the final dates without future labels are trimmed.
    Forward inference should use a separate, label-free path.
    """
    seg = prepared_panel[
        (prepared_panel["trade_date"] >= str(start))
        & (prepared_panel["trade_date"] <= str(end))
    ].copy()
    if seg.empty:
        raise ValueError(f"no rows in benchmark window {start}..{end}")

    ds = DenseWindowDataset(
        seg,
        feature_cols=feature_cols,
        tau=tau,
        label_col="label",
        min_stocks_per_day=min_stocks_per_day,
    )
    if len(ds) == 0:
        raise ValueError("no valid benchmark prediction dates after label/window filtering")

    model = load_alpha_model(str(checkpoint_path), device=device)
    rows: list[dict[str, object]] = []
    with torch.no_grad():
        for i in range(len(ds)):
            sample = ds[i]
            if sample.x.numel() == 0:
                continue
            out = model(sample.x.to(device))
            scores = out[:, -1].detach().cpu().numpy()
            for ts, score in zip(sample.ts_codes, scores):
                rows.append(
                    {
                        "trade_date": sample.trade_date,
                        "ts_code": str(ts),
                        "pred": float(score),
                    }
                )
    if not rows:
        raise ValueError("model produced no benchmark predictions")
    return pd.DataFrame(rows)


def load_industry_map(
    panel: pd.DataFrame,
    industry_file: str | Path | None = None,
) -> dict[str, str]:
    """Load ts_code -> industry mapping from a file or from the panel."""
    if industry_file:
        df = pd.read_csv(industry_file, dtype=str)
        if "ts_code" not in df.columns:
            raise ValueError("industry file must contain ts_code")
        candidates = ["industry", "sw_l2", "industry_name", "sector"]
        col = next((c for c in candidates if c in df.columns), None)
        if col is None:
            raise ValueError(f"industry file must contain one of: {', '.join(candidates)}")
        return dict(zip(df["ts_code"], df[col].fillna("NA")))
    if "industry" in panel.columns:
        df = panel[["ts_code", "industry"]].dropna().drop_duplicates("ts_code")
        return dict(zip(df["ts_code"].astype(str), df["industry"].astype(str)))
    return {}


def run_research_backtest(
    predictions: pd.DataFrame,
    panel: pd.DataFrame,
    strategy: ResearchTopNStrategy,
    *,
    init_cash: float = 1_000_000.0,
    fee_rate: float = 0.0013,
    lot_size: int = 100,
    exec_price: str = "open",
    nav_price: str | None = None,
) -> BacktestResult:
    if exec_price not in {"open", "close"}:
        raise ValueError("exec_price must be 'open' or 'close'")
    if nav_price is not None and nav_price not in {"open", "close"}:
        raise ValueError("nav_price must be None, 'open', or 'close'")

    panel = panel.sort_values(["trade_date", "ts_code"]).copy()
    panel["trade_date"] = panel["trade_date"].astype(str)
    predictions = predictions.sort_values(["trade_date", "ts_code"]).copy()
    predictions["trade_date"] = predictions["trade_date"].astype(str)

    panel_by_day = {d: g.set_index("ts_code") for d, g in panel.groupby("trade_date", sort=True)}
    preds_by_day = {
        d: dict(zip(g["ts_code"], g["pred"]))
        for d, g in predictions.groupby("trade_date", sort=True)
    }
    trade_days = sorted(set(preds_by_day) & set(panel_by_day))
    if not trade_days:
        raise ValueError("predictions and panel have no overlapping dates")

    cash = float(init_cash)
    holdings: dict[str, int] = {}
    nav_records: list[tuple[str, float]] = []
    holdings_records: list[tuple[str, str, int]] = []
    trades_records: list[tuple[str, str, str, int, float, float, float]] = []
    daily_summary: list[tuple[str, float, float, float, int]] = []

    prev_pred: dict[str, float] | None = None
    for date in trade_days:
        day_panel = panel_by_day[date]
        tradable = {ts: _is_tradable(row) for ts, row in day_panel.iterrows()}

        if prev_pred is not None:
            target = strategy.decide(date, dict(holdings), prev_pred, tradable)
            cash, holdings, trade_log = _execute_target_weights(
                date,
                target,
                cash,
                holdings,
                day_panel,
                tradable,
                fee_rate=fee_rate,
                lot_size=lot_size,
                exec_price=exec_price,
            )
            trades_records.extend(trade_log)

        nav_col = nav_price or exec_price
        position_value = 0.0
        for ts, shares in holdings.items():
            if ts in day_panel.index and pd.notna(day_panel.loc[ts, nav_col]):
                position_value += shares * float(day_panel.loc[ts, nav_col])
        nav = cash + position_value
        nav_records.append((date, nav))
        daily_summary.append((date, nav, cash, position_value, len(holdings)))
        for ts, shares in holdings.items():
            holdings_records.append((date, ts, shares))

        prev_pred = preds_by_day.get(date, {})

    nav_series = pd.Series(
        [v for _, v in nav_records],
        index=[d for d, _ in nav_records],
        name="nav",
    )
    return BacktestResult(
        nav=nav_series,
        holdings=pd.DataFrame(holdings_records, columns=["trade_date", "ts_code", "shares"]),
        trades=pd.DataFrame(
            trades_records,
            columns=["trade_date", "ts_code", "side", "shares", "price", "amount", "fee"],
        ),
        daily_summary=pd.DataFrame(
            daily_summary,
            columns=["trade_date", "nav", "cash", "position_value", "n_holdings"],
        ),
    )


def summarize_backtest(result: BacktestResult) -> dict[str, float | int | str]:
    nav = result.nav.dropna().astype(float)
    if len(nav) < 2:
        raise ValueError("need at least two NAV points to summarize")
    total_return = nav.iloc[-1] / nav.iloc[0] - 1.0
    daily_ret = nav.pct_change().dropna()
    annual_return = (nav.iloc[-1] / nav.iloc[0]) ** (252 / len(nav)) - 1.0
    sharpe = (
        float(daily_ret.mean() / daily_ret.std() * np.sqrt(252))
        if daily_ret.std() > 0
        else float("nan")
    )
    drawdown = nav / nav.cummax() - 1.0
    turnover = _turnover_rate(result.trades, nav)
    months = pd.DataFrame({"trade_date": nav.index, "nav": nav.values})
    months["month"] = months["trade_date"].str[:6]
    month_ret = []
    for _, g in months.groupby("month"):
        if len(g) > 1:
            month_ret.append(g["nav"].iloc[-1] / g["nav"].iloc[0] - 1.0)
    return {
        "start": str(nav.index[0]),
        "end": str(nav.index[-1]),
        "n_days": int(len(nav)),
        "cum_return": float(total_return),
        "cum_return_pct": float(total_return * 100),
        "annual_return": float(annual_return),
        "annual_return_pct": float(annual_return * 100),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "max_drawdown_pct": float(drawdown.min() * 100),
        "turnover": turnover,
        "final_nav": float(nav.iloc[-1]),
        "month_win_rate": float(np.mean(np.array(month_ret) > 0)) if month_ret else float("nan"),
    }


def run_benchmark_for_checkpoint(
    panel: pd.DataFrame,
    checkpoint_path: str | Path,
    config: BenchmarkConfig,
    *,
    industry_map: dict[str, str] | None = None,
    device: str = "cpu",
) -> tuple[pd.DataFrame, BacktestResult, dict[str, object]]:
    config.validate()
    base_panel = panel.copy()
    base_panel["trade_date"] = base_panel["trade_date"].astype(str)
    base_panel = base_panel[base_panel["trade_date"] <= config.end].copy()
    prepared, feature_cols = prepare_benchmark_panel(base_panel, label_basis=config.label_basis)
    preds = historical_predict(
        prepared,
        feature_cols,
        checkpoint_path,
        start=config.start,
        end=config.end,
        tau=config.tau,
        device=device,
        min_stocks_per_day=config.min_stocks_per_day,
    )
    seg = prepared[(prepared["trade_date"] >= config.start) & (prepared["trade_date"] <= config.end)].copy()
    strategy = ResearchTopNStrategy(
        n_hold=config.n_hold,
        pool_rank=config.pool_rank,
        sell_rank=config.sell_rank,
        industry_map=industry_map or {},
        max_industry_frac=config.max_industry_frac,
    )
    result = run_research_backtest(
        preds,
        seg,
        strategy,
        init_cash=config.init_cash,
        fee_rate=config.fee_rate,
        lot_size=config.lot_size,
        exec_price=config.exec_price,
        nav_price=config.nav_price,
    )
    summary = summarize_backtest(result)
    summary["alignment"] = validate_benchmark_alignment(preds, result)
    summary["config"] = asdict(config)
    summary["n_predictions"] = int(len(preds))
    summary["n_prediction_dates"] = int(preds["trade_date"].nunique())
    summary["first_prediction_date"] = str(preds["trade_date"].min())
    summary["last_prediction_date"] = str(preds["trade_date"].max())
    summary["checkpoint"] = str(checkpoint_path)
    return preds, result, summary


def validate_benchmark_alignment(
    predictions: pd.DataFrame,
    result: BacktestResult,
) -> dict[str, object]:
    """Check the benchmark's core time-alignment contract."""
    pred_dates = sorted(predictions["trade_date"].astype(str).unique())
    nav_dates = [str(d) for d in result.nav.index]
    if not pred_dates:
        raise ValueError("alignment check failed: no prediction dates")
    if not nav_dates:
        raise ValueError("alignment check failed: no NAV dates")
    if nav_dates[0] != pred_dates[0]:
        raise ValueError(
            f"alignment check failed: first NAV date {nav_dates[0]} "
            f"!= first prediction date {pred_dates[0]}"
        )
    if nav_dates[-1] != pred_dates[-1]:
        raise ValueError(
            f"alignment check failed: last NAV date {nav_dates[-1]} "
            f"!= last prediction date {pred_dates[-1]}"
        )

    first_trade_date = None
    if not result.trades.empty:
        first_trade_date = str(result.trades["trade_date"].min())
        if first_trade_date <= pred_dates[0]:
            raise ValueError(
                "alignment check failed: first trade does not occur after "
                f"the first prediction date ({first_trade_date} <= {pred_dates[0]})"
            )

    return {
        "first_prediction_date": pred_dates[0],
        "last_prediction_date": pred_dates[-1],
        "first_nav_date": nav_dates[0],
        "last_nav_date": nav_dates[-1],
        "first_trade_date": first_trade_date,
        "signal_lag_checked": first_trade_date is None or first_trade_date > pred_dates[0],
        "label_filtered_historical_path": True,
    }


def _is_tradable(row: pd.Series) -> bool:
    if pd.isna(row.get("vol")) or float(row.get("vol", 0.0)) == 0.0:
        return False
    pct = row.get("pct_chg")
    if pd.isna(pct):
        return False
    ts = row.name if isinstance(row.name, str) else ""
    limit = 19.95 if (ts.startswith("300") or ts.startswith("688")) else 9.95
    return abs(float(pct)) < limit


def _execute_target_weights(
    date: str,
    target_weights: dict[str, float],
    cash: float,
    holdings: dict[str, int],
    day_panel: pd.DataFrame,
    tradable: dict[str, bool],
    *,
    fee_rate: float,
    lot_size: int,
    exec_price: str,
) -> tuple[float, dict[str, int], list[tuple[str, str, str, int, float, float, float]]]:
    trade_log: list[tuple[str, str, str, int, float, float, float]] = []
    position_value = sum(
        shares * float(day_panel.loc[ts, exec_price])
        for ts, shares in holdings.items()
        if ts in day_panel.index and pd.notna(day_panel.loc[ts, exec_price])
    )
    total_value = cash + position_value

    target_codes = set(target_weights)
    for ts in [ts for ts in list(holdings) if ts not in target_codes]:
        if not tradable.get(ts, False) or ts not in day_panel.index:
            continue
        shares = holdings.pop(ts)
        price = float(day_panel.loc[ts, exec_price])
        amount = shares * price
        fee = amount * fee_rate
        cash += amount - fee
        trade_log.append((date, ts, "sell", shares, price, amount, fee))

    total_value_after_sell = cash + sum(
        shares * float(day_panel.loc[ts, exec_price])
        for ts, shares in holdings.items()
        if ts in day_panel.index and pd.notna(day_panel.loc[ts, exec_price])
    )
    if total_value_after_sell <= 0:
        total_value_after_sell = total_value

    for ts, weight in target_weights.items():
        if not tradable.get(ts, False) or ts not in day_panel.index:
            continue
        price = float(day_panel.loc[ts, exec_price])
        if price <= 0:
            continue
        target_amount = total_value_after_sell * weight
        current_shares = holdings.get(ts, 0)
        current_amount = current_shares * price
        delta_amount = target_amount - current_amount
        delta_shares = int(np.floor(delta_amount / price / lot_size)) * lot_size
        if delta_shares > 0:
            cost = delta_shares * price
            fee = cost * fee_rate
            need = cost + fee
            if need > cash:
                delta_shares = int(np.floor(cash / (price * (1 + fee_rate)) / lot_size)) * lot_size
                if delta_shares <= 0:
                    continue
                cost = delta_shares * price
                fee = cost * fee_rate
            cash -= cost + fee
            holdings[ts] = current_shares + delta_shares
            trade_log.append((date, ts, "buy", delta_shares, price, cost, fee))
        elif delta_shares < 0:
            sell_shares = min(-delta_shares, current_shares)
            sell_shares = (sell_shares // lot_size) * lot_size
            if sell_shares <= 0:
                continue
            amount = sell_shares * price
            fee = amount * fee_rate
            cash += amount - fee
            next_shares = current_shares - sell_shares
            if next_shares:
                holdings[ts] = next_shares
            else:
                holdings.pop(ts, None)
            trade_log.append((date, ts, "sell", sell_shares, price, amount, fee))

    return cash, holdings, trade_log


def _turnover_rate(trades_df: pd.DataFrame, nav: pd.Series) -> float:
    if trades_df.empty:
        return 0.0
    daily_amount = trades_df.groupby("trade_date")["amount"].sum()
    daily_nav = nav.reindex(daily_amount.index).ffill()
    return float((daily_amount / daily_nav).mean())


def write_benchmark_outputs(
    out_dir: str | Path,
    *,
    key: str,
    predictions: pd.DataFrame,
    result: BacktestResult,
    summary: dict[str, object],
) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = key.replace(".", "_")
    predictions.to_parquet(out / f"predictions_{safe}.parquet", index=False)
    result.nav.rename("nav").to_frame().to_csv(out / f"nav_{safe}.csv")
    result.trades.to_csv(out / f"trades_{safe}.csv", index=False)
    result.holdings.to_csv(out / f"holdings_{safe}.csv", index=False)
    pd.Series(summary, dtype=object).to_json(
        out / f"summary_{safe}.json",
        force_ascii=False,
        indent=2,
    )
