"""AlphaModel — M²-Alpha 推理用模型定义。

只包含 production v3-gauss4 配置所需的最少模块；剥离了训练期才会用到的 gating / ortho
penalty / multi-horizon head / 可学习 PE / 多尺度回看等消融开关。
"""

from __future__ import annotations

import math
import torch
import torch.nn as nn


# ─────────────────────────────────────────────────────────────────────
# Positional encoding
# ─────────────────────────────────────────────────────────────────────

class SinusoidalPositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 64):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * -(math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, D)

    def get(self, T: int) -> torch.Tensor:
        return self.pe[:, :T]


# ─────────────────────────────────────────────────────────────────────
# Attention block (time-axis self-attn + cross-section attn + FFN)
# ─────────────────────────────────────────────────────────────────────

class AttentionBlock(nn.Module):
    """单层：causal time-axis attention + cross-stock attention + FFN，保持 (S, T, D)。"""

    def __init__(self, d_model: int, n_heads_intra: int = 4, n_heads_inter: int = 2,
                 ff_mult: int = 2, dropout: float = 0.1):
        super().__init__()
        self.intra_mha = nn.MultiheadAttention(d_model, n_heads_intra, dropout=dropout, batch_first=True)
        self.intra_norm = nn.LayerNorm(d_model)
        self.inter_mha = nn.MultiheadAttention(d_model, n_heads_inter, dropout=dropout, batch_first=True)
        self.inter_norm = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_model * ff_mult),
            nn.ReLU(),
            nn.Linear(d_model * ff_mult, d_model),
        )
        self.ffn_norm = nn.LayerNorm(d_model)
        self.drop = nn.Dropout(dropout)

    def forward(self, h: torch.Tensor, attn_mask: torch.Tensor) -> torch.Tensor:
        # time-axis attention（causal + 高斯距离先验，由 mask 承载）
        a, _ = self.intra_mha(h, h, h, attn_mask=attn_mask, need_weights=False)
        h = self.intra_norm(h + self.drop(a))

        # cross-stock attention: 转 (T, S, D) 让 S 当 sequence dim
        h_t = h.transpose(0, 1)
        b, _ = self.inter_mha(h_t, h_t, h_t, need_weights=False)
        h_t = h_t + self.drop(b)
        h = h_t.transpose(0, 1)
        h = self.inter_norm(h)

        # FFN
        h = self.ffn_norm(h + self.drop(self.ffn(h)))
        return h


# ─────────────────────────────────────────────────────────────────────
# AlphaModel
# ─────────────────────────────────────────────────────────────────────

class AlphaModel(nn.Module):
    """M²-Alpha 主模型。

    输入: x ∈ (S, T, F) — S 只股票 × T 时间步 × F 特征
    输出: scores ∈ (S, T) — 每只股票每个时间步一个预测分数；交易信号 = scores[:, -1]
    """

    def __init__(
        self,
        feat_dim: int = 35,
        d_model: int = 256,
        n_heads_intra: int = 4,
        n_heads_inter: int = 2,
        n_layers: int = 3,
        dropout: float = 0.1,
        gaussian_sigma: float = 4.0,        # production: time-distance 高斯衰减先验
    ):
        super().__init__()
        self.feat_dim = feat_dim
        self.d_model = d_model
        self.n_layers = n_layers
        self.gaussian_sigma = gaussian_sigma

        self.feat_proj = nn.Linear(feat_dim, d_model)
        self.posenc = SinusoidalPositionalEncoding(d_model)
        self.in_norm = nn.LayerNorm(d_model)
        self.blocks = nn.ModuleList([
            AttentionBlock(d_model, n_heads_intra, n_heads_inter, dropout=dropout)
            for _ in range(n_layers)
        ])
        self.head = nn.Linear(d_model, 1)   # 每步出 1 个 scalar

    def _build_mask(self, T: int, device) -> torch.Tensor:
        """causal mask + 高斯时间距离先验。
        允许位置 (j<=i) 加上 exp(-(j-i)^2 / 2σ²) 偏置；禁止位置 (j>i) 设 -inf。"""
        i = torch.arange(T, device=device).view(T, 1).float()
        j = torch.arange(T, device=device).view(1, T).float()
        bias = torch.exp(-((j - i) ** 2) / (2.0 * self.gaussian_sigma ** 2))
        allowed = (j <= i)
        return torch.where(allowed, bias, torch.full_like(bias, float("-inf")))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (S, T, F)
        S, T, F = x.shape
        h = self.feat_proj(x)
        h = h + self.posenc.get(T)
        h = self.in_norm(h)
        mask = self._build_mask(T, x.device)
        for block in self.blocks:
            h = block(h, mask)
        out = self.head(h).squeeze(-1)      # (S, T)
        return out


# ─────────────────────────────────────────────────────────────────────
# Checkpoint loader
# ─────────────────────────────────────────────────────────────────────

def load_alpha_model(ckpt_path: str, device: str = "cpu") -> AlphaModel:
    """从 m2alpha.pt 加载模型 + 元数据。

    Checkpoint 结构（训练时保存）:
        {
          'model_state':   nn.Module.state_dict(),
          'model_kwargs':  {...},           # 构造参数
          'feature_cols':  [...35 columns],
          'market_cols':   [...] | None,
          'tau':           8,
          'best_ic':       float,
          'history':       [...],
        }
    """
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)

    if isinstance(ckpt, dict) and "model_state" in ckpt:
        state = ckpt["model_state"]
        kwargs = ckpt.get("model_kwargs", {})
        # 从 ckpt 元数据构造 model；只保留 AlphaModel 认识的字段
        model_kwargs = {
            "feat_dim":       kwargs.get("feat_dim", 35),
            "d_model":        kwargs.get("d_model", 256),
            "n_heads_intra":  kwargs.get("n_heads_intra", 4),
            "n_heads_inter":  kwargs.get("n_heads_inter", 2),
            "n_layers":       kwargs.get("n_layers", 3),
            "dropout":        kwargs.get("dropout", 0.1),
            "gaussian_sigma": kwargs.get("gaussian_sigma", 4.0),
        }
    elif isinstance(ckpt, dict) and "state_dict" in ckpt:
        state, model_kwargs = ckpt["state_dict"], {}
    else:
        state, model_kwargs = ckpt, {}

    model = AlphaModel(**model_kwargs)
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    return model
