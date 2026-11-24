"""YFinance bar fetcher and cached MarketDataProvider."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import certifi
import pandas as pd
import yfinance as yf

from app.core.atr import OHLCBar, compute_wilder_atr, filter_closed_bars
from app.core.calendar import get_latest_closed_session
from app.core.decimal_utils import fmt_price, fmt_ratio, round_price, to_decimal
from app.core.errors import NotFoundError, ValidationError
from app.core.strategy import WarningItem, validate_symbol
from app.providers.base import Clock, MarketDataFetcher, MarketDataResult
from app.storage.json_store import JsonFileStore

MIN_BARS_FOR_ATR50 = 51


def _ensure_ascii_ca_bundle() -> None:
    """Work around libcurl/curl_cffi error 77 on Windows when certifi path has non-ASCII chars."""
    if os.environ.get("CURL_CA_BUNDLE"):
        return
    ca_src = certifi.where()
    if ca_src.isascii():
        return
    ca_dst = Path(tempfile.gettempdir()) / "quant_zifang_cacert.pem"
    if not ca_dst.exists() or ca_dst.stat().st_size != Path(ca_src).stat().st_size:
        shutil.copyfile(ca_src, ca_dst)
    os.environ["CURL_CA_BUNDLE"] = str(ca_dst)


class YFinanceFetcher:
    """Fetches 2 years of auto-adjusted daily OHLC bars via yfinance (no `.info`)."""

    def fetch_daily_bars(self, symbol: str) -> list[OHLCBar]:
        _ensure_ascii_ca_bundle()
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y", auto_adjust=True)
        if df is None or df.empty:
            return []

        bars: list[OHLCBar] = []
        for idx, row in df.iterrows():
            high = row.get("High")
            low = row.get("Low")
            close = row.get("Close")
            if pd.isna(high) or pd.isna(low) or pd.isna(close):
                continue

            bar_date = (
                idx.date()
                if hasattr(idx, "date")
                else date.fromisoformat(str(idx)[:10])
            )
            bars.append(
                OHLCBar(
                    date=bar_date,
                    high=to_decimal(float(high), "High"),
                    low=to_decimal(float(low), "Low"),
                    close=to_decimal(float(close), "Close"),
                )
            )
        return bars


class MarketDataProvider:
    """Market data & ATR provider with XNYS calendar awareness and JSON caching."""

    def __init__(
        self,
        *,
        fetcher: MarketDataFetcher,
        cache_path: Path,
        clock: Clock,
    ) -> None:
        self._fetcher = fetcher
        self._cache_store = JsonFileStore(cache_path)
        self._clock = clock

    def get_market_data(self, symbol: str, force_refresh: bool = False) -> MarketDataResult:
        sym = validate_symbol(symbol)
        now = self._clock.now()
        latest_session = get_latest_closed_session(now)
        cache_key = f"{sym}_{latest_session.isoformat()}"

        if not force_refresh:
            cache_data = self._cache_store.read()
            cached = cache_data.get(cache_key)
            if isinstance(cached, dict):
                return MarketDataResult(
                    symbol=sym,
                    trading_date=date.fromisoformat(str(cached["trading_date"])),
                    close=to_decimal(cached["close"], "close"),
                    atr_14_pct=to_decimal(cached["atr_14_pct"], "atr_14_pct"),
                    atr_50_pct=to_decimal(cached["atr_50_pct"], "atr_50_pct"),
                    cache_hit=True,
                    warnings=(),
                )

        raw_bars = self._fetcher.fetch_daily_bars(sym)
        if not raw_bars:
            raise NotFoundError(f"查無代號 {sym} 的行情資料")

        closed_bars = filter_closed_bars(raw_bars, latest_session)
        if len(closed_bars) < MIN_BARS_FOR_ATR50:
            raise ValidationError(
                f"代號 {sym} 已收盤 K 棒僅 {len(closed_bars)} 根，少於 {MIN_BARS_FOR_ATR50} 根無法計算 ATR50"
            )

        atr14 = compute_wilder_atr(closed_bars, 14)
        atr50 = compute_wilder_atr(closed_bars, 50)
        actual_date = closed_bars[-1].date
        latest_close = round_price(closed_bars[-1].close)

        warnings: tuple[WarningItem, ...] = ()
        if actual_date != latest_session:
            warnings = (
                WarningItem(
                    code="STALE_MARKET_DATA",
                    message=(
                        f"實際行情資料日期為 {actual_date.isoformat()}，"
                        f"落後於最新已收盤交易日 {latest_session.isoformat()}（資料延遲或停牌），未寫入快取。"
                    ),
                ),
            )
        else:
            entry: dict[str, Any] = {
                "trading_date": actual_date.isoformat(),
                "close": fmt_price(latest_close),
                "atr_14_pct": fmt_ratio(atr14.atr_pct_rounded),
                "atr_50_pct": fmt_ratio(atr50.atr_pct_rounded),
                "fetched_at": now.isoformat(),
            }

            def _write_cache(data: dict[str, Any]) -> None:
                data[cache_key] = entry

            self._cache_store.update(_write_cache)

        return MarketDataResult(
            symbol=sym,
            trading_date=actual_date,
            close=latest_close,
            atr_14_pct=atr14.atr_pct_rounded,
            atr_50_pct=atr50.atr_pct_rounded,
            cache_hit=False,
            warnings=warnings,
        )
