# M²-Alpha

<p align="center">
  <a href="https://johnny-xuan.github.io/M2-Alpha"><b>🌐 在线访问 →  johnny-xuan.github.io/M2-Alpha</b></a>
</p>

<p align="center">
  <a href="https://github.com/Johnny-xuan/M2-Alpha/actions/workflows/daily-update.yml">
    <img alt="Daily Update" src="https://github.com/Johnny-xuan/M2-Alpha/actions/workflows/daily-update.yml/badge.svg">
  </a>
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-c8f93d.svg">
  <img alt="Universe" src="https://img.shields.io/badge/Universe-CSI_300-1f232c.svg">
  <img alt="OOS Sharpe" src="https://img.shields.io/badge/OOS_Sharpe-2.93-c8f93d.svg">
</p>

> 自研深度学习量化模型，在中国 A 股沪深 300 上做 cross-sectional alpha selection。
> 配套一套完全公开的执行策略，并通过 GitHub Actions 每日 live tracking
> 持续生成 out-of-sample 样本 —— 把一份训练好的 checkpoint
> 变成一个持续自我验证的实验。

---

## 项目定位

本项目由以下三部分组成：

1. **自研模型** —— 从数据处理、label 设计、网络架构、训练循环到超参选型，
   全部由作者一人完成，使用 7 年 A 股数据训练（2017–2023）。不是 fork、不是
   论文复现、不依赖任何预训练 backbone。
2. **完整公开的执行策略** —— equal-weight top-10、industry-diversified、
   open-to-open 成交、双边 0.13% commission。所有规则逐条列于下方，
   回测口径与 live trading 完全一致。
3. **每日 live tracking** —— 每个交易日北京时间 18:30，GitHub Actions
   自动拉取最新数据、跑模型推理、写入 `docs/data/data.json`、commit + push，
   GitHub Pages 随之自动重新部署。

区别于一次性的静态 backtest 展示，本项目的实证记录通过 daily live tracking
**持续累积**：每过一个交易日，便新增一个真正意义上的 out-of-sample sample，
全过程记录在 `docs/data/data.json` 的 git history 中，公开可查、不可篡改。

---

## 它不是什么

- 不是荐股或投资咨询服务
- 不是公开募集的基金产品
- 不是已发表论文（例如 MASTER / HIST / IGMTF）的复现
- 不构成任何形式的投资建议、要约或诱导

---

## Out-of-sample 实测结果

测试区间：**2025-07 → 2026-05（11 个月连续 walk-forward）**

| Metric                            | Model        | CSI 300 Benchmark |
|-----------------------------------|--------------|-------------------|
| Cumulative return                 | **+121.2%**  | +24.8%            |
| Annualized return                 | ~+142%       | ~+27%             |
| Sharpe ratio (annualized)         | **2.93**     | –                 |
| Max drawdown                      | **−12.6%**   | –                 |
| Monthly excess win rate           | **82%** (9/11) | –               |
| Daily hit rate (top-10 vs index)  | **57.7%**    | –                 |
| Daily average excess              | **+0.32%**   | –                 |
| Per-pick hit rate                 | 51.0%        | –                 |
| Average daily turnover            | 34.8%        | –                 |

