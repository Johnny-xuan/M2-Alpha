"""Public M2-Alpha model registry for the historical backtest site."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / "cache"
ML = ROOT / "ml"


@dataclass(frozen=True)
class ModelVersion:
    key: str
    public_id: str
    label: str
    title: str
    lineage: str
    checkpoint: Path
    preds_path: Path
    n_layers: int
    sha256: str
    role: str
    research_benchmark: dict[str, object]

    def public_metadata(self) -> dict:
        return {
            "key": self.key,
            "id": self.public_id,
            "label": self.label,
            "title": self.title,
            "lineage": self.lineage,
            "n_layers": self.n_layers,
            "role": self.role,
            "research_benchmark": self.research_benchmark,
        }


MODEL_VERSIONS: tuple[ModelVersion, ...] = (
    ModelVersion(
        key="m1m",
        public_id="m2alpha-m1m",
        label="M-1-M",
        title="M-1-M · full-factor 3-block",
        lineage="full-factor 3-block checkpoint",
        checkpoint=ML / "m2alpha-m1m.pt",
        preds_path=CACHE / "preds_m1m.parquet",
        n_layers=3,
        sha256="b2d12a39b2600369d3b14fbb6674365cf76f7e219f301a6f7539b135f92f3716",
        role="historical full-factor 3-block research curve",
        research_benchmark={
            "label": "research benchmark",
            "cum_pct": 239.12,
            "sharpe": 3.40,
            "max_dd_pct": -15.43,
            "basis": "compatible full-factor top1000 panel · n=5/cap20 · pool_rank=100 · sell_rank=200 · open execution · fee_rate=0.0013",
        },
    ),
    ModelVersion(
        key="m2m",
        public_id="m2alpha-m2m",
        label="M-2-M",
        title="M-2-M · full-factor 5-block",
        lineage="full-factor 5-block checkpoint",
        checkpoint=ML / "m2alpha-m2m.pt",
        preds_path=CACHE / "preds_m2m.parquet",
        n_layers=5,
        sha256="1588b22a7dbde0fda06f7db17c50d80c5d5250423bfd0cc326bab38e50432cd5",
        role="historical full-factor 5-block research highlight",
        research_benchmark={
            "label": "research benchmark",
            "cum_pct": 354.34,
            "sharpe": 3.99,
            "max_dd_pct": -17.68,
            "basis": "compatible full-factor top1000 panel · n=5/cap20 · pool_rank=100 · sell_rank=200 · open execution · fee_rate=0.0013",
        },
    ),
)

DEFAULT_MODEL_LABEL = "M-2-M"


def iter_model_versions() -> tuple[ModelVersion, ...]:
    return MODEL_VERSIONS


def model_keys() -> list[str]:
    return [version.label for version in MODEL_VERSIONS]


def get_model_version(key: str) -> ModelVersion:
    normalized = key.lower()
    for version in MODEL_VERSIONS:
        if normalized == version.label.lower():
            return version
    known = ", ".join(model_keys())
    raise KeyError(f"unknown model version {key!r}; expected one of: {known}")
