# M²-Alpha

<p align="center">
  <a href="https://johnny-xuan.github.io/M2-Alpha"><b>🌐 Live →  johnny-xuan.github.io/M2-Alpha</b></a>
</p>

<p align="center">
  <a href="https://github.com/Johnny-xuan/M2-Alpha/actions/workflows/daily-update.yml">
    <img alt="Daily Update" src="https://github.com/Johnny-xuan/M2-Alpha/actions/workflows/daily-update.yml/badge.svg">
  </a>
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-c8f93d.svg">
  <img alt="Universe" src="https://img.shields.io/badge/Universe-CSI_300-1f232c.svg">
  <img alt="OOS Sharpe" src="https://img.shields.io/badge/OOS_Sharpe-3.12-c8f93d.svg">
</p>

**M²-Alpha** 是一个自研的 A 股深度学习量化模型，配套一套完全公开的执行规则
（strategy），并通过 GitHub Actions 实现**每个交易日自动更新一次**的 live OOS
tracking pipeline。

模型 + 策略 + 数据 + 推理 + 部署，全链路开源；每过一个交易日，OOS 记录在
`docs/data/data.json` 的 git history 中新增一条。

---

## Overview

| 组成部分        | 内容                                                          |
|-----------------|---------------------------------------------------------------|
| **模型**        | 自研架构，数据预处理 / label / 网络 / 训练循环 / 超参完全独立开发；用 7 年 A 股数据训练；checkpoint 仅 2.4 MB，CPU 推理即可。 |
| **策略**        | 6 条规则全公开（等权 top-10 / industry-diversified / open-to-open / 滞后带换仓，详见下表）。回测净值未扣手续费，实际跟单会低于此处展示。 |
| **Live pipeline** | GitHub Actions cron 每个交易日北京时间 20:00 自动触发：增量拉数据 → 重跑推理 → 重建 `data.json` → commit panel/preds + data.json → Pages 重新部署。 |
| **结果留痕**     | 所有每日 signal 与 OOS 结果通过 `data.json` 的 git history 永久公开，可审计、不可篡改。 |

区别于一次性的静态回测项目，**本项目核心理念是把训练好的 checkpoint 投放到持续
live tracking 中**：静态 backtest 容易 overfit，连续 daily OOS 才是真正的考核
方式。

## Non-Goals

- 不是荐股 / 投顾 / 基金产品 / 收费服务
- 不是已发表论文（MASTER / HIST / IGMTF 等）的复现
- 不构成任何形式的投资建议、要约或诱导

---

## 11-Month OOS Backtest (2025-07 → 2026-05)

| Metric                            | Model         | CSI 300 |
|-----------------------------------|---------------|---------|
| Cumulative return                 | **+137.7%**   | +23.1%  |
| Sharpe (annualized)               | **3.12**      | –       |
| Max drawdown                      | **−14.6%**    | –       |
| Monthly excess win rate           | **72.7%** (8/11) | –    |
| Daily hit rate (top-10 vs index)  | **50.6%**     | –       |
| Daily average excess              | **+0.33%**    | –       |

