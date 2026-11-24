"""Market data API schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import WarningSchema


class MarketDataResponse(BaseModel):
    symbol: str
    trading_date: str
    close: str
    atr_14_pct: str
    atr_50_pct: str
    cache_hit: bool
    warnings: list[WarningSchema]
