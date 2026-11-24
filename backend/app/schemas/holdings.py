"""Holdings CRUD and settlement API schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import DecimalInput, StrictIntInput


class StoredLotSchema(BaseModel):
    id: str
    type: Literal["base", "grid"]
    price: str
    shares: int
    filled_at: str | None = None
    note: str | None = None


class HoldingResponse(BaseModel):
    symbol: str
    B: str
    initial_price: str
    P0: str
    a: str
    b: str
    c: str
    K: str
    realized_profit: str
    base_profit_pool: str
    atr_14_pct: str | None = None
    atr_50_pct: str | None = None
    atr_source: Literal["fetched", "manual"] | None = None
    atr_date: str | None = None
    lots: list[StoredLotSchema]


class HoldingsListResponse(BaseModel):
    symbols: list[str]


class UpsertHoldingRequest(BaseModel):
    B: DecimalInput
    initial_price: DecimalInput
    P0: DecimalInput = Decimal("0.30")
    a: DecimalInput = Decimal("0.6")
    b: DecimalInput = Decimal("0.1")
    c: DecimalInput = Decimal("0.5")
    K: DecimalInput = Decimal("6")
    realized_profit: DecimalInput | None = None
    base_profit_pool: DecimalInput | None = None
    atr_14_pct: DecimalInput | None = None
    atr_50_pct: DecimalInput | None = None
    atr_source: Literal["fetched", "manual"] | None = None
    atr_date: str | None = None


class LotMutationRequest(BaseModel):
    type: Literal["base", "grid"]
    price: DecimalInput
    shares: StrictIntInput
    filled_at: str | None = None
    note: str | None = None


class AddLotResponse(BaseModel):
    id: str
    holding: HoldingResponse


class DeleteHoldingResponse(BaseModel):
    deleted: bool
    symbol: str


class SettleLotRequest(BaseModel):
    exit_price: DecimalInput
    retain_shares: StrictIntInput | None = None


class SettlementSummarySchema(BaseModel):
    lot_id: str
    exit_price: str
    realized_gain: str
    retain_shares: int
    sell_shares: int
    realized_profit: str
    base_profit_pool: str


class SettleLotResponse(BaseModel):
    settlement: SettlementSummarySchema
    holding: HoldingResponse
