"""Enrich the public BaoStock panel with open/free A-share fields.

The public/open-data cache keeps BaoStock as the stable historical base source.
This step adds a best-effort no-secret enrichment layer:

- derived historical `volume_ratio` from BaoStock volume;
- AKShare / efinance available snapshots for valuation, market-cap, and
  industry fields;
- Eastmoney historical money-flow fallback for the order-size flow features
  used in the report, with explicit approximation metadata.

Source failures are recorded in metadata instead of being hidden as model
regressions or breaking the whole public-data pipeline.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / "cache"
PANEL = CACHE / "panel.parquet"
BASIC = CACHE / "basic.csv"
METADATA = CACHE / "source_enrichment.json"
RAW_CACHE = Path(os.environ.get("M2ALPHA_RAW_CACHE", str(CACHE / "source_raw")))

SOURCE_TIMEOUT = int(float(os.environ.get("M2ALPHA_ENRICH_TIMEOUT", "60")))
MONEYFLOW_TIMEOUT = int(float(os.environ.get("M2ALPHA_MONEYFLOW_TIMEOUT", "8")))
MONEYFLOW_SLEEP = float(os.environ.get("M2ALPHA_MONEYFLOW_SLEEP", "0.05"))
MONEYFLOW_MAX_CONSECUTIVE_ERRORS = int(os.environ.get("M2ALPHA_MONEYFLOW_MAX_CONSECUTIVE_ERRORS", "8"))
_HAS_ALARM = hasattr(signal, "SIGALRM")


@contextmanager
def _deadline(seconds: int):
    if not _HAS_ALARM or seconds <= 0:
        yield
        return

    def _on_alarm(signum, frame):
        raise TimeoutError(f"source call exceeded {seconds}s")

    old = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _plain_code(ts_code: str) -> str:
    return str(ts_code).split(".")[0].zfill(6)


def _to_ts_code(code: object) -> str | None:
    s = "".join(ch for ch in str(code) if ch.isdigit())
    if len(s) < 6:
        return None
    s = s[-6:]
    if s.startswith(("6", "5", "9")):
        return f"{s}.SH"
    if s.startswith(("0", "2", "3")):
        return f"{s}.SZ"
    if s.startswith(("4", "8")):
        return f"{s}.BJ"
    return None


def _first_existing(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _num(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip().replace(",", "")
    if s in {"", "-", "--", "None", "nan", "NaN"}:
        return None
    percent = s.endswith("%")
    if percent:
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _numeric_series(df: pd.DataFrame, col: str | None) -> pd.Series:
    if col is None:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")
    return df[col].map(_num).astype("Float64")


def _safe_error(exc: Exception) -> str:
    text = repr(exc)
    text = re.sub(r"https?://[^\s'\"()]+", "<url>", text)
    text = re.sub(r"url: [^\s'\"()]+", "url: <url>", text)
    text = re.sub(r"host='127\.0\.0\.1', port=\d+", "host='<network-proxy>'", text)
    text = re.sub(r"host='<network-proxy>', port=\d+", "host='<network-proxy>'", text)
    text = re.sub(r"127\.0\.0\.1:\d+", "<network-proxy>", text)
    text = re.sub(r"localhost:\d+", "<network-proxy>", text)
    text = text.replace("127.0.0.1", "<network-proxy>")
    return text[:500]


def _public_path(path: Path | str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return p.name


def _source_meta(status: str, **kwargs) -> dict:
    out = {"status": status}
    out.update(kwargs)
    return out


def _read_json_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _moneyflow_cache_file(raw_cache_dir: Path, ts_code: str, start_date: str, end_date: str) -> Path:
    plain = _plain_code(ts_code)
    return raw_cache_dir / "eastmoney_moneyflow" / f"{plain}_{start_date}_{end_date}.json"


@contextmanager
def _quiet_vendor_output():
    if os.environ.get("M2ALPHA_ENRICH_VERBOSE") == "1":
        yield
        return
    with open(os.devnull, "w", encoding="utf-8") as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield


def _normalize_snapshot(df: pd.DataFrame, prefix: str, mapping: dict[str, list[str]]) -> pd.DataFrame:
    code_col = _first_existing(df, ["代码", "股票代码"])
    if code_col is None:
        return pd.DataFrame(columns=["ts_code"])
    out = pd.DataFrame({"ts_code": df[code_col].map(_to_ts_code)})
    for target, source_cols in mapping.items():
        out[f"{prefix}_{target}"] = _numeric_series(df, _first_existing(df, source_cols))
    name_col = _first_existing(df, ["名称", "股票名称"])
    if name_col:
        out[f"{prefix}_name"] = df[name_col].astype(str)
    out = out.dropna(subset=["ts_code"]).drop_duplicates("ts_code", keep="last")
    return out


def fetch_akshare_spot() -> tuple[pd.DataFrame, dict]:
    import akshare as ak

    with _deadline(SOURCE_TIMEOUT):
        df = ak.stock_zh_a_spot_em()
    out = _normalize_snapshot(df, "akshare", {
        "volume_ratio": ["量比"],
        "turnover_rate": ["换手率"],
        "pb": ["市净率"],
        "pe_dynamic": ["市盈率-动态", "动态市盈率"],
        "market_cap": ["总市值"],
        "float_market_cap": ["流通市值"],
    })
    return out, {"status": "ok", "rows": int(len(df)), "normalized_rows": int(len(out))}


def fetch_efinance_realtime() -> tuple[pd.DataFrame, dict]:
    import efinance as ef

    with _deadline(SOURCE_TIMEOUT):
        df = ef.stock.get_realtime_quotes()
    out = _normalize_snapshot(df, "efinance", {
        "volume_ratio": ["量比"],
        "turnover_rate": ["换手率"],
        "pe_dynamic": ["动态市盈率", "市盈率-动态"],
        "market_cap": ["总市值"],
        "float_market_cap": ["流通市值"],
    })
    return out, {"status": "ok", "rows": int(len(df)), "normalized_rows": int(len(out))}


def fetch_efinance_base_info(codes: list[str], batch_size: int = 80) -> tuple[pd.DataFrame, dict]:
    import efinance as ef

    frames = []
    batch_errors = []
    for i in range(0, len(codes), batch_size):
        chunk = [_plain_code(c) for c in codes[i:i + batch_size]]
        try:
            with _deadline(SOURCE_TIMEOUT):
                with _quiet_vendor_output():
                    df = ef.stock.get_base_info(chunk)
        except Exception as exc:
            batch_errors.append({
                "batch_start": i,
                "batch_size": len(chunk),
                "error": _safe_error(exc),
            })
            continue
        if isinstance(df, pd.Series):
            df = df.to_frame().T
        if df is not None and len(df):
            if "股票代码" not in df.columns and "代码" not in df.columns:
                if len(df) == len(chunk):
                    df = df.copy()
                    df.insert(0, "股票代码", chunk)
                elif len(df.index) == len(df):
                    df = df.copy()
                    df.insert(0, "股票代码", [str(x).zfill(6)[-6:] for x in df.index])
            frames.append(df)

    if not frames:
        status = "error" if batch_errors else "empty"
        return pd.DataFrame(columns=["ts_code"]), {
            "status": status,
            "rows": 0,
            "normalized_rows": 0,
            "batch_errors": batch_errors[:5],
            "n_batch_errors": len(batch_errors),
        }

    raw = pd.concat(frames, ignore_index=True)
    out = _normalize_snapshot(raw, "efinance_base", {
        "pb": ["市净率"],
        "pe_dynamic": ["市盈率(动)", "动态市盈率"],
        "market_cap": ["总市值"],
        "float_market_cap": ["流通市值"],
        "roe": ["ROE"],
        "net_margin": ["净利率"],
        "gross_margin": ["毛利率"],
    })
    industry_col = _first_existing(raw, ["所处行业", "行业"])
    code_col = _first_existing(raw, ["股票代码", "代码"])
    if industry_col and code_col:
        industry = pd.DataFrame({
            "ts_code": raw[code_col].map(_to_ts_code),
            "efinance_base_industry": raw[industry_col].astype(str),
        }).dropna(subset=["ts_code"]).drop_duplicates("ts_code", keep="last")
        out = out.merge(industry, on="ts_code", how="left")
    return out, {
        "status": "partial" if batch_errors else "ok",
        "rows": int(len(raw)),
        "normalized_rows": int(len(out)),
        "batch_errors": batch_errors[:5],
        "n_batch_errors": len(batch_errors),
    }


def _combine_sources(frames: list[pd.DataFrame]) -> pd.DataFrame:
    merged = None
    for frame in frames:
        if frame is None or frame.empty:
            continue
        merged = frame if merged is None else merged.merge(frame, on="ts_code", how="outer")
    return merged if merged is not None else pd.DataFrame(columns=["ts_code"])


def _coalesce(frame: pd.DataFrame, cols: list[str]) -> pd.Series:
    values = pd.Series([pd.NA] * len(frame), index=frame.index, dtype="Float64")
    for col in cols:
        if col in frame.columns:
            values = values.fillna(frame[col])
    return values


def fill_derived_volume_ratio(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Fill historical `volume_ratio` from same-day volume vs prior-5-day mean.

    The report feature uses a daily-basic volume-ratio field. BaoStock does not
    expose that field, while AKShare/efinance generally expose it only in
    realtime snapshots. For historical benchmark payloads, the closest
    no-secret proxy is today's volume divided by the previous five trading
    days' average volume, computed within each stock's own time series. This
    keeps the feature non-empty without using future rows.
    """
    panel = panel.copy()
    panel["trade_date"] = panel["trade_date"].astype(str)
    if "volume_ratio" not in panel.columns:
        panel["volume_ratio"] = pd.NA

    before = int(pd.to_numeric(panel["volume_ratio"], errors="coerce").notna().sum())
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    vol = pd.to_numeric(panel["vol"], errors="coerce")
    prev5 = vol.groupby(panel["ts_code"], sort=False).transform(
        lambda x: x.shift(1).rolling(5, min_periods=3).mean()
    )
    derived = (vol / prev5.replace(0, pd.NA)).clip(lower=0, upper=20)
    current = pd.to_numeric(panel["volume_ratio"], errors="coerce")
    needs_fill = current.isna() | (current.fillna(0).abs() < 1e-12)
    panel.loc[needs_fill, "volume_ratio"] = derived.loc[needs_fill]
    after = int(pd.to_numeric(panel["volume_ratio"], errors="coerce").notna().sum())
    active_after = int((pd.to_numeric(panel["volume_ratio"], errors="coerce").fillna(0).abs() > 1e-12).sum())
    return panel, {
        "status": "ok",
        "method": "vol / rolling_mean(previous_5_trading_days_vol), per stock",
        "rows_before": before,
        "rows_after": after,
        "active_after": active_after,
        "newly_filled": after - before,
        "note": "Open/free proxy for report daily_basic volume_ratio; not a vendor-identical field.",
    }


