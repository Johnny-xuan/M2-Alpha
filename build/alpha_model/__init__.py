"""
alpha_model — M²-Alpha 推理所需最小代码集合。

模块：
  - model.py        : AlphaModel (PyTorch nn.Module) + 加载函数
  - features.py     : 35-feature basic 集合（量价 + 基本面 + 资金流向）
  - normalize.py    : 截面 robust z-score
"""

from .model import AlphaModel, load_alpha_model
from .features import make_features, feature_columns
from .normalize import cross_sectional_robust_zscore

__all__ = [
    "AlphaModel",
    "load_alpha_model",
    "make_features",
    "feature_columns",
    "cross_sectional_robust_zscore",
]
