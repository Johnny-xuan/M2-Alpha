"""init.py — 一次性历史回填。

什么时候用：
  · 第一次部署项目（本地或新 fork）
  · 想换业绩起点（修改 START_SIGNAL_DATE）
  · 换了 M-1-M/M-2-M 研究曲线模型权重
  · panel.parquet / preds_m2_*.parquet 损坏需要重建

跑这个之前确保：
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt

跑完会产出：
  build/cache/panel.parquet    从 2025-04-01 起的 warmup + 公开股票池日线 panel
  build/cache/csi300.parquet   指数日线
  build/cache/basic.csv         成分股 + 行业映射
  build/cache/source_enrichment.json  AKShare/efinance 增强记录
  build/cache/preds_m1m.parquet / preds_m2m.parquet 公开研究曲线模型的全期预测
  docs/data/data.json           网站展示数据

之后可按需手动重建网站展示数据；当前公开页面不作为自动每日交易服务发布。
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# 回填起点：比 2025-07-10 回测窗口提前约 60 个交易日，
# 给 20/30/60 日 rolling features 留足 warmup。
DEFAULT_START = "2025-04-01"


def run(cmd: list[str]):
    print(f"\n$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        sys.exit(f"[init] {cmd[0]} 失败，退出码 {res.returncode}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_START,
                        help=f"回填起点 (默认 {DEFAULT_START})")
    args = parser.parse_args()

    t0 = datetime.now()
    print(f"[init] {t0:%Y-%m-%d %H:%M:%S}  start={args.start}")

    py = sys.executable
    run([py, "build/fetch_data.py", "--start", args.start])
    run([py, "build/enrich_data.py"])
    run([py, "build/inference.py"])
    run([py, "build/update_backtest_site.py"])

    dt = (datetime.now() - t0).total_seconds()
    print(f"\n[init] 完成，耗时 {dt:.0f}s。")
    print(f"\n下一步：git add build/cache/*.parquet build/cache/basic.csv docs/data/data.json")
    print(f"        git commit -m 'init: 历史数据回填 from {args.start}'")
    print(f"        git push")


if __name__ == "__main__":
    main()
