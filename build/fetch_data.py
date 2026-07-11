"""fetch_data.py — build the public/open-data A-share panel.

BaoStock 优势：
  · 免费可用，无 token，适合公开数据基线
  · 走自家 TCP 协议（data.baostock.com:31322），不依赖东财 / 雪球 / 深交所
  · 直接返回 peTTM / pbMRQ / psTTM / turn 等关键基本面（一次 query 拿齐）

输出:
  build/cache/panel.parquet — public universe panel: ts_code, trade_date, OHLCV, pre_close,
    pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f, pe_ttm, pb,
    ps_ttm, volume_ratio, net_mf_amount, buy/sell_(sm|md|lg|elg)_amount
  build/cache/csi300.parquet — 沪深 300 指数日线
  build/cache/basic.csv — public universe code + name + industry mapping
  build/cache/top1000_universe.csv — monthly dynamic top1000 membership snapshots

默认 universe=top1000：每月按 AKShare 全市场快照的流通市值选前 1000，
若选样失败则沿用最近可用月份。日频 K 线仍由 BaoStock 拉取。
首次回填默认从 2025-04-01 拉取，给 20/30/60 日滚动特征提供足够垫底；
后续按需增量重建时可使用 --incremental，只追加新交易日。
"""

from __future__ import annotations
import argparse, os, re, signal, socket, sys, time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
INDUSTRY_MAP_CSV = HERE / "industry_map.csv"     # tushare 申万行业映射 (committed in repo)
TOP1000_UNIVERSE_CSV = CACHE / "top1000_universe.csv"
DEFAULT_HISTORY_START = "2025-04-01"

# --- BaoStock hang 防护 -------------------------------------------------------
# BaoStock 走自家阻塞 TCP socket，本身没有任何超时。两种挂死实测都出现过：
#   1) 服务端连上但 recv 一直滴字节不结束 → socket.setdefaulttimeout（单次 recv
#      超时）形同虚设，永远不触发；
#   2) 对"窗口内无交易日"（周末/数据未就绪）的 k 线 query 直接永久阻塞。
# 这是增量重建偶发 failure 的根因（6/9–6/12 多次撞上，6/12 双窗口全挂）。
#
# 根治：用 SIGALRM 给每个 baostock 调用套一个进程级"硬墙钟超时"——它能中断 C 层
# 阻塞的 recv 并在 Python 抛 TimeoutError，无论服务端怎么 dribble 都逃不掉。
# socket 默认超时保留为第二层网兜。
SOCKET_TIMEOUT = float(os.environ.get("BAOSTOCK_SOCKET_TIMEOUT", "30"))
socket.setdefaulttimeout(SOCKET_TIMEOUT)
HARD_TIMEOUT = int(float(os.environ.get("BAOSTOCK_HARD_TIMEOUT", "25")))
_HAS_ALARM = hasattr(signal, "SIGALRM")


@contextmanager
def _hard_deadline(seconds: int):
    """SIGALRM 硬超时：seconds 内未完成则抛 TimeoutError，中断阻塞的 socket recv。

    仅 Unix 主线程可用；不支持时（理论上 CI/本地都支持）退化为无超时。
    """
    if not _HAS_ALARM or seconds <= 0:
        yield
        return

    def _on_alarm(signum, frame):
        raise TimeoutError(f"baostock call exceeded {seconds}s hard deadline")

    old = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _bs_login(bs, retries: int = 3):
    """带硬超时 + 重试的 baostock 登录。"""
    last_msg = ""
    for attempt in range(1, retries + 1):
        try:
            with _hard_deadline(HARD_TIMEOUT):
                lg = bs.login()
            if lg.error_code == "0":
                print(f"  baostock login ok (code={lg.error_code})", flush=True)
                return lg
            last_msg = lg.error_msg
        except (TimeoutError, socket.timeout, OSError) as e:
            last_msg = repr(e)
        print(f"  baostock login failed (attempt {attempt}/{retries}): {last_msg}", flush=True)
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError(f"baostock login failed after {retries} attempts: {last_msg}")


def _relogin(bs):
    """超时后重建 socket 连接：先 logout（忽略异常）再 login。"""
    try:
        with _hard_deadline(HARD_TIMEOUT):
            bs.logout()
    except Exception:
        pass
    time.sleep(2)
    try:
        with _hard_deadline(HARD_TIMEOUT):
            bs.login()
    except Exception:
        pass


