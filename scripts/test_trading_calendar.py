"""Small offline checks for the trading-session guard's holiday behavior."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

from trading_calendar import resolve_session


def main() -> None:
    golden_week = ["20250930", "20251009", "20251010"]
    assert resolve_session("20250930", golden_week) == {
        "trade_date": "20250930",
        "is_trading_day": True,
        "next_trading_day": "20251009",
    }
    assert resolve_session("20251001", golden_week) == {
        "trade_date": "20251001",
        "is_trading_day": False,
        "next_trading_day": "20251009",
    }
    assert resolve_session("20251011", golden_week) == {
        "trade_date": "20251011",
        "is_trading_day": False,
        "next_trading_day": None,
    }
    print("trading-calendar guard checks passed")


if __name__ == "__main__":
    main()