回测净值按 open-to-open 计算，**未扣手续费 / 印花税 / 滑点**，实际跟单收益会低于此处展示。
实时数据 + 每日明细见 [live 站点](https://johnny-xuan.github.io/M2-Alpha)。

---

## Strategy (Fully Disclosed)

| Rule           | Value                                                |
|----------------|------------------------------------------------------|
| Universe       | CSI 300 成分股（每次 BaoStock 刷新）                    |
| Selection      | 按 score 降序遍历全部 300 只，受行业上限约束直到凑满 10 只 |
| Position count | 10                                                   |
| Weighting      | Equal-weight（≈ 10% / 只）                            |
| Industry cap   | 同一申万行业 ≤ 2 只                                    |
| Sell rule      | 持仓 score 掉出 top-50 才卖（lazy sell / 滞后带）       |
| Execution      | 次日 open price（开盘买开盘卖）                        |
| Commission     | **未扣**（回测净值为理论上限）                          |
| Initial NAV    | 1,000,000 CNY                                        |

Strategy ablation 测过 score-weighting / inverse-volatility weighting /
stop-loss overlay，均未采纳。equal-weight + lazy sell 在多种 market regime
下表现最稳健。

---

## Live Tracking Pipeline

```
每个交易日北京时间 20:00：

  ①  GitHub Actions cron 触发
  ②  fetch_data.py --incremental    BaoStock 仅拉新增日子，append 到 panel.parquet
  ③  inference.py                    在全期 panel 上重跑 m2alpha.pt，覆盖 preds.parquet
  ④  update_daily.py                 strategy.py 模拟全期 → 重建 docs/data/data.json
  ⑤  git commit panel/preds/data.json + push
  ⑥  GitHub Pages 自动重新部署
```

20:00 是为了等 BaoStock 当日数据全部就绪（17:30 后陆续刷出，留 2.5 小时缓冲）。
GitHub cron 不是严格准时，通常延迟 5–15 分钟。Daily pipeline 最常见的
breakage 来自 BaoStock 字段 schema 变更 —— 公开数据爬虫的本质风险。

首次部署 / 想换业绩起点 / 换模型权重时跑一次性回填：

```
python build/init.py    # 等价于 fetch_data --start + inference + update_daily
```

---

## Local Reproduction

```bash
git clone https://github.com/Johnny-xuan/M2-Alpha.git
cd M2-Alpha
pip install -r requirements.txt

# 仓库内已 commit panel/preds 缓存，直接看历史/继续 daily 用 --incremental
python build/fetch_data.py --incremental    # 只拉新增日子，几秒
python build/inference.py                    # CPU 全量重跑，约 30 秒
python build/update_daily.py                 # 重建 docs/data/data.json

# 或一次性回填全部历史（换模型 / 换起点时用）
python build/init.py                         # 约 10 分钟

cd docs && python3 -m http.server 8765
open http://localhost:8765
```

模型仅 ~600K 参数，CPU 推理 sub-second per day。Apple Silicon / x86 Linux /
Windows 均可运行，**不需要 GPU**。

---

## Project Structure

```
M2-Alpha/
├── docs/                         GitHub Pages 站点
│   ├── index.html / styles.css
│   ├── js/                       ES modules: navbar / hero / picks /
│   │                              scorecard / equity-chart / monthly / holdings
│   └── data/data.json            每日自动更新
├── ml/
│   └── m2alpha.pt                训练完成的 checkpoint (~2.4 MB)
├── build/
│   ├── alpha_model/              推理用的最小 Python 包
│   │   ├── model.py              架构定义 + load_alpha_model()
│   │   ├── features.py           35 个 basic features
│   │   └── normalize.py          cross-sectional robust z-score
│   ├── fetch_data.py             BaoStock → cache/*.parquet（支持 --incremental）
│   ├── inference.py              checkpoint → preds.parquet
│   ├── strategy.py               行业分散 top-10 + 滞后带 simulator
│   ├── update_daily.py           preds → docs/data/data.json（完全重建）
│   ├── init.py                   一次性回填编排器
│   └── cache/                    panel/preds/csi300/basic 状态文件（commit 进 git）
├── .github/workflows/
│   └── daily-update.yml          cron 北京时间 20:00，周一至周五
├── requirements.txt
└── LICENSE
```

---

## Known Caveats

- **Sample size 持续累积中**：初始 OOS 段（2025-07 → 2026-05）约 11 个月，
  之后每个交易日通过 live tracking 新增一个样本 —— 时间越久样本越具说服力，
  当前结论仍为 suggestive 而非 conclusive。
- **单一市场**：仅在 CSI 300 universe 上训练与验证，未做 cross-market generalization 测试。
- **Slippage / market impact 仅做基础建模**。真实 execution 会与回测存在系统性差异。
- **Regime decay**：所有训练得到的模型最终都会随 market structure 演变而衰减；
  本模型也不例外。这也是项目坚持 live tracking 而非停留在静态回测的核心动机。
- **数据源风险**：BaoStock 走自家协议，字段 schema 变更会直接中断 daily pipeline。

---

## Disclaimer

研究与工程项目。本 repo 与 [live 站点](https://johnny-xuan.github.io/M2-Alpha)
所有数据**不构成投资建议、要约或诱导**。过去的回测**不预测未来收益**。
据此进行的任何交易决策由使用者自行承担风险。

---

## License

[Apache License 2.0](LICENSE) — 允许商用 / 修改 / 分发；包含明确的专利授权条款。
