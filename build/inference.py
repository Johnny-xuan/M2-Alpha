"""inference.py — 加载 m2alpha.pt 在最新 panel 上跑推理 → 输出每日 Top 10。

输入: build/cache/panel.parquet (来自 fetch_data.py)
输出: build/cache/preds.parquet  字段: trade_date, ts_code, pred

策略：
  - 对每一日 D，构造 X ∈ (S, τ=8, F=35)，X[t] = features at D-τ+1+t
  - forward 得 (S, T)，取 [:, -1] 作为当日预测分数
  - 输出长表 (trade_date, ts_code, pred)
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from alpha_model import (
    load_alpha_model,
    make_features,
    feature_columns,
    cross_sectional_robust_zscore,
)

CACHE = HERE / "cache"
ML = HERE.parent / "ml"
CKPT = ML / "m2alpha.pt"


def run_inference(panel: pd.DataFrame, ckpt_path: Path, tau: int = 8,
                  device: str = "cpu") -> pd.DataFrame:
    """对 panel 跑模型 → 返回长表 (trade_date, ts_code, pred)。"""
    # 1. 特征工程
    print(f"  feature engineering ...")
    panel = make_features(panel)
    fc = feature_columns(panel)
    print(f"    {len(fc)} features: {fc[:3]}...{fc[-3:]}")
    assert len(fc) == 35, f"expected 35 features, got {len(fc)}"

    # 2. 截面 z-score
    print("  cross-sectional z-score ...")
    panel = cross_sectional_robust_zscore(panel, fc)

    # 3. 排序 + 透视成 (ts_code, date, F) 3D 数组
    panel = panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    all_dates = sorted(panel["trade_date"].unique())
    if len(all_dates) < tau:
        raise ValueError(f"need >= {tau} days of data, got {len(all_dates)}")
    all_codes = sorted(panel["ts_code"].unique())
    print(f"    universe: {len(all_codes)} stocks × {len(all_dates)} days")

    # 4. 加载模型
    print(f"  loading model: {ckpt_path}")
    model = load_alpha_model(str(ckpt_path), device=device)

    # 5. 对每一日（从第 tau 天起）跑推理
    print("  running inference ...")
    # 关键：每天只把"当天实际有 panel 数据"的股票喂给模型；零填充行不进 batch。
    # 否则带 inter-stock attention 的模型会被 padding 污染（peer-set 变了 → 所有 pred 跟着变），
    # 导致历史回测不稳定（每次 fetch 拉到的 universe 大小不同就会改一遍）。
    # 用 (ts_code, trade_date) 元组的集合来判断 raw 行是否存在。
    raw_keys = set(zip(panel["ts_code"].to_numpy(), panel["trade_date"].to_numpy()))
    has_data = np.array(
        [[(ts, d) in raw_keys for d in all_dates] for ts in all_codes]
    )  # (S, T) bool

    pivoted = {}
    for col in fc:
        pivoted[col] = panel.pivot(index="ts_code", columns="trade_date", values=col).reindex(
            index=all_codes, columns=all_dates).fillna(0.0).values
    X_full = np.stack([pivoted[c] for c in fc], axis=-1)             # (S, T, F)

    results = []
    with torch.no_grad():
        for t in range(tau - 1, len(all_dates)):
            d = all_dates[t]
            mask = has_data[:, t]                                    # 当天有数据的股票
            if not mask.any():
                continue
            sel_idx = np.flatnonzero(mask)
            X_win = torch.tensor(
                X_full[sel_idx, t - tau + 1:t + 1, :],
                dtype=torch.float32, device=device,
            )                                                        # (S_d, τ, F)
            out = model(X_win)                                       # (S_d, τ)
            scores = out[:, -1].cpu().numpy()                         # last-step signal
            for i, s in zip(sel_idx, scores):
                results.append({"trade_date": d, "ts_code": all_codes[i], "pred": float(s)})

    df = pd.DataFrame(results)
    print(f"  → {len(df)} predictions across {len(all_dates) - tau + 1} dates"
          f" (per-day avg {len(df) / max(len(all_dates) - tau + 1, 1):.0f} stocks)")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", default=str(CACHE / "panel.parquet"))
    parser.add_argument("--ckpt", default=str(CKPT))
    parser.add_argument("--out", default=str(CACHE / "preds.parquet"))
    parser.add_argument("--tau", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    print(f"[inference] loading panel: {args.panel}")
    panel = pd.read_parquet(args.panel)
    print(f"  panel rows: {len(panel)}")
    print(f"  trade_date range: {panel.trade_date.min()} → {panel.trade_date.max()}")

    preds = run_inference(panel, Path(args.ckpt), tau=args.tau, device=args.device)
    preds.to_parquet(args.out, index=False)
    print(f"[OK] saved → {args.out}  ({len(preds):,} rows)")

    # show today's top 10
    last_date = preds["trade_date"].max()
    top10 = preds[preds.trade_date == last_date].nlargest(10, "pred")
    print(f"\n[今日 Top 10 · {last_date}]")
    for r in top10.itertuples():
        print(f"  {r.ts_code}  pred={r.pred:+.3f}")


if __name__ == "__main__":
    main()
