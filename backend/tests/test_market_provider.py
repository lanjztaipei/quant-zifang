"""Tests for MarketDataProvider caching, staleness, errors, and yfinance adapter."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.providers.yfinance_provider import YFinanceFetcher
from tests.conftest import FakeMarketDataFetcher, FixedClock
from tests.test_atr import ATR_A_RAW_BARS, ATR_B_RAW_BARS

ET = ZoneInfo("America/New_York")


def test_market_cache_miss_then_hit_and_force_refresh(tmp_path: Path, make_client) -> None:
    clock = FixedClock(datetime(2026, 11, 23, 11, 0, tzinfo=ET))
    fetcher = FakeMarketDataFetcher({"AAPL": ATR_B_RAW_BARS})
    client = make_client(clock=clock, fetcher=fetcher)

    # 1. Cache miss -> fetches, filters out intraday 2026-11-23 bar, computes ATR, writes cache
    resp1 = client.get("/api/v1/market/aapl")
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1 == {
        "symbol": "AAPL",
        "trading_date": "2026-11-20",
        "close": "115.82",
        "atr_14_pct": "0.026405",
        "atr_50_pct": "0.026468",
        "cache_hit": False,
        "warnings": [],
    }
    assert fetcher.call_count["AAPL"] == 1

    cache_path = tmp_path / "atr_cache.json"
    assert cache_path.exists()
    cache_content = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "AAPL_2026-11-20" in cache_content
    assert cache_content["AAPL_2026-11-20"]["trading_date"] == "2026-11-20"
    assert cache_content["AAPL_2026-11-20"]["close"] == "115.82"
    assert cache_content["AAPL_2026-11-20"]["atr_14_pct"] == "0.026405"
    assert cache_content["AAPL_2026-11-20"]["atr_50_pct"] == "0.026468"
    assert "fetched_at" in cache_content["AAPL_2026-11-20"]

    # 2. Cache hit -> does NOT call fetcher again
    resp2 = client.get("/api/v1/market/AAPL")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["cache_hit"] is True
    assert body2["close"] == "115.82"
    assert body2["atr_14_pct"] == "0.026405"
    assert body2["atr_50_pct"] == "0.026468"
    assert body2["warnings"] == []
    assert fetcher.call_count["AAPL"] == 1

    # 3. force_refresh=true -> bypasses cache and refetches
    resp3 = client.get("/api/v1/market/AAPL?force_refresh=true")
    assert resp3.status_code == 200
    assert resp3.json()["cache_hit"] is False
    assert fetcher.call_count["AAPL"] == 2


def test_market_stale_data_returns_warning_and_does_not_write_cache(
    tmp_path: Path, make_client
) -> None:
    clock = FixedClock(datetime(2026, 11, 23, 11, 0, tzinfo=ET))
    # Drop the 2026-11-20 bar and intraday bar so latest available bar is 2026-11-19 (59 bars)
    stale_bars = [bar for bar in ATR_B_RAW_BARS if bar.date <= date(2026, 11, 19)]
    fetcher = FakeMarketDataFetcher({"AAPL": stale_bars})
    client = make_client(clock=clock, fetcher=fetcher)

    resp = client.get("/api/v1/market/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["trading_date"] == "2026-11-19"
    assert body["close"] == "115.86"
    assert body["cache_hit"] is False
    assert len(body["warnings"]) == 1
    assert body["warnings"][0]["code"] == "STALE_MARKET_DATA"

    # Must NOT write to cache when stale
    cache_path = tmp_path / "atr_cache.json"
    if cache_path.exists():
        cache_content = json.loads(cache_path.read_text(encoding="utf-8"))
        assert "AAPL_2026-11-20" not in cache_content
        assert "AAPL_2026-11-19" not in cache_content

    # Subsequent call still fetches because nothing was cached
    resp2 = client.get("/api/v1/market/AAPL")
    assert resp2.status_code == 200
    assert resp2.json()["cache_hit"] is False
    assert fetcher.call_count["AAPL"] == 2


def test_market_unknown_symbol_returns_404(make_client) -> None:
    client = make_client(fetcher=FakeMarketDataFetcher({}))
    resp = client.get("/api/v1/market/NOPE")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert "message" in body


def test_market_insufficient_bars_returns_422(make_client) -> None:
    # ATR_A has only 16 closed bars (< 51 required for ATR50)
    fetcher = FakeMarketDataFetcher({"SHORT": ATR_A_RAW_BARS})
    client = make_client(fetcher=fetcher)
    resp = client.get("/api/v1/market/SHORT")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"


def test_market_invalid_symbol_returns_422(make_client) -> None:
    client = make_client()
    resp = client.get("/api/v1/market/BAD$SYM")
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_yfinance_fetcher_uses_history_auto_adjust_and_never_info(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class DummyTicker:
        def __init__(self, symbol: str) -> None:
            captured["symbol"] = symbol

        @property
        def info(self):  # pragma: no cover - must never be called
            raise AssertionError("YFinanceFetcher must never access .info")

        def history(self, *, period: str, auto_adjust: bool):
            captured["period"] = period
            captured["auto_adjust"] = auto_adjust
            idx = pd.to_datetime(["2026-11-19", "2026-11-20"])
            return pd.DataFrame(
                {
                    "High": [102.5, 105.25],
                    "Low": [99.5, 101.75],
                    "Close": [101.0, 104.10],
                },
                index=idx,
            )

    monkeypatch.setattr("app.providers.yfinance_provider.yf.Ticker", DummyTicker)
    bars = YFinanceFetcher().fetch_daily_bars("AAPL")
    assert captured == {"symbol": "AAPL", "period": "2y", "auto_adjust": True}
    assert len(bars) == 2
    assert bars[0].date == date(2026, 11, 19)
    assert bars[1].close == Decimal("104.1")
