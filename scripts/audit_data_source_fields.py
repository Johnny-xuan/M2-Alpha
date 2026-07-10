#!/usr/bin/env python3
"""Audit whether an A-share panel can support the M2-Alpha feature contract.

The tool intentionally audits panel files instead of fetching third-party data.
This keeps optional data-source experiments outside the default public pipeline:
build a candidate panel with any provider, then compare its field coverage here.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from m2alpha.features import feature_columns, make_features  # noqa: E402


REQUIRED_COLUMNS = [
    "trade_date",
    "ts_code",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "pct_chg",
    "vol",
    "amount",
    "vwap",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "net_mf_amount",
    "buy_sm_amount",
    "buy_lg_amount",
    "buy_elg_amount",
]

CRITICAL_SIGNAL_COLUMNS = [
    "turnover_rate_f",
    "volume_ratio",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "net_mf_amount",
    "buy_sm_amount",
    "buy_lg_amount",
    "buy_elg_amount",
]

MONEY_FLOW_COLUMNS = {
    "net_mf_amount",
    "buy_sm_amount",
    "buy_lg_amount",
    "buy_elg_amount",
}


@dataclass
class PanelSpec:
    name: str
    path: Path


def parse_panel_spec(raw: str) -> PanelSpec:
    if "=" in raw:
        name, path = raw.split("=", 1)
        name = name.strip()
    else:
        path = raw
        name = Path(path).stem
    if not name:
        raise argparse.ArgumentTypeError(f"empty panel name in {raw!r}")
    return PanelSpec(name=name, path=Path(path).expanduser())


def read_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported panel format: {path} (use .parquet or .csv)")


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def pct(n: int | float, d: int | float) -> float:
    if not d:
        return 0.0
    return round(float(n) / float(d) * 100.0, 2)


def status_for_column(df: pd.DataFrame, column: str) -> dict:
    rows = len(df)
    if column not in df.columns:
        return {
            "column": column,
            "status": "missing",
            "non_null_pct": 0.0,
            "non_zero_pct": 0.0,
            "unique": 0,
            "note": "column absent",
        }

    series = df[column]
    non_null = int(series.notna().sum())
    unique = int(series.nunique(dropna=True))
    note = ""

    numeric = numeric_series(df, column)
    finite = numeric[np.isfinite(numeric)]
    non_zero = int((finite.abs() > 1e-12).sum())

    if non_null == 0:
        status = "empty"
        note = "all values are null"
    elif column in MONEY_FLOW_COLUMNS and non_zero == 0:
        status = "neutral"
        note = "all numeric values are zero; behaves like a stub"
    elif column == "volume_ratio" and non_zero == 0:
        status = "inactive"
        note = "no non-zero volume-ratio signal"
    elif unique <= 1 and column in CRITICAL_SIGNAL_COLUMNS:
        status = "constant"
        note = "single non-null value; little cross-sectional signal"
    else:
        status = "active"

    if column == "turnover_rate_f" and "turnover_rate" in df.columns and non_null > 0:
        base = numeric_series(df, "turnover_rate")
        both = numeric.notna() & base.notna()
        if both.any():
            equal_share = float(np.isclose(numeric[both], base[both], equal_nan=False).mean())
            if equal_share >= 0.99:
                status = "proxy"
                note = "matches turnover_rate on >=99% comparable rows"

    return {
        "column": column,
        "status": status,
        "non_null_pct": pct(non_null, rows),
        "non_zero_pct": pct(non_zero, rows),
        "unique": unique,
        "note": note,
    }


def panel_overview(df: pd.DataFrame) -> dict:
    overview = {"rows": int(len(df))}
    if "trade_date" in df.columns:
        dates = df["trade_date"].astype(str)
        overview["date_min"] = str(dates.min()) if len(dates) else ""
        overview["date_max"] = str(dates.max()) if len(dates) else ""
        overview["dates"] = int(dates.nunique(dropna=True))
        per_date = df.groupby(dates).size()
        overview["stocks_per_date_min"] = int(per_date.min()) if len(per_date) else 0
        overview["stocks_per_date_median"] = float(per_date.median()) if len(per_date) else 0.0
        overview["stocks_per_date_max"] = int(per_date.max()) if len(per_date) else 0
    if "ts_code" in df.columns:
        overview["tickers"] = int(df["ts_code"].nunique(dropna=True))
    return overview


def feature_audit(df: pd.DataFrame) -> dict:
    try:
        featured = make_features(df)
        cols = feature_columns(featured)
        return {
            "status": "ok" if len(cols) == 35 else "incomplete",
            "feature_count": len(cols),
            "missing_feature_count": max(35 - len(cols), 0),
        }
    except Exception as exc:  # pragma: no cover - used for CLI diagnostics
        return {
            "status": "error",
            "feature_count": 0,
            "missing_feature_count": 35,
            "error": f"{type(exc).__name__}: {exc}",
        }


def audit_panel(spec: PanelSpec) -> dict:
    df = read_panel(spec.path)
    fields = [status_for_column(df, column) for column in REQUIRED_COLUMNS]
    missing = [f["column"] for f in fields if f["status"] == "missing"]
    inactive = [
        f["column"]
        for f in fields
        if f["column"] in CRITICAL_SIGNAL_COLUMNS
        and f["status"] in {"empty", "neutral", "inactive", "constant", "proxy"}
    ]
    return {
        "name": spec.name,
        "path": str(spec.path),
        "overview": panel_overview(df),
        "features": feature_audit(df),
        "fields": fields,
        "missing_columns": missing,
        "inactive_or_proxy_critical_columns": inactive,
    }


def print_markdown(results: list[dict]) -> None:
    print("# M2-Alpha Data-Source Field Audit")
    print()
    print("| Panel | Rows | Dates | Tickers | Date span | Feature cols | Critical gaps |")
    print("|---|---:|---:|---:|---|---:|---|")
    for result in results:
        overview = result["overview"]
        features = result["features"]
        span = f"{overview.get('date_min', '')} -> {overview.get('date_max', '')}"
        gaps = result["missing_columns"] + result["inactive_or_proxy_critical_columns"]
        gap_text = ", ".join(dict.fromkeys(gaps)) if gaps else "none"
        print(
            f"| {result['name']} | {overview.get('rows', 0):,} | "
            f"{overview.get('dates', 0):,} | {overview.get('tickers', 0):,} | "
            f"{span} | {features.get('feature_count', 0)} | {gap_text} |"
        )

    for result in results:
        print()
        print(f"## {result['name']}")
        overview = result["overview"]
        print(
            f"- Stocks per date: min {overview.get('stocks_per_date_min', 0)}, "
            f"median {overview.get('stocks_per_date_median', 0):.1f}, "
            f"max {overview.get('stocks_per_date_max', 0)}"
        )
        print(f"- Feature build: {result['features']}")
        print()
        print("| Column | Status | Non-null % | Non-zero % | Unique | Note |")
        print("|---|---|---:|---:|---:|---|")
        for field in result["fields"]:
            print(
                f"| `{field['column']}` | {field['status']} | "
                f"{field['non_null_pct']:.2f} | {field['non_zero_pct']:.2f} | "
                f"{field['unique']} | {field['note']} |"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit one or more A-share panel files against the M2-Alpha field contract."
    )
    parser.add_argument(
        "--panel",
        action="append",
        type=parse_panel_spec,
        required=True,
        help="Panel to audit, either PATH or NAME=PATH. Repeat to compare sources.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for machine-readable JSON audit output.",
    )
    args = parser.parse_args()

    results = [audit_panel(spec) for spec in args.panel]
    print_markdown(results)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