def _has_trading_day(bs, start_date: str, end_date: str) -> bool:
    """前置检查：窗口内是否有交易日。周末/假期/数据未就绪时返回 False，
    避免对"无交易日区间"的 k 线 query 触发 BaoStock 永久阻塞。"""
    try:
        with _hard_deadline(HARD_TIMEOUT):
            rs = bs.query_trade_dates(start_date=start_date, end_date=end_date)
            if rs.error_code != "0":
                # 查不了就乐观放行，让后续带超时的 query 自己兜底
                return True
            df = _bs_query_to_df(rs)
    except (TimeoutError, socket.timeout, OSError) as e:
        print(f"  ⚠ query_trade_dates 超时/失败 ({e})，乐观放行", flush=True)
        return True
    if df.empty or "is_trading_day" not in df.columns:
        return True
    return (df["is_trading_day"].astype(str) == "1").any()


def _bs_code_to_ts(bs_code: str) -> str:
    """Convert 'sh.600519' → '600519.SH'."""
    if "." not in bs_code:
        return bs_code
    mkt, code = bs_code.split(".")
    return f"{code}.{mkt.upper()}"


def _ts_to_bs_code(ts_code: str) -> str:
    """Convert '600519.SH' → 'sh.600519'."""
    if "." not in ts_code:
        return ts_code
    code, mkt = ts_code.split(".")
    return f"{mkt.lower()}.{code}"


def _plain_to_ts_code(code: object) -> str | None:
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


def _date_to_compact(d: str) -> str:
    """'2026-05-29' → '20260529'."""
    return d.replace("-", "")


def _bs_query_to_df(rs) -> pd.DataFrame:
    rows = []
    while (rs.error_code == "0") & rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


def shorten_industry(s: str) -> str:
    """Normalize 证监会行业分类长名 → 短名 (用于 UI 显示)。

    Examples:
      'C39计算机、通信和其他电子设备制造业' → '计算机'
      'C38电气机械和器材制造业'             → '电气机械'
      'J66货币金融服务'                    → '货币金融'
      'C32有色金属冶炼和压延加工业'         → '有色金属冶炼'
      ''                                  → '—'
    """
    if not s or not isinstance(s, str):
        return "—"
    # Strip leading "C39" / "J66" 等代码前缀
    s = re.sub(r'^[A-Z]\d+', '', s).strip()
    # 按"、和及与"切第一个名词块
    for sep in ['、', '和', '及', '与']:
        if sep in s:
            s = s.split(sep)[0]
            break
    # 去常见后缀
    for suffix in ['制造业', '服务业', '加工业', '业', '服务']:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    return s.strip() or "—"


def load_industry_maps(bs) -> tuple[dict[str, str], dict[str, str]]:
    """Load primary repo mapping plus BaoStock coarse fallback."""
    primary_map = {}
    if INDUSTRY_MAP_CSV.exists():
        df_map = pd.read_csv(INDUSTRY_MAP_CSV, dtype=str).dropna(subset=["industry"])
        primary_map = dict(zip(df_map["ts_code"], df_map["industry"]))
        print(f"  loaded primary industry mapping ({len(primary_map)} tickers)")

    with _hard_deadline(HARD_TIMEOUT):
        rs = bs.query_stock_industry()
        ind = _bs_query_to_df(rs)
    ind["ts_code"] = ind["code"].apply(_bs_code_to_ts)
    fallback_map = dict(zip(ind["ts_code"], ind["industry"].apply(shorten_industry)))
    return primary_map, fallback_map


def apply_industry(comps: pd.DataFrame, bs) -> pd.DataFrame:
    primary_map, fallback_map = load_industry_maps(bs)
    comps = comps.copy()
    comps["industry"] = comps["ts_code"].apply(
        lambda ts: primary_map.get(ts) or fallback_map.get(ts) or "—"
    )
    missing = (comps["industry"] == "—").sum()
    if missing:
        print(f"  ⚠️ {missing} 只股票 industry 缺失（mapping 都没匹配上）")
    return comps


