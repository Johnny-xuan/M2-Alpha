#!/usr/bin/env python3
"""Train the public M2-Alpha baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from m2alpha.training import train_baseline


def _load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "configs" / "baseline.json"))
    parser.add_argument("--panel", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--smoke", action="store_true", help="Run a tiny local smoke train on committed cache data.")
    args = parser.parse_args()

    cfg = _load_config(Path(args.config))
    panel = args.panel or cfg.get("panel", "build/cache/panel.parquet")
    out = args.out or cfg.get("output", "outputs/checkpoints/m2alpha_baseline.pt")
    training = dict(cfg.get("training", {}))
    if args.epochs is not None:
        training["epochs"] = args.epochs
    if args.device is not None:
        training["device"] = args.device
    if args.seed is not None:
        training["seed"] = args.seed
    if args.smoke:
        training["epochs"] = int(training.get("smoke_epochs", 1))
        training.setdefault("device", "cpu")

    result = train_baseline(
        panel_path=ROOT / panel if not Path(panel).is_absolute() else Path(panel),
        output_path=ROOT / out if not Path(out).is_absolute() else Path(out),
        tau=int(cfg.get("tau", 8)),
        model_kwargs=cfg.get("model", {}),
        training_kwargs=training,
        split=None if args.smoke else cfg.get("split"),
        label_price=str(cfg.get("label_price", "open")),
        smoke=args.smoke,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
