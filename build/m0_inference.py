"""Generate the M-0-M public-baseline prediction cache from the current panel."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from inference import run_inference


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PANEL = HERE / "cache" / "panel.parquet"
DEFAULT_CHECKPOINT = ROOT / "ml" / "m2alpha.pt"
DEFAULT_OUTPUT = HERE / "cache" / "preds_m0m.parquet"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate M-0-M predictions for the public baseline update path."
    )
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tau", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    if not args.panel.exists():
        raise FileNotFoundError(f"missing panel: {args.panel}")
    if not args.checkpoint.exists():
        raise FileNotFoundError(f"missing M-0-M checkpoint: {args.checkpoint}")

    panel = pd.read_parquet(args.panel)
    print(
        f"[M-0-M inference] panel={args.panel} rows={len(panel):,} "
        f"dates={panel['trade_date'].min()}..{panel['trade_date'].max()}"
    )
    predictions = run_inference(
        panel,
        args.checkpoint,
        tau=args.tau,
        device=args.device,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(args.out, index=False)
    latest = predictions["trade_date"].max()
    print(
        f"[OK] M-0-M predictions saved to {args.out} "
        f"({len(predictions):,} rows; latest={latest})"
    )


if __name__ == "__main__":
    main()
