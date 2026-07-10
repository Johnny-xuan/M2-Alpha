"""Training helpers for the public M2-Alpha baseline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from .dataset import DenseWindowDataset
from .features import feature_columns, make_features
from .labels import cross_sectional_zscore_label, make_next_close_return, make_next_open_return
from .model import AlphaModel
from .normalize import cross_sectional_robust_zscore


def choose_device(pref: str = "auto") -> torch.device:
    if pref == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(pref)


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def prepare_panel(panel: pd.DataFrame, label_price: str = "open") -> tuple[pd.DataFrame, list[str]]:
    """Build features, labels, and normalized model input columns."""
    panel = panel.copy()
    panel["trade_date"] = panel["trade_date"].astype(str)
    featured = make_features(panel)
    fc = feature_columns(featured)
    if len(fc) != 35:
        raise ValueError(f"expected 35 features, got {len(fc)}")

    raw = make_next_open_return(featured) if label_price == "open" else make_next_close_return(featured)
    featured["label_raw"] = raw
    featured["label"] = cross_sectional_zscore_label(featured, "label_raw")
    featured = cross_sectional_robust_zscore(featured, fc)
    return featured, fc


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _run_epoch(
    model: AlphaModel,
    dataset: DenseWindowDataset,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    rng: np.random.Generator,
) -> tuple[float, float]:
    train = optimizer is not None
    model.train(train)
    indices = np.arange(len(dataset))
    if train:
        rng.shuffle(indices)

    losses: list[float] = []
    ics: list[float] = []
    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for i in indices:
            sample = dataset[int(i)]
            if sample.x.numel() == 0:
                continue
            x = sample.x.to(device)
            y = sample.y.to(device)
            pred = model(x)
            loss = torch.mean((pred - y) ** 2)
            if train:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()
            losses.append(float(loss.detach().cpu()))
            ic = _safe_corr(
                pred[:, -1].detach().cpu().numpy(),
                y[:, -1].detach().cpu().numpy(),
            )
            if ic is not None and np.isfinite(ic):
                ics.append(ic)

    mean_loss = float(np.mean(losses)) if losses else float("nan")
    mean_ic = float(np.mean(ics)) if ics else float("nan")
    return mean_loss, mean_ic


def _split_dates(
    dates: list[str],
    split: dict[str, Any] | None,
    smoke: bool,
    smoke_train_days: int,
    smoke_valid_days: int,
) -> tuple[list[str], list[str]]:
    if smoke:
        need = smoke_train_days + smoke_valid_days
        use = dates[-need:] if len(dates) >= need else dates
        return use[:smoke_train_days], use[smoke_train_days:smoke_train_days + smoke_valid_days]

    if split and split.get("train") and split.get("valid"):
        tr0, tr1 = split["train"]
        va0, va1 = split["valid"]
        train_dates = [d for d in dates if tr0 <= d <= tr1]
        valid_dates = [d for d in dates if va0 <= d <= va1]
        if train_dates and valid_dates:
            return train_dates, valid_dates
        raise ValueError(
            "configured split produced no train/valid dates for this panel; "
            "use --smoke for committed cache data or provide a matching panel"
        )

    cut = max(1, int(len(dates) * 0.75))
    return dates[:cut], dates[cut:]


def train_baseline(
    panel_path: str | Path,
    output_path: str | Path,
    *,
    tau: int = 8,
    model_kwargs: dict[str, Any] | None = None,
    training_kwargs: dict[str, Any] | None = None,
    split: dict[str, Any] | None = None,
    label_price: str = "open",
    smoke: bool = False,
) -> dict[str, Any]:
    """Train the public baseline and save a checkpoint compatible with inference."""
    model_kwargs = dict(model_kwargs or {})
    training_kwargs = dict(training_kwargs or {})
    epochs = int(training_kwargs.get("epochs", 40))
    lr = float(training_kwargs.get("lr", 1e-5))
    weight_decay = float(training_kwargs.get("weight_decay", 1e-4))
    seed = int(training_kwargs.get("seed", 42))
    patience = int(training_kwargs.get("patience", 10))
    device = choose_device(str(training_kwargs.get("device", "auto")))
    min_stocks = int(training_kwargs.get("min_stocks_per_day", 30))
    smoke_train_days = int(training_kwargs.get("smoke_train_days", 8))
    smoke_valid_days = int(training_kwargs.get("smoke_valid_days", 2))

    set_seed(seed)
    rng = np.random.default_rng(seed)

    raw = pd.read_parquet(panel_path)
    panel, feature_cols = prepare_panel(raw, label_price=label_price)
    all_ds = DenseWindowDataset(panel, feature_cols, tau, min_stocks_per_day=min_stocks)
    if len(all_ds) < 3:
        raise ValueError(f"not enough valid days after feature/label construction: {len(all_ds)}")
    train_dates, valid_dates = _split_dates(
        all_ds.dates, split, smoke, smoke_train_days=smoke_train_days, smoke_valid_days=smoke_valid_days
    )
    if not train_dates or not valid_dates:
        raise ValueError(f"empty train/valid split: train={len(train_dates)} valid={len(valid_dates)}")

    train_ds = DenseWindowDataset(panel, feature_cols, tau, allowed_dates=train_dates, min_stocks_per_day=min_stocks)
    valid_ds = DenseWindowDataset(panel, feature_cols, tau, allowed_dates=valid_dates, min_stocks_per_day=min_stocks)

    model_kwargs.setdefault("feat_dim", len(feature_cols))
    model = AlphaModel(**model_kwargs).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    history: list[dict[str, Any]] = []
    best_ic = -float("inf")
    best_state = None
    bad = 0
    for ep in range(epochs):
        train_loss, train_ic = _run_epoch(model, train_ds, optimizer, device, rng)
        valid_loss, valid_ic = _run_epoch(model, valid_ds, None, device, rng)
        rec = {
            "epoch": ep,
            "train_loss": train_loss,
            "train_ic": train_ic,
            "valid_loss": valid_loss,
            "valid_ic": valid_ic,
            "train_days": len(train_ds),
            "valid_days": len(valid_ds),
        }
        history.append(rec)
        print(
            f"ep {ep:02d} train_loss={train_loss:.5f} valid_loss={valid_loss:.5f} "
            f"train_ic={train_ic:+.4f} valid_ic={valid_ic:+.4f}"
        )
        score = valid_ic if np.isfinite(valid_ic) else -float("inf")
        if score > best_ic:
            best_ic = score
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
        if bad >= patience:
            print(f"early stop at epoch {ep}")
            break

    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ckpt = {
        "model_state": best_state,
        "model_name": "m2alpha",
        "model_kwargs": {
            "feat_dim": len(feature_cols),
            "d_model": int(model_kwargs.get("d_model", 128)),
            "n_heads_intra": int(model_kwargs.get("n_heads_intra", 4)),
            "n_heads_inter": int(model_kwargs.get("n_heads_inter", 2)),
            "n_layers": int(model_kwargs.get("n_layers", 3)),
            "dropout": float(model_kwargs.get("dropout", 0.1)),
            "gaussian_sigma": float(model_kwargs.get("gaussian_sigma", 4.0)),
        },
        "feature_cols": feature_cols,
        "tau": tau,
        "label_price": label_price,
        "best_ic": best_ic,
        "history": history,
    }
    torch.save(ckpt, output_path)
    return {
        "output": str(output_path),
        "best_ic": best_ic,
        "history": history,
        "train_days": len(train_ds),
        "valid_days": len(valid_ds),
        "feature_cols": feature_cols,
    }