📊 实时数据与每日明细：[johnny-xuan.github.io/M2-Alpha](https://johnny-xuan.github.io/M2-Alpha)

所有数字均扣除双边 0.13% commission；采用严格 walk-forward OOS 协议，
决策时刻使用的特征均来自 `≤ t` 的信息。

---

## Live tracking pipeline

```
每个交易日北京时间 18:30 自动执行：

  ①  GitHub Actions cron 触发
  ②  fetch_data.py    用 AKShare 拉取当日 OHLCV + fundamentals
  ③  inference.py     加载 ml/m2alpha.pt 计算今日 cross-sectional scores
  ④  update_daily.py  增量更新 docs/data/data.json
  ⑤  git commit + push
  ⑥  GitHub Pages 自动重新部署
```

每一天的运行结果都会沉淀进 git history，构成一份**公开可审计**的连续 OOS 记录。

---

## Method overview

模型将选股建模为 **cross-sectional ranking task**：在每个交易日，
为每只股票输出一个 score，要求该 score 能正确排序"次日 cross-section
内的相对收益"。

几个关键设计（架构细节暂不公开）：

- **Cross-sectional z-score label** — 直接对齐下游"buy top-N"目标，
  模型学到的是排序而非数值
- **Per-timestep dense supervision** — lookback window 中每个时间步都被
  监督，T 倍 training gradient，而非仅监督最后一步
- **Causal time-axis self-attention** — 中间时间步不允许 attend 到决定
  label 的未来 input，从结构上排除 leakage
- **Per-date robust z-score normalization** — 仅在日内 cross-section 做，
  不跨日，天然避免另一类常见 leakage

### Anti-leakage guarantees

- **Time split 严格不交叠**：train 2017–2023 / valid 2024–2025H1 /
  test 2025-07 → 2026-05
- **Labels** 形如 `close[t+2] / close[t+1] − 1`（T+1 compliant），
  features 严格使用 `≤ t` 的信息
- **CSI 300 universe** 用 forward-fill 处理月度 rebalance，**不**
  使用未来才公布的成分股调整
- **Causal mask** 配套单元测试

---

## Trading strategy（完整披露）

| Rule              | Value                                                    |
|-------------------|----------------------------------------------------------|
| Universe          | CSI 300 成分股（月度刷新）                                 |
| Pool              | 当日模型 score 前 30                                       |
| Position count    | 10                                                       |
| Weighting         | Equal-weight（约 10% / 只）                                |
| Industry cap      | 同一申万一级行业 ≤ 2 只                                    |
| Sell rule         | 持仓 score 掉出 top-50 才卖出（lazy sell / 滞后带）         |
| Execution         | 次日 open price（不参与盘中博弈）                          |
| Commission        | 0.13% bilateral                                          |
| Initial NAV       | 1,000,000 CNY                                            |

Strategy ablation 结果：equal-weight ≫ score-weighted ≫ inverse-volatility。
Stop-loss overlay 在 trending market 中拖累整体表现，最终未采用。

---

## 本地复现

```bash
git clone https://github.com/Johnny-xuan/M2-Alpha.git
cd M2-Alpha
pip install -r requirements.txt

python build/fetch_data.py        # 约 3 分钟，使用 AKShare 拉取数据
python build/inference.py         # CPU 推理约 30 秒
python build/update_daily.py      # 增量更新 docs/data/data.json

cd docs && python3 -m http.server 8765
open http://localhost:8765
```

模型参数约 600K，CPU 推理 sub-second per day。Apple Silicon / x86 Linux /
Windows 均可运行，无需 GPU。

---

## 项目结构

```
M2-Alpha/
├── docs/                         GitHub Pages 站点
│   ├── index.html / styles.css
│   ├── js/                       ES modules：navbar / hero / picks /
│   │                              scorecard / equity-chart / monthly / holdings
│   └── data/data.json            自动每日更新
├── ml/
│   └── m2alpha.pt                训练完成的 checkpoint (~2.4 MB)
├── build/
│   ├── alpha_model/              推理用 Python 包
│   │   ├── model.py              架构定义 + load_alpha_model()
│   │   ├── features.py           35 个 basic features
│   │   └── normalize.py          cross-sectional robust z-score
│   ├── fetch_data.py             AKShare → cache/*.parquet
│   ├── inference.py              checkpoint → preds.parquet
│   └── update_daily.py           preds → docs/data/data.json（增量）
├── .github/workflows/
│   └── daily-update.yml          cron 北京时间 18:30，周一至周五
├── requirements.txt
└── LICENSE                       Apache 2.0
```

---

## Limitations

- **Sample size 有限**：11 个月 OOS 数据虽然 suggestive，但远未达到 conclusive
  的程度。需要更长的 live record 才能形成更可靠的结论。
- **单一市场**：仅在中国 A 股 / CSI 300 universe 上训练与验证，未在其他
  市场或其他股票池上做 generalization 测试。
- **Slippage 与 market impact** 仅做基础建模。真实执行结果可能与回测存在
  系统性差异。
- **Regime risk**：所有训练得到的模型都会随 market structure 的演变而衰减，
  本模型也不例外。
- **数据源风险**：AKShare 通过爬取公开 endpoint 提供数据，字段 schema 变动
  可能导致 daily pipeline 中断。

---

## 免责声明

本项目为研究与工程项目。本 repo 与 [live 站点](https://johnny-xuan.github.io/M2-Alpha)
所示的所有数据**不构成投资建议、要约或诱导**。过去的回测表现**不能预测未来收益**。
使用本项目所做的任何交易决策，作者不承担任何责任。

---

## License

[Apache License 2.0](LICENSE) — 允许商用、修改、分发；包含明确的专利授权条款。

---

<p align="center">
  <sub>Designed, trained, and maintained by a single author · Live since May 2026</sub>
</p>
