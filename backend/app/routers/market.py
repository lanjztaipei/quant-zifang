"""Market data & ATR route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.decimal_utils import fmt_price, fmt_ratio
from app.dependencies import get_market_provider
from app.providers.base import MarketDataService
from app.schemas.common import WarningSchema
from app.schemas.market import MarketDataResponse

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/{symbol}", response_model=MarketDataResponse)
def get_market(
    symbol: str,
    force_refresh: bool = Query(default=False),
    provider: MarketDataService = Depends(get_market_provider),
) -> MarketDataResponse:
    result = provider.get_market_data(symbol, force_refresh=force_refresh)
    return MarketDataResponse(
        symbol=result.symbol,
        trading_date=result.trading_date.isoformat(),
        close=fmt_price(result.close),
        atr_14_pct=fmt_ratio(result.atr_14_pct),
        atr_50_pct=fmt_ratio(result.atr_50_pct),
        cache_hit=result.cache_hit,
        warnings=[WarningSchema(code=w.code, message=w.message) for w in result.warnings],
    )
