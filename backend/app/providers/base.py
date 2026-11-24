"""Interfaces (Protocols) for clock and market data fetching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol

from app.core.atr import OHLCBar
from app.core.strategy import WarningItem


class Clock(Protocol):
    """Injectable current-time provider."""

    def now(self) -> datetime: ...


class SystemClock:
    """Default UTC system clock."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class MarketDataFetcher(Protocol):
    """Injectable daily OHLC bar fetcher."""

    def fetch_daily_bars(self, symbol: str) -> list[OHLCBar]: ...


@dataclass(frozen=True)
class MarketDataResult:
    symbol: str
    trading_date: date
    close: Decimal
    atr_14_pct: Decimal
    atr_50_pct: Decimal
    cache_hit: bool
    warnings: tuple[WarningItem, ...]


class MarketDataService(Protocol):
    """High-level market data service interface."""

    def get_market_data(self, symbol: str, force_refresh: bool = False) -> MarketDataResult: ...
