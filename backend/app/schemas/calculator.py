"""Calculator API request and response schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import DecimalInput, StrictIntInput, WarningSchema


class LotInputSchema(BaseModel):
    id: str | None = None
    type: Literal["base", "grid"]
    price: DecimalInput
    shares: StrictIntInput
    filled_at: str | None = None
    note: str | None = None


class CalculatorComputeRequest(BaseModel):
    symbol: str
    B: DecimalInput
    initial_price: DecimalInput
    P0: DecimalInput = Decimal("0.30")
    a: DecimalInput = Decimal("0.6")
    b: DecimalInput = Decimal("0.1")
    c: DecimalInput = Decimal("0.5")
    K: DecimalInput = Decimal("6")
    realized_profit: DecimalInput = Decimal("0")
    base_profit_pool: DecimalInput = Decimal("0")
    atr_14_pct: DecimalInput
    atr_50_pct: DecimalInput
    holdings: list[LotInputSchema] = Field(default_factory=list)
    current_price: DecimalInput | None = None


class ReverseBuySchema(BaseModel):
    buy_trigger_price: str
    buy_trail_pct: str
    buy_max_price: str
    shares: int


class ComputedLotSchema(BaseModel):
    id: str | None
    type: Literal["base", "grid"]
    price: str
    shares: int
    filled_at: str | None
    note: str | None
    tp: str | None
    tp_trail_pct: str | None
    tp_reached: bool | None
    expected_profit: str | None
    proj_base_pool: str | None
    retain_shares: int
    sell_shares: int
    reverse_buy: ReverseBuySchema | None


class ReverseSellSchema(BaseModel):
    sell_trigger_price: str
    sell_trail_pct: str
    expected_profit: str
    proj_base_pool: str
    retain_shares: int
    sell_shares: int


class FutureGridLevelSchema(BaseModel):
    j: int
    P_j: str
    buy_trail_pct: str
    P_j_max: str
    Q_j: int
    cum_invest: str
    TP_j: str
    breached: bool | None
    reverse_sell: ReverseSellSchema


class StrategyParamsSummarySchema(BaseModel):
    atr_eff_pct: str
    x: str
    y: str
    z: str
    N: int
    N_rem: int
    max_safe_drop: str


class StrategyDashboardSchema(BaseModel):
    total_shares: int
    base_shares: int
    grid_shares: int
    avg_cost: str | None
    B: str
    realized_profit: str
    B_eff: str
    base_profit_pool: str
    C_now: str
    remaining_cash: str
    utilization: str
    remaining_cover: str
    P_anchor: str | None
    warnings: list[WarningSchema]


class CalculatorComputeResponse(BaseModel):
    symbol: str
    mode: Literal["new", "rebalance"]
    params_summary: StrategyParamsSummarySchema
    dashboard: StrategyDashboardSchema
    holdings: list[ComputedLotSchema]
    future_grid: list[FutureGridLevelSchema]