def get_csi300_components(bs) -> pd.DataFrame:
    """获取沪深 300 成分股清单 + 行业。"""
    print("[1/4] 拉取沪深 300 成分股 ...")
    with _hard_deadline(HARD_TIMEOUT):
        rs = bs.query_hs300_stocks()
        comps = _bs_query_to_df(rs)
    comps["ts_code"] = comps["code"].apply(_bs_code_to_ts)
    comps["name"] = comps["code_name"]
    print(f"  → {len(comps)} 只成分股")

    comps = apply_industry(comps[["ts_code", "name"]], bs)
    return comps[["ts_code", "name", "industry"]]


def _month_key(iso_date: str) -> str:
    return iso_date[:7].replace("-", "")


def _window_months(start_date: str, end_date: str) -> list[str]:
    start = pd.Period(start_date[:7], freq="M")
    end = pd.Period(end_date[:7], freq="M")
    return [str(p).replace("-", "") for p in pd.period_range(start, end, freq="M")]


def _normalize_top1000_snapshot(raw: pd.DataFrame, *, n: int, month: str, source: str) -> pd.DataFrame:
    code_col = "代码" if "代码" in raw.columns else "股票代码"
    name_col = "名称" if "名称" in raw.columns else "股票名称"
    mv_col = "流通市值" if "流通市值" in raw.columns else None
    if code_col not in raw.columns or name_col not in raw.columns or mv_col is None:
        raise ValueError(f"AKShare snapshot lacks required columns; got {list(raw.columns)}")
    out = pd.DataFrame({
        "month": month,
        "ts_code": raw[code_col].map(_plain_to_ts_code),
        "name": raw[name_col].astype(str),
        "float_market_cap": pd.to_numeric(raw[mv_col], errors="coerce"),
        "source": source,
    })
    out = out.dropna(subset=["ts_code", "float_market_cap"])
    out = out[~out["ts_code"].str.endswith(".BJ")]
    out = out[~out["name"].str.upper().str.contains("ST", na=False)]
    out = out.sort_values(["float_market_cap", "ts_code"], ascending=[False, True])
    out = out.drop_duplicates("ts_code", keep="first").head(n).reset_index(drop=True)
    if len(out) < min(n, 30):
        raise ValueError(f"AKShare top{n} snapshot too small: {len(out)} rows")
    return out


def _read_top1000_cache() -> pd.DataFrame:
    if not TOP1000_UNIVERSE_CSV.exists():
        return pd.DataFrame(columns=["month", "ts_code", "name", "float_market_cap", "source"])
    df = pd.read_csv(TOP1000_UNIVERSE_CSV, dtype={"month": str, "ts_code": str})
    return df


def _write_top1000_cache(snapshot: pd.DataFrame) -> None:
    old = _read_top1000_cache()
    merged = pd.concat([old, snapshot], ignore_index=True)
    merged["month"] = merged["month"].astype(str)
    merged = merged.drop_duplicates(["month", "ts_code"], keep="last")
    merged = merged.sort_values(["month", "float_market_cap", "ts_code"], ascending=[True, False, True])
    merged.to_csv(TOP1000_UNIVERSE_CSV, index=False)
    print(f"  saved → {TOP1000_UNIVERSE_CSV} ({merged.month.nunique()} months)")


def _fetch_akshare_top1000(month: str, n: int) -> pd.DataFrame:
    print(f"[1/4] AKShare 全市场快照选样 top{n} month={month} ...")
    import akshare as ak

    with _hard_deadline(HARD_TIMEOUT):
        raw = ak.stock_zh_a_spot_em()
    snapshot = _normalize_top1000_snapshot(
        raw, n=n, month=month, source="akshare.stock_zh_a_spot_em"
    )
    print(f"  → selected {len(snapshot)} stocks from {len(raw)} snapshot rows")
    return snapshot


def _snapshot_for_month(cache: pd.DataFrame, month: str) -> pd.DataFrame | None:
    if cache.empty:
        return None
    months = sorted(cache["month"].astype(str).unique())
    prev = [m for m in months if m <= month]
    if prev:
        use_month = prev[-1]
    else:
        # Initial historical backfill has no true past snapshots yet. Use the
        # earliest available snapshot as an explicit seed; future monthly runs
        # will replace this with real month-by-month snapshots.
        use_month = months[0]
    snap = cache[cache["month"].astype(str) == use_month].copy()
    snap["source_month"] = use_month
    if use_month != month:
        snap["source"] = snap["source"].astype(str) + f"|fallback_from_{use_month}"
    return snap


