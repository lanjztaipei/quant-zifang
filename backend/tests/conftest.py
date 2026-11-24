"""Shared pytest fixtures and test doubles (all mocked, no network)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.atr import OHLCBar
from app.main import create_app


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeMarketDataFetcher:
    def __init__(self, bars_by_symbol: dict[str, list[OHLCBar]] | None = None) -> None:
        self.bars_by_symbol: dict[str, list[OHLCBar]] = bars_by_symbol or {}
        self.call_count: dict[str, int] = {}

    def fetch_daily_bars(self, symbol: str) -> list[OHLCBar]:
        self.call_count[symbol] = self.call_count.get(symbol, 0) + 1
        return list(self.bars_by_symbol.get(symbol, []))


@pytest.fixture
def make_client(tmp_path: Path):
    def _factory(
        *,
        clock: FixedClock | None = None,
        fetcher: FakeMarketDataFetcher | None = None,
        cors_origins: tuple[str, ...] = ("http://localhost:5173",),
    ) -> TestClient:
        settings = Settings(data_dir=tmp_path, cors_origins=cors_origins)
        app = create_app(
            settings=settings,
            clock=clock or FixedClock(datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)),
            fetcher=fetcher or FakeMarketDataFetcher(),
        )
        return TestClient(app)

    return _factory
