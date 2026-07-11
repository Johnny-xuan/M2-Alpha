"""BaoStock-backed A-share session guard for the M-0-M update workflow."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def compact_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value).replace("-", "")[:8]


def resolve_session(target_date: str, calendar_dates: list[str]) -> dict[str, object]:
    """Resolve whether target_date is a trading session and its next session.

    The pure function makes holiday behavior testable without a network call.
    """
    target = compact_date(target_date)
    dates = sorted({compact_date(value) for value in calendar_dates})
    next_dates = [value for value in dates if value > target]
    return {
        "trade_date": target,
        "is_trading_day": target in dates,
        "next_trading_day": next_dates[0] if next_dates else None,
    }


def query_trade_dates(start_date: str, end_date: str) -> list[str]:
    import baostock as bs

    login = bs.login()
    if getattr(login, "error_code", "0") != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_code} {login.error_msg}")
    try:
        result = bs.query_trade_dates(start_date=start_date, end_date=end_date)
        if getattr(result, "error_code", "0") != "0":
            raise RuntimeError(
                f"BaoStock trading-calendar query failed: {result.error_code} {result.error_msg}"
            )
        frame = result.get_data()
    finally:
        bs.logout()

    if frame.empty or not {"calendar_date", "is_trading_day"}.issubset(frame.columns):
        raise RuntimeError("BaoStock returned no usable trading-calendar rows")
    return [
        compact_date(row.calendar_date)
        for row in frame.itertuples(index=False)
        if str(row.is_trading_day) == "1"
    ]


def write_github_output(path: Path, status: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"trade_date={status['trade_date']}\n")
        handle.write(f"is_trading_day={'true' if status['is_trading_day'] else 'false'}\n")
        handle.write(f"next_trading_day={status['next_trading_day'] or ''}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Determine the current A-share session before a baseline update."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target Shanghai date in YYYY-MM-DD format; defaults to today in Asia/Shanghai.",
    )
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=45,
        help="Calendar look-ahead used to find the next open session.",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="Optional GitHub Actions output file.",
    )
    args = parser.parse_args()

    target = compact_date(args.date or datetime.now(SHANGHAI))
    start = datetime.strptime(target, "%Y%m%d").date()
    end = start + timedelta(days=args.horizon_days)
    calendar_dates = query_trade_dates(start.isoformat(), end.isoformat())
    status = resolve_session(target, calendar_dates)
    if not status["next_trading_day"]:
        raise RuntimeError(
            f"no next trading day found within {args.horizon_days} days after {target}"
        )

    print(json.dumps(status, ensure_ascii=False))
    output_path = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if output_path:
        write_github_output(Path(output_path), status)


if __name__ == "__main__":
    main()
