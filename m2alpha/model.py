"""Baseline M2-Alpha model used by the public training path."""

from __future__ import annotations

import math

import torch
import torch.nn as nn


class SinusoidalPositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 64):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * -(math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))

    def get(self, t: int) -> torch.Tensor:
        return self.pe[:, :t]


class M2Block(nn.Module):
    """One Micro/Macro block: causal time attention, cross-stock attention, and FFN."""

    def __init__(
        self,
        d_model: int,
        n_heads_intra: int = 4,
        n_heads_inter: int = 2,
        ff_mult: int = 2,
        dropout: float = 0.1,
    ):
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
        a, _ = self.intra_mha(h, h, h, attn_mask=attn_mask, need_weights=False)
        h = self.intra_norm(h + self.drop(a))

        h_t = h.transpose(0, 1)
        b, _ = self.inter_mha(h_t, h_t, h_t, need_weights=False)
        h = self.inter_norm((h_t + self.drop(b)).transpose(0, 1))

        h = self.ffn_norm(h + self.drop(self.ffn(h)))
        return h


class AlphaModel(nn.Module):
    """M2-Alpha baseline.

    Input shape is `(S, T, F)`: stocks, lookback window, features.
    Output shape is `(S, T)`: one cross-sectional score per stock per time step.
    """

    def __init__(
        self,
        feat_dim: int = 35,
        d_model: int = 128,
        n_heads_intra: int = 4,
        n_heads_inter: int = 2,
        n_layers: int = 3,
        dropout: float = 0.1,
        gaussian_sigma: float = 4.0,
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
            M2Block(d_model, n_heads_intra, n_heads_inter, dropout=dropout)
            for _ in range(n_layers)
        ])
        self.head = nn.Linear(d_model, 1)

    def _build_mask(self, t: int, device) -> torch.Tensor:
        i = torch.arange(t, device=device).view(t, 1).float()
        j = torch.arange(t, device=device).view(1, t).float()
        bias = torch.exp(-((j - i) ** 2) / (2.0 * self.gaussian_sigma ** 2))
        allowed = j <= i
        return torch.where(allowed, bias, torch.full_like(bias, float("-inf")))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, t, _ = x.shape
        h = self.feat_proj(x)
        h = h + self.posenc.get(t)
        h = self.in_norm(h)
        mask = self._build_mask(t, x.device)
        for block in self.blocks:
            h = block(h, mask)
        return self.head(h).squeeze(-1)


def load_alpha_model(ckpt_path: str, device: str = "cpu") -> AlphaModel:
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    kwargs = ckpt.get("model_kwargs", {}) if isinstance(ckpt, dict) else {}
    model_kwargs = {
        "feat_dim": kwargs.get("feat_dim", 35),
        "d_model": kwargs.get("d_model", 128),
        "n_heads_intra": kwargs.get("n_heads_intra", 4),
        "n_heads_inter": kwargs.get("n_heads_inter", 2),
        "n_layers": kwargs.get("n_layers", 3),
        "dropout": kwargs.get("dropout", 0.1),
        "gaussian_sigma": kwargs.get("gaussian_sigma", 4.0),
    }
    state = ckpt["model_state"] if isinstance(ckpt, dict) and "model_state" in ckpt else ckpt
    model = AlphaModel(**model_kwargs)
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    return model