def _moneyflow_secid(ts_code: str) -> str:
    code = _plain_code(ts_code)
    market = "1" if code.startswith("6") else "0"
    return f"{market}.{code}"


def _eastmoney_moneyflow_request(ts_code: str, *, lmt: int) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Referer": "https://data.eastmoney.com/zjlx/detail.html",
        "Accept": "application/json,text/plain,*/*",
    }
    params = {
        "lmt": str(lmt),
        "klt": "101",
        "secid": _moneyflow_secid(ts_code),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "_": str(int(time.time() * 1000)),
    }
    attempts = [
        ("http", False),
        ("https", False),
        ("http", True),
        ("https", True),
    ]
    last_error: Exception | None = None
    for scheme, trust_env in attempts:
        session = requests.Session()
        session.trust_env = trust_env
        try:
            url = f"{scheme}://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
            response = session.get(url, params=params, headers=headers, timeout=MONEYFLOW_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if payload.get("rc") == 0:
                return payload
            last_error = RuntimeError(f"eastmoney rc={payload.get('rc')} rt={payload.get('rt')}")
        except Exception as exc:
            last_error = exc
    if last_error is None:
        raise RuntimeError("eastmoney moneyflow request failed without exception")
    raise last_error


def _moneyflow_row_from_net_values(
    ts_code: str,
    trade_date: str,
    *,
    main_net: float | None,
    small_net: float | None,
    medium_net: float | None,
    large_net: float | None,
    extra_large_net: float | None,
) -> dict | None:
    if main_net is None:
        return None

    def wy(value: float | None) -> float:
        return 0.0 if value is None else float(value) / 10000.0

    def pos(value: float | None) -> float:
        return max(wy(value), 0.0)

    def neg(value: float | None) -> float:
        return max(-wy(value), 0.0)

    return {
        "ts_code": ts_code,
        "trade_date": str(trade_date).replace("-", ""),
        "net_mf_amount": wy(main_net),
        "buy_sm_amount": pos(small_net),
        "sell_sm_amount": neg(small_net),
        "buy_md_amount": pos(medium_net),
        "sell_md_amount": neg(medium_net),
        "buy_lg_amount": pos(large_net),
        "sell_lg_amount": neg(large_net),
        "buy_elg_amount": pos(extra_large_net),
        "sell_elg_amount": neg(extra_large_net),
    }


def _rows_from_eastmoney_payload(
    ts_code: str,
    payload: dict,
    start_date: str,
    end_date: str,
) -> list[dict]:
    rows = []
    data = payload.get("data") or {}
    klines = data.get("klines") or []
    for item in klines:
        parts = item.split(",")
        if len(parts) < 13:
            continue
        date = parts[0].replace("-", "")
        if date < start_date or date > end_date:
            continue
        row = _moneyflow_row_from_net_values(
            ts_code,
            date,
            main_net=_num(parts[1]),
            small_net=_num(parts[2]),
            medium_net=_num(parts[3]),
            large_net=_num(parts[4]),
            extra_large_net=_num(parts[5]),
        )
        if row is not None:
            rows.append(row)
    return rows


def fetch_eastmoney_moneyflow_history(codes: list[str], start_date: str, end_date: str,
                                      max_codes: int | None = None,
                                      raw_cache_dir: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Fetch Eastmoney historical money-flow net fields and map them to M2 columns.

    Eastmoney exposes net inflow by order-size bucket. The report panel was
    built from buy/sell amount fields, so this adapter records an approximation:
    positive net flow is mapped to the corresponding buy amount and negative net
    flow to sell amount. This preserves direction and relative scale for the two
    deployed money-flow features without pretending to be Tushare parity.
    """
    rows = []
    errors = []
    selected = codes[:max_codes] if max_codes else codes
    consecutive_errors = 0
    stopped_early = False
    cached_payloads = 0
    downloaded_payloads = 0
    lmt = max(260, len(pd.unique(pd.Series(pd.date_range(
        f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}",
        f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}",
        freq="B",
    )))) + 20)

    for i, ts_code in enumerate(selected, 1):
        payload = None
        cache_file = (
            _moneyflow_cache_file(raw_cache_dir, ts_code, start_date, end_date)
            if raw_cache_dir is not None
            else None
        )
        if cache_file is not None:
            payload = _read_json_cache(cache_file)
            if payload is not None:
                cached_payloads += 1
        try:
            if payload is None:
                with _deadline(max(MONEYFLOW_TIMEOUT * 4, SOURCE_TIMEOUT)):
                    payload = _eastmoney_moneyflow_request(ts_code, lmt=lmt)
                downloaded_payloads += 1
                if cache_file is not None:
                    _write_json_cache(cache_file, payload)
        except Exception as exc:
            errors.append({"ts_code": ts_code, "error": _safe_error(exc)})
            consecutive_errors += 1
            if consecutive_errors >= MONEYFLOW_MAX_CONSECUTIVE_ERRORS and not rows:
                stopped_early = True
                break
            continue
        consecutive_errors = 0

        rows.extend(_rows_from_eastmoney_payload(ts_code, payload, start_date, end_date))
        if MONEYFLOW_SLEEP > 0 and i < len(selected):
            time.sleep(MONEYFLOW_SLEEP)

    out = pd.DataFrame(rows)
    if out.empty:
        return out, _source_meta(
            "error" if errors else "empty",
            attempted_codes=len(selected),
            matched_codes=0,
            rows=0,
            errors=errors[:10],
            n_errors=len(errors),
            stopped_early=stopped_early,
            max_consecutive_errors=MONEYFLOW_MAX_CONSECUTIVE_ERRORS,
            cached_payloads=cached_payloads,
            downloaded_payloads=downloaded_payloads,
            raw_cache_dir=_public_path(raw_cache_dir),
        )

    matched_codes = int(out["ts_code"].nunique())
    return out.drop_duplicates(["ts_code", "trade_date"], keep="last"), _source_meta(
        "partial" if errors else "ok",
        attempted_codes=len(selected),
        matched_codes=matched_codes,
        rows=int(len(out)),
        errors=errors[:10],
        n_errors=len(errors),
        stopped_early=stopped_early,
        max_consecutive_errors=MONEYFLOW_MAX_CONSECUTIVE_ERRORS,
        cached_payloads=cached_payloads,
        downloaded_payloads=downloaded_payloads,
        raw_cache_dir=_public_path(raw_cache_dir),
        field_mapping=(
            "Eastmoney net-flow buckets are converted to Tushare-like amount columns: "
            "positive net flow -> buy_*_amount, negative net flow -> sell_*_amount, "
            "main net flow -> net_mf_amount. Units converted from yuan to ten-thousand CNY."
        ),
    )


def fetch_efinance_moneyflow_history(codes: list[str], start_date: str, end_date: str,
                                     max_codes: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Fetch historical order-size net flow through efinance as a fallback.

    efinance wraps the same Eastmoney money-flow surface but exposes a stable
    DataFrame schema. It is tried after the direct request path, so a transient
    failure in one wrapper does not erase an otherwise usable source.
    """
    import efinance as ef

    rows = []
    errors = []
    selected = codes[:max_codes] if max_codes else codes
    consecutive_errors = 0
    stopped_early = False

    for i, ts_code in enumerate(selected, 1):
        try:
            with _deadline(max(MONEYFLOW_TIMEOUT * 4, SOURCE_TIMEOUT)):
                with _quiet_vendor_output():
                    df = ef.stock.get_history_bill(_plain_code(ts_code))
        except Exception as exc:
            errors.append({"ts_code": ts_code, "error": _safe_error(exc)})
            consecutive_errors += 1
            if consecutive_errors >= MONEYFLOW_MAX_CONSECUTIVE_ERRORS and not rows:
                stopped_early = True
                break
            continue
        consecutive_errors = 0
        if df is None or df.empty:
            continue

        date_col = _first_existing(df, ["日期", "date", "trade_date"])
        main_col = _first_existing(df, ["主力净流入", "主力净流入-净额"])
        small_col = _first_existing(df, ["小单净流入", "小单净流入-净额"])
        medium_col = _first_existing(df, ["中单净流入", "中单净流入-净额"])
        large_col = _first_existing(df, ["大单净流入", "大单净流入-净额"])
        extra_col = _first_existing(df, ["超大单净流入", "超大单净流入-净额"])
        if not date_col or not main_col:
            errors.append({
                "ts_code": ts_code,
                "error": f"missing expected efinance columns: {list(df.columns)[:20]}",
            })
            continue

        for _, row in df.iterrows():
            date = str(row[date_col]).split()[0].replace("-", "")
            if date < start_date or date > end_date:
                continue
            mapped = _moneyflow_row_from_net_values(
                ts_code,
                date,
                main_net=_num(row.get(main_col)),
                small_net=_num(row.get(small_col)) if small_col else None,
                medium_net=_num(row.get(medium_col)) if medium_col else None,
                large_net=_num(row.get(large_col)) if large_col else None,
                extra_large_net=_num(row.get(extra_col)) if extra_col else None,
            )
            if mapped is not None:
                rows.append(mapped)
        if MONEYFLOW_SLEEP > 0 and i < len(selected):
            time.sleep(MONEYFLOW_SLEEP)

    out = pd.DataFrame(rows)
    if out.empty:
        return out, _source_meta(
            "error" if errors else "empty",
            attempted_codes=len(selected),
            matched_codes=0,
            rows=0,
            errors=errors[:10],
            n_errors=len(errors),
            stopped_early=stopped_early,
            max_consecutive_errors=MONEYFLOW_MAX_CONSECUTIVE_ERRORS,
        )

    matched_codes = int(out["ts_code"].nunique())
    return out.drop_duplicates(["ts_code", "trade_date"], keep="last"), _source_meta(
        "partial" if errors else "ok",
        attempted_codes=len(selected),
        matched_codes=matched_codes,
        rows=int(len(out)),
        errors=errors[:10],
        n_errors=len(errors),
        stopped_early=stopped_early,
        max_consecutive_errors=MONEYFLOW_MAX_CONSECUTIVE_ERRORS,
        field_mapping=(
            "efinance get_history_bill net-flow buckets are converted to M2 amount columns: "
            "positive net flow -> buy_*_amount, negative net flow -> sell_*_amount, "
            "main net flow -> net_mf_amount. Units converted from yuan to ten-thousand CNY."
        ),
    )


def apply_moneyflow_history(panel: pd.DataFrame, moneyflow: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    panel = panel.copy()
    if moneyflow.empty:
        return panel, {
            "status": "empty",
            "rows_available": 0,
            "rows_applied": 0,
            "active_after": {},
        }

    columns = [
        "net_mf_amount",
        "buy_sm_amount",
        "buy_md_amount",
        "buy_lg_amount",
        "buy_elg_amount",
        "sell_sm_amount",
        "sell_md_amount",
        "sell_lg_amount",
        "sell_elg_amount",
    ]
    for col in columns:
        if col not in panel.columns:
            panel[col] = 0.0

    key = ["ts_code", "trade_date"]
    panel["trade_date"] = panel["trade_date"].astype(str)
    moneyflow = moneyflow.copy()
    moneyflow["trade_date"] = moneyflow["trade_date"].astype(str)
    moneyflow = moneyflow[key + [c for c in columns if c in moneyflow.columns]]
    merged = panel[key].merge(moneyflow, on=key, how="left", suffixes=("", "_src"))

    applied = {"status": "ok", "rows_available": int(len(moneyflow))}
    any_applied = pd.Series(False, index=panel.index)
    for col in columns:
        if col not in merged.columns:
            continue
        source = pd.to_numeric(merged[col], errors="coerce")
        current = pd.to_numeric(panel[col], errors="coerce")
        needs_fill = current.isna() | (current.fillna(0).abs() < 1e-12)
        use = needs_fill & source.notna()
        panel.loc[use, col] = source.loc[use].to_numpy()
        any_applied = any_applied | use
        active = int((pd.to_numeric(panel[col], errors="coerce").fillna(0).abs() > 1e-12).sum())
        applied[col] = {
            "source_available": int(source.notna().sum()),
            "newly_filled": int(use.sum()),
            "active_after": active,
        }

    applied["rows_applied"] = int(any_applied.sum())
    applied["matched_panel_rows"] = int(merged.drop(columns=key).notna().any(axis=1).sum())
    return panel, applied


def apply_enrichment(panel: pd.DataFrame, basic: pd.DataFrame, target_date: str,
                     sources: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    panel = panel.copy()
    basic = basic.copy()
    panel["trade_date"] = panel["trade_date"].astype(str)

    mask = panel["trade_date"] == target_date
    latest = panel.loc[mask, ["ts_code"]].merge(sources, on="ts_code", how="left")
    latest_index = panel.index[mask]

    applied = {
        "target_date": target_date,
        "target_rows": int(mask.sum()),
        "matched_rows": int(latest.drop(columns=["ts_code"], errors="ignore").notna().any(axis=1).sum()),
    }

    fill_specs = {
        "volume_ratio": ["akshare_volume_ratio", "efinance_volume_ratio"],
        "pb": ["efinance_base_pb", "akshare_pb"],
        "market_cap": ["efinance_base_market_cap", "efinance_market_cap", "akshare_market_cap"],
        "float_market_cap": ["efinance_base_float_market_cap", "efinance_float_market_cap", "akshare_float_market_cap"],
        "pe_dynamic": ["efinance_base_pe_dynamic", "efinance_pe_dynamic", "akshare_pe_dynamic"],
    }

    for target, source_cols in fill_specs.items():
        if target not in panel.columns:
            panel[target] = pd.NA
        values = _coalesce(latest, source_cols)
        before = panel.loc[mask, target].notna().sum()
        current = panel.loc[mask, target].reset_index(drop=True)
        needs_fill = current.isna() | (pd.to_numeric(current, errors="coerce").fillna(0) == 0)
        merged = current.mask(needs_fill, values)
        panel.loc[latest_index, target] = merged.to_numpy()
        after = panel.loc[mask, target].notna().sum()
        applied[target] = {
            "source_available": int(values.notna().sum()),
            "active_after": int(after),
            "newly_filled": int(after - before),
        }

    if "efinance_base_industry" in sources.columns and "industry" in basic.columns:
        industry = sources[["ts_code", "efinance_base_industry"]].dropna()
        basic = basic.merge(industry, on="ts_code", how="left")
        missing = basic["industry"].isna() | (basic["industry"].astype(str).str.strip().isin(["", "—", "nan"]))
        before_missing = int(missing.sum())
        basic.loc[missing, "industry"] = basic.loc[missing, "efinance_base_industry"]
        basic = basic.drop(columns=["efinance_base_industry"])
        after_missing = int((basic["industry"].isna() | (basic["industry"].astype(str).str.strip().isin(["", "—", "nan"]))).sum())
        applied["industry_filled"] = before_missing - after_missing

    return panel, basic, applied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", default=str(PANEL))
    parser.add_argument("--basic", default=str(BASIC))
    parser.add_argument("--out-panel", default=str(PANEL))
    parser.add_argument("--out-basic", default=str(BASIC))
    parser.add_argument("--metadata", default=str(METADATA))
    parser.add_argument("--date", default=None, help="Target trade_date YYYYMMDD; default uses panel max date.")
    parser.add_argument("--strict", action="store_true", help="Fail if either source cannot be queried.")
    parser.add_argument(
        "--skip-moneyflow",
        action="store_true",
        help="Skip Eastmoney historical money-flow fallback; volume-ratio and snapshots still run.",
    )
    parser.add_argument(
        "--moneyflow-max-codes",
        type=int,
        default=int(os.environ.get("M2ALPHA_MONEYFLOW_MAX_CODES", "0")) or None,
        help="Limit money-flow history to the first N target codes for debugging.",
    )
    parser.add_argument(
        "--raw-cache-dir",
        default=str(RAW_CACHE),
        help="Directory for reusable raw provider responses, especially intermittent money-flow JSON.",
    )
    parser.add_argument(
        "--no-raw-cache",
        action="store_true",
        help="Disable raw response cache/replay for source probes.",
    )
    args = parser.parse_args()

    panel_path = Path(args.panel)
    basic_path = Path(args.basic)
    panel = pd.read_parquet(panel_path)
    basic = pd.read_csv(basic_path, dtype=str)
    panel["trade_date"] = panel["trade_date"].astype(str)
    target_date = args.date or str(panel["trade_date"].max())
    codes = sorted(panel.loc[panel["trade_date"] == target_date, "ts_code"].astype(str).unique())

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date,
        "base_source": "BaoStock",
        "enrichment_sources": ["AKShare", "efinance"],
        "source_timeout_seconds": SOURCE_TIMEOUT,
        "raw_cache_dir": "" if args.no_raw_cache else _public_path(args.raw_cache_dir),
        "sources": {},
    }

    panel, derived_volume_meta = fill_derived_volume_ratio(panel)
    metadata["sources"]["derived.volume_ratio_from_baostock_volume"] = derived_volume_meta
    print(f"[enrich] derived.volume_ratio_from_baostock_volume: {derived_volume_meta}")

    frames = []
    for name, fn in [
        ("akshare.stock_zh_a_spot_em", fetch_akshare_spot),
        ("efinance.stock.get_realtime_quotes", fetch_efinance_realtime),
        ("efinance.stock.get_base_info", lambda: fetch_efinance_base_info(codes)),
    ]:
        try:
            frame, info = fn()
            frames.append(frame)
            info["matched_target_rows"] = int(frame["ts_code"].isin(codes).sum()) if "ts_code" in frame else 0
            metadata["sources"][name] = info
            print(f"[enrich] {name}: {info}")
        except Exception as exc:
            safe_error = _safe_error(exc)
            metadata["sources"][name] = {"status": "error", "error": safe_error}
            print(f"[enrich] {name} failed: {safe_error}", file=sys.stderr)
            if args.strict:
                Path(args.metadata).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                raise

    sources = _combine_sources(frames)
    panel, basic, applied = apply_enrichment(panel, basic, target_date, sources)
    metadata["applied"] = applied

    if args.skip_moneyflow:
        metadata["sources"]["eastmoney.moneyflow_history"] = _source_meta("skipped")
        metadata["applied_moneyflow"] = {"status": "skipped"}
    else:
        start_date = str(panel["trade_date"].min())
        end_date = str(panel["trade_date"].max())
        raw_cache_dir = None if args.no_raw_cache else Path(args.raw_cache_dir)
        try:
            eastmoney_moneyflow, eastmoney_meta = fetch_eastmoney_moneyflow_history(
                codes,
                start_date,
                end_date,
                max_codes=args.moneyflow_max_codes,
                raw_cache_dir=raw_cache_dir,
            )
            metadata["sources"]["eastmoney.moneyflow_history"] = eastmoney_meta
            moneyflow_frames = [eastmoney_moneyflow] if not eastmoney_moneyflow.empty else []
            print(f"[enrich] eastmoney.moneyflow_history: {eastmoney_meta}")
        except Exception as exc:
            safe_error = _safe_error(exc)
            metadata["sources"]["eastmoney.moneyflow_history"] = _source_meta("error", error=safe_error)
            moneyflow_frames = []
            print(f"[enrich] eastmoney.moneyflow_history failed: {safe_error}", file=sys.stderr)
            if args.strict:
                Path(args.metadata).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                raise

        try:
            efinance_moneyflow, efinance_mf_meta = fetch_efinance_moneyflow_history(
                codes, start_date, end_date, max_codes=args.moneyflow_max_codes
            )
            metadata["sources"]["efinance.stock.get_history_bill"] = efinance_mf_meta
            if not efinance_moneyflow.empty:
                moneyflow_frames.append(efinance_moneyflow)
            print(f"[enrich] efinance.stock.get_history_bill: {efinance_mf_meta}")
        except Exception as exc:
            safe_error = _safe_error(exc)
            metadata["sources"]["efinance.stock.get_history_bill"] = _source_meta("error", error=safe_error)
            print(f"[enrich] efinance.stock.get_history_bill failed: {safe_error}", file=sys.stderr)
            if args.strict:
                Path(args.metadata).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                raise

        if moneyflow_frames:
            moneyflow = pd.concat(moneyflow_frames, ignore_index=True)
            moneyflow = moneyflow.drop_duplicates(["ts_code", "trade_date"], keep="first")
        else:
            moneyflow = pd.DataFrame()
        try:
            panel, moneyflow_applied = apply_moneyflow_history(panel, moneyflow)
            metadata["applied_moneyflow"] = moneyflow_applied
            print(f"[enrich] applied_moneyflow: {moneyflow_applied}")
        except Exception as exc:
            safe_error = _safe_error(exc)
            metadata["applied_moneyflow"] = {"status": "error", "error": safe_error}
            print(f"[enrich] applying moneyflow failed: {safe_error}", file=sys.stderr)
            if args.strict:
                Path(args.metadata).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                raise

    Path(args.out_panel).parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.out_panel, index=False)
    basic.to_csv(args.out_basic, index=False)
    Path(args.metadata).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[enrich] saved panel -> {args.out_panel}")
    print(f"[enrich] saved basic -> {args.out_basic}")
    print(f"[enrich] saved metadata -> {args.metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