def _seed_top1000_membership_from_existing_cache(
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Build a historical warmup universe from the existing committed cache.

    This is a practical fallback for public/open-data backfills. If AKShare's
    full-market snapshot is temporarily unavailable and no historical top1000
    cache exists yet, the current `panel.parquet` still tells us which stocks
    were in the active universe for each already-tracked month. For months
    before the committed panel starts, we include all known active names only
    to provide per-stock rolling-feature history; those earlier dates are not
    used as the reported benchmark window.
    """
    panel_path = CACHE / "panel.parquet"
    basic_path = CACHE / "basic.csv"
    if not panel_path.exists() or not basic_path.exists():
        return None

    try:
        panel = pd.read_parquet(panel_path, columns=["trade_date", "ts_code"])
        basic = pd.read_csv(basic_path, dtype=str)
    except Exception as exc:
        print(f"  ⚠ existing-cache universe seed unavailable: {exc}", flush=True)
        return None

    if panel.empty or "ts_code" not in basic.columns:
        return None
    panel["trade_date"] = panel["trade_date"].astype(str)
    panel["ts_code"] = panel["ts_code"].astype(str)
    panel["month"] = panel["trade_date"].str[:6]
    basic["ts_code"] = basic["ts_code"].astype(str)
    if "name" not in basic.columns:
        basic["name"] = basic["ts_code"]
    if "industry" not in basic.columns:
        basic["industry"] = "—"

    known_codes = sorted(set(basic["ts_code"]) | set(panel["ts_code"]))
    if not known_codes:
        return None
    meta = (
        basic.drop_duplicates("ts_code", keep="last")
        .set_index("ts_code")[["name", "industry"]]
        .to_dict(orient="index")
    )
    month_codes = {
        str(month): sorted(g["ts_code"].unique())
        for month, g in panel.groupby("month", sort=True)
    }
    existing_months = sorted(month_codes)
    first_existing = existing_months[0]
    rows: list[dict[str, object]] = []
    latest_month = first_existing
    for month in _window_months(start_date, end_date):
        if month in month_codes:
            codes = month_codes[month]
            source_month = month
            source = "existing_panel_monthly_seed"
            latest_month = month
        elif month < first_existing:
            codes = known_codes
            source_month = "all_known"
            source = f"basic_csv_history_warmup_seed_before_{first_existing}"
        else:
            codes = month_codes.get(latest_month, known_codes)
            source_month = latest_month
            source = f"existing_panel_monthly_seed|fallback_from_{latest_month}"
        for rank, ts_code in enumerate(codes, 1):
            info = meta.get(ts_code, {})
            rows.append({
                "month": month,
                "ts_code": ts_code,
                "name": info.get("name", ts_code),
                "industry": info.get("industry", "—"),
                "float_market_cap": float(len(codes) - rank + 1),
                "source_month": source_month,
                "source": source,
            })

    membership = pd.DataFrame(rows)
    basic_out = (
        pd.DataFrame({
            "ts_code": known_codes,
            "name": [meta.get(ts, {}).get("name", ts) for ts in known_codes],
            "industry": [meta.get(ts, {}).get("industry", "—") for ts in known_codes],
        })
        .drop_duplicates("ts_code", keep="last")
        .reset_index(drop=True)
    )
    print(
        f"  seeded top1000 membership from existing cache: "
        f"{membership.month.nunique()} months, {basic_out.ts_code.nunique()} unique stocks"
    )
    return membership[["month", "ts_code", "source_month", "source"]], basic_out


def build_top1000_membership(bs, start_date: str, end_date: str, n: int = 1000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return monthly membership plus a code/name/industry table.

    AKShare provides the monthly top1000 selection snapshot. If a month has no
    fresh snapshot because the endpoint failed, we carry forward the nearest
    cached month. During a first historical backfill, the first available
    snapshot is used as a clearly marked seed for earlier months.
    """
    target_month = _month_key(end_date)
    seed_from_existing = _seed_top1000_membership_from_existing_cache(start_date, end_date)
    cache = _read_top1000_cache()
    if target_month not in set(cache.get("month", pd.Series(dtype=str)).astype(str)):
        try:
            snapshot = _fetch_akshare_top1000(target_month, n)
            _write_top1000_cache(snapshot)
            cache = _read_top1000_cache()
        except Exception as exc:
            print(f"  ⚠ AKShare top1000 snapshot failed: {exc}", flush=True)
            if seed_from_existing is not None:
                print("  → using existing panel/basic.csv as historical warmup universe seed")
                return seed_from_existing
            if cache.empty:
                raise RuntimeError(
                    "No top1000 universe cache exists and AKShare selection failed. "
                    "Seed build/cache/top1000_universe.csv or retry when AKShare/Eastmoney is reachable."
                ) from exc

    window_months = _window_months(start_date, end_date)
    cache_months = set(cache.get("month", pd.Series(dtype=str)).astype(str))
    if seed_from_existing is not None and not set(window_months).issubset(cache_months):
        print("  → using existing panel/basic.csv seed because top1000 cache lacks full window coverage")
        return seed_from_existing

    memberships = []
    for month in window_months:
        snap = _snapshot_for_month(cache, month)
        if snap is None or snap.empty:
            raise RuntimeError(f"no top1000 membership available for {month}")
        m = snap[["ts_code", "name", "float_market_cap", "source", "source_month"]].copy()
        m["month"] = month
        memberships.append(m)
    membership = pd.concat(memberships, ignore_index=True)
    latest_meta = (
        membership.sort_values(["month", "float_market_cap"], ascending=[True, False])
        .drop_duplicates("ts_code", keep="last")
        [["ts_code", "name"]]
        .reset_index(drop=True)
    )
    basic = apply_industry(latest_meta, bs)
    print(
        f"[1/4] top1000 membership: {membership.month.nunique()} months, "
        f"{membership.ts_code.nunique()} unique stocks"
    )
    return membership[["month", "ts_code", "source_month", "source"]], basic[["ts_code", "name", "industry"]]


def _query_kdata_with_retry(bs, bs_code, fields, start_date, end_date,
                            adjustflag="2", retries: int = 3) -> pd.DataFrame | None:
    """单只股票 k 线查询，带 socket 超时重试 + 重建连接。

    返回 DataFrame；连重试都失败返回 None（由调用方决定 skip 还是 abort）。
    """
    for attempt in range(1, retries + 1):
        try:
            with _hard_deadline(HARD_TIMEOUT):
                rs = bs.query_history_k_data_plus(
                    bs_code, fields,
                    start_date=start_date, end_date=end_date,
                    frequency="d", adjustflag=adjustflag,
                )
                if rs.error_code != "0":
                    raise RuntimeError(f"error_code={rs.error_code} {rs.error_msg}")
                return _bs_query_to_df(rs)   # rs.next() 的 socket recv 也包进硬超时
        except (TimeoutError, socket.timeout, OSError, RuntimeError) as e:
            print(f"    ⚠ {bs_code} query attempt {attempt}/{retries} failed: {e}", flush=True)
            if attempt < retries:
                _relogin(bs)
    return None


def get_daily_panel(bs, ts_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """拉每只股票日线 OHLCV + PE/PB/PS/turnover (一次 query 全拿)。"""
    print(f"[2/4] 拉取 {len(ts_codes)} 只股票 [{start_date}~{end_date}] 日线 ...")
    fields = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,peTTM,pbMRQ,psTTM"
    rows = []
    skipped = 0
    failed = []
    for i, ts_code in enumerate(ts_codes):
        bs_code = _ts_to_bs_code(ts_code)
        df = _query_kdata_with_retry(bs, bs_code, fields, start_date, end_date)
        if df is None:
            failed.append(ts_code)
            continue
        if df.empty:
            skipped += 1
            continue
        df["ts_code"] = ts_code
        rows.append(df)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(ts_codes)}")

    if failed:
        # 增量模式下只新增 1-2 天，少数股票拉失败可容忍（下次增量会补齐）；
        # 但全员失败说明连接彻底坏了，必须 abort 让 CI 标红而不是 commit 残缺数据。
        print(f"  ⚠️ {len(failed)} 只股票重试后仍失败: {failed[:10]}{' ...' if len(failed) > 10 else ''}")
        if len(failed) == len(ts_codes):
            raise RuntimeError("BaoStock 全部股票查询失败，连接不可用，中止本次更新")

    if not rows:
        print("  ⚠ 该窗口内 BaoStock 没数据（可能是周末/假期），返回空 panel")
        return pd.DataFrame(columns=[
            "ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "vol", "amount", "turnover_rate", "pct_chg",
            "pe_ttm", "pb", "ps_ttm", "vwap", "turnover_rate_f", "volume_ratio",
            "net_mf_amount", "buy_sm_amount", "buy_md_amount",
            "buy_lg_amount", "buy_elg_amount", "sell_sm_amount",
            "sell_md_amount", "sell_lg_amount", "sell_elg_amount",
        ])

    panel = pd.concat(rows, ignore_index=True)
    print(f"  → {len(panel)} 行 (skipped {skipped} 股)")

    # Rename to match training-time tushare schema
    panel = panel.rename(columns={
        "date": "trade_date",
        "volume": "vol",
        "turn": "turnover_rate",
        "pctChg": "pct_chg",
        "preclose": "pre_close",
        "peTTM": "pe_ttm",
        "pbMRQ": "pb",
        "psTTM": "ps_ttm",
    })
    panel["trade_date"] = panel["trade_date"].apply(_date_to_compact)

    # Cast numeric columns
    num_cols = ["open", "high", "low", "close", "pre_close", "vol", "amount",
                "turnover_rate", "pct_chg", "pe_ttm", "pb", "ps_ttm"]
    for c in num_cols:
        if c in panel.columns:
            panel[c] = pd.to_numeric(panel[c], errors="coerce")

    # Derived: vwap
    panel["vwap"] = panel["amount"] / panel["vol"].replace(0, pd.NA)

    # Stubbed fields not provided by BaoStock — features.py 用到它们会喂 0
    # （cross-sectional z-score 下 0 == neutral，不会引入虚假信号）
    panel["turnover_rate_f"] = panel["turnover_rate"]   # 自由换手率近似
    panel["volume_ratio"] = pd.NA                        # 量比，缺
    for c in ["net_mf_amount", "buy_sm_amount", "buy_md_amount",
              "buy_lg_amount", "buy_elg_amount",
              "sell_sm_amount", "sell_md_amount",
              "sell_lg_amount", "sell_elg_amount"]:
        panel[c] = 0.0
    return panel


def get_csi300_index(bs, start_date: str, end_date: str) -> pd.DataFrame:
    """获取沪深 300 指数日线作为基准。"""
    print("[3/4] 拉取沪深 300 指数日线 ...")
    df = _query_kdata_with_retry(
        bs, "sh.000300",
        "date,open,high,low,close,preclose,volume,amount,pctChg",
        start_date, end_date, adjustflag="3",   # 3 = 不复权 (指数)
    )
    if df is None:
        raise RuntimeError("BaoStock 沪深300指数查询失败")
    df = df.rename(columns={"date": "trade_date"})
    df["trade_date"] = df["trade_date"].apply(_date_to_compact)
    df["ts_code"] = "000300.SH"
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    print(f"  → {len(df)} 行")
    return df[["ts_code", "trade_date", "open", "high", "low", "close"]]


def _compact_to_iso(d: str) -> str:
    """20260529 -> 2026-05-29."""
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["top1000", "csi300"], default="top1000",
                        help="stock universe (default: dynamic top1000)")
    parser.add_argument("--top-n", type=int, default=1000,
                        help="number of names for --universe top1000")
    parser.add_argument("--days", type=int, default=None,
                        help="往前回溯多少自然日；不传时默认从 2025-04-01 回填 warmup")
    parser.add_argument("--start", default=None,
                        help=f"显式起始日期 YYYY-MM-DD (覆盖 --days)。默认 {DEFAULT_HISTORY_START}。")
    parser.add_argument("--end", default=None,
                        help="显式结束日期 YYYY-MM-DD (默认今天)。")
    parser.add_argument("--incremental", action="store_true",
                        help="增量模式：读已有 panel.parquet 的 max_date，"
                             "只拉自那之后的新数据，append + dedupe。"
                             "首次跑请用 --start 全量回填。")
    args = parser.parse_args()

    # CI 非 TTY 下 stdout 默认块缓冲，step 被 kill 时日志全丢；改行缓冲方便定位 hang。
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    today = datetime.now()
    raw_end_date = args.end or today.strftime("%Y-%m-%d")
    end_date = datetime.strptime(
        str(raw_end_date).replace("-", "")[:8],
        "%Y%m%d",
    ).strftime("%Y-%m-%d")

    if args.incremental:
        panel_path = CACHE / "panel.parquet"
        if not panel_path.exists():
            raise SystemExit(
                "[fetch] --incremental 需要已有 panel.parquet。"
                "首次请改用 --start YYYY-MM-DD 全量回填。"
            )
        existing_panel = pd.read_parquet(panel_path)
        existing_panel["trade_date"] = existing_panel["trade_date"].astype(str)
        max_d = existing_panel["trade_date"].max()
        # 从 max_d 后一个自然日开始拉
        from datetime import timedelta as _td
        next_d = datetime.strptime(max_d, "%Y%m%d") + _td(days=1)
        start_date = next_d.strftime("%Y-%m-%d")
        if start_date > end_date:
            print(f"[fetch] panel 已是最新 (max={max_d})，无需更新。")
            return
        print(f"[fetch incremental] panel max={max_d}, 新增窗口 {start_date} → {end_date}")
    elif args.start:
        start_date = datetime.strptime(
            str(args.start).replace("-", "")[:8],
            "%Y%m%d",
        ).strftime("%Y-%m-%d")
    elif args.days is None:
        start_date = DEFAULT_HISTORY_START
    else:
        start_date = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"[fetch] window: {start_date} → {end_date}")

    import baostock as bs
    _bs_login(bs)

    try:
        # 0. 前置检查：窗口内无交易日（周末/假期/数据未就绪）则干净退出，
        #    避免对"无交易日区间"的 k 线 query 触发 BaoStock 永久阻塞。
        if not _has_trading_day(bs, start_date, end_date):
            print(f"[fetch] {start_date}–{end_date} 窗口内无交易日，无需更新，跳过。", flush=True)
            return

        # 1. Universe + industry. For top1000 this builds monthly membership
        #    and later filters panel rows by trade-date month.
        membership = None
        if args.universe == "top1000":
            membership, comps = build_top1000_membership(bs, start_date, end_date, n=args.top_n)
        else:
            comps = get_csi300_components(bs)
        comps.to_csv(CACHE / "basic.csv", index=False)
        print(f"  saved → {CACHE / 'basic.csv'}")

        # 2. 全成分股日线 panel
        new_panel = get_daily_panel(bs, comps["ts_code"].tolist(), start_date, end_date)
        if membership is not None and len(new_panel):
            membership = membership.copy()
            membership["month"] = membership["month"].astype(str)
            new_panel["month"] = new_panel["trade_date"].astype(str).str[:6]
            before_filter = len(new_panel)
            new_panel = new_panel.merge(
                membership[["month", "ts_code"]],
                on=["month", "ts_code"],
                how="inner",
            ).drop(columns=["month"])
            print(f"  top1000 monthly filter: {before_filter} → {len(new_panel)} rows")

        if args.incremental:
            existing_panel = pd.read_parquet(CACHE / "panel.parquet")
            existing_panel["trade_date"] = existing_panel["trade_date"].astype(str)
            if len(new_panel) == 0:
                panel = existing_panel
                print(f"  panel 无新增（{start_date}–{end_date} 无交易日），保持 {len(panel)} 行")
            else:
                new_panel["trade_date"] = new_panel["trade_date"].astype(str)
                before = len(existing_panel)
                panel = pd.concat([existing_panel, new_panel], ignore_index=True)
                panel = panel.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
                panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
                print(f"  panel merge: {before} + {len(new_panel)} (new) → {len(panel)} after dedupe")
        else:
            panel = new_panel
        panel.to_parquet(CACHE / "panel.parquet", index=False)
        print(f"  saved → {CACHE / 'panel.parquet'}  rows={len(panel)}")

        # 3. CSI 300 index
        new_idx = get_csi300_index(bs, start_date, end_date)
        if args.incremental and (CACHE / "csi300.parquet").exists():
            existing_idx = pd.read_parquet(CACHE / "csi300.parquet")
            existing_idx["trade_date"] = existing_idx["trade_date"].astype(str)
            new_idx["trade_date"] = new_idx["trade_date"].astype(str)
            idx = pd.concat([existing_idx, new_idx], ignore_index=True)
            idx = idx.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
            idx = idx.sort_values("trade_date").reset_index(drop=True)
        else:
            idx = new_idx
        idx.to_parquet(CACHE / "csi300.parquet", index=False)
        print(f"  saved → {CACHE / 'csi300.parquet'}  rows={len(idx)}")

        print(f"\n[4/4] all data fetched.")
    finally:
        bs.logout()


if __name__ == "__main__":
    main()
