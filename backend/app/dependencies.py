"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from app.providers.base import MarketDataService
from app.storage.holdings_store import HoldingsRepository


def get_market_provider(request: Request) -> MarketDataService:
    return cast(MarketDataService, request.app.state.market_provider)


def get_holdings_repo(request: Request) -> HoldingsRepository:
    return cast(HoldingsRepository, request.app.state.holdings_repo)
