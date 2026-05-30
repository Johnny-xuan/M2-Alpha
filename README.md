# M²-Alpha · A 股每日选股参考

<p align="center">
  <a href="https://johnny-xuan.github.io/M2-Alpha"><b>📈 在线访问 →  johnny-xuan.github.io/M2-Alpha</b></a>
</p>

> **M²-Alpha** (Micro-Macro Alpha Engine) · 基于深度学习的 A 股沪深 300 每日选股参考。
> 每个交易日 18:30 自动给出次日开盘的 Top 10 推荐 · 11 个月历史回测累计 +121.2% · 月度胜率 82%。

---

## 🎯 这是什么

一个**全自动运行**的 A 股选股参考网站：

- 🤖 **深度学习模型** 每个交易日盘后自动给出沪深 300 池里最受看好的 10 只股票
- 📊 **公开透明**的交易策略（等权 10 只 / 行业分散 / 开盘买开盘卖）
- 📈 **真实历史回测**：11 个月连续滚动跑出 +121.2% / Sharpe 2.93 / 最大回撤 -12.6%
- 🔍 **预测复盘**：每个历史交易日的 Top 10 推荐 + 实际涨幅，让你看到模型有没有真本事
- ⚙️ **自动更新**：GitHub Actions 每个交易日 18:30 自动跑模型、更新数据、重新部署

---

## ⚡ 实测成绩 · 11 个月连续回测

| 指标 | 数值 | 出处 |
|---|---|---|
| 累计收益 | **+121.2%** | 100 万 → 221 万 |
| 跑赢沪深 300 | **+96.4 pp** | 同期基准 +24.8% |
| 月度胜率 | **82%** | 11 个月中 9 个月跑赢 |
| 夏普比 | **2.93** | 年化收益 / 年化波动 |
| 最大回撤 | **-12.6%** | 单次最大 |
| 日级胜率 | **57.7%** | 单日 Top 10 跑赢基准的比例 |

📌 **所有数字来自策略 A（等权 10 只 + 行业分散 + 开盘买卖 + 双边 0.13% 手续费）真实历史回测，不含任何未来信息**。

---

## 🚦 如何参考使用

每个交易日 19:00 后访问本站，按下面流程操作：

1. **查看「今日推荐」** — 模型给出的次日开盘 Top 10
2. **次日 09:25** 在自己的券商交易软件里录入 10 只市价买单（每只配 10% 资金）
3. **第三日 09:30** 集合竞价开盘卖出，回笼资金。再访问本站看新的清单，循环操作。

详见网站 [「如何使用」](https://johnny-xuan.github.io/M2-Alpha#howto) 章节。

---

## ⚠️ 重要声明

- 本站为深度学习模型预测的**公开展示与研究项目**，**不构成任何形式的投资建议**。
- **过去的收益不代表未来表现** — 模型有效性可能随市场结构变化而衰减。
- 历史回测中也曾出现单日 **-9.21%** 的最差日，跟单需有承受短期回撤的心理准备。
- 建议至少配置 **10 万元以上**本金参与，否则手续费占比过高。
- 据此进行的任何交易决策，**请自行承担风险**。

---

## 🏗️ 项目结构

```
M2-Alpha/
├── docs/                       ← GitHub Pages 部署目录
│   ├── index.html / styles.css
│   ├── js/                     ES modules
│   │   ├── main.js             入口
│   │   ├── navbar.js / hero.js / picks.js
│   │   ├── scorecard.js        预测复盘 + 日期范围选择
│   │   ├── equity-chart.js     净值曲线 + 十字光标 tooltip
│   │   ├── monthly.js / holdings.js
│   │   └── utils.js
│   └── data/
│       └── data.json           每日自动更新
├── ml/
│   └── m2alpha.pt              模型权重 (PyTorch checkpoint)
├── build/                      数据 + 推理脚本
│   ├── fetch_data.py           AKShare 拉数据
│   ├── inference.py            模型推理
│   ├── build_data.py           组装 data.json
│   └── build_scorecard.py      复盘回填
├── .github/workflows/
│   └── daily-update.yml        每日 18:30 (北京) 定时任务
├── requirements.txt
├── LICENSE                     Apache 2.0
└── README.md
```

## 🛠️ 本地运行

```bash
# 1. 启动一个静态 HTTP server（任何方式都行）
cd docs && python3 -m http.server 8765

# 2. 浏览器打开
open http://localhost:8765
```

## 🤖 自动化更新（GitHub Actions）

每个交易日（周一到周五）北京时间 18:30 自动执行：

1. **拉数据** — 用 AKShare 获取沪深 300 当日量价 + 基本面
2. **跑推理** — 加载 `ml/m2alpha.pt` 输出新一日 Top 10
3. **回填复盘** — 对 D-2 的预测计算实际收益
4. **重建 `data.json`** + commit + push
5. GitHub Pages **自动重新部署**

工作流定义：[.github/workflows/daily-update.yml](.github/workflows/daily-update.yml)

## 📜 协议

[Apache License 2.0](LICENSE) — 允许商用、修改、分发；带专利授权条款。

---

<p align="center">
  <sub>Made with 🍵 · A research & demonstration project · Not investment advice</sub>
</p>
