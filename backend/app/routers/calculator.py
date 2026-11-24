"""Stateless VAG Grid calculator route."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.decimal_utils import fmt_price, fmt_ratio
from app.core.strategy import HoldingLotInput, StrategyInput, compute_strategy
from app.schemas.calculator import (
    CalculatorComputeRequest,
    CalculatorComputeResponse,
    ComputedLotSchema,
    FutureGridLevelSchema,
    ReverseBuySchema,
    ReverseSellSchema,
    StrategyDashboardSchema,
    StrategyParamsSummarySchema,
)
from app.schemas.common import WarningSchema

router = APIRouter(prefix="/calculator", tags=["calculator"])


@router.post("/compute", response_model=CalculatorComputeResponse)
def calculator_compute(payload: CalculatorComputeRequest) -> CalculatorComputeResponse:
    strategy_input = StrategyInput(
        symbol=payload.symbol,
        B=payload.B,
        initial_price=payload.initial_price,
        P0=payload.P0,
        a=payload.a,
        b=payload.b,
        c=payload.c,
        K=payload.K,
        realized_profit=payload.realized_profit,
        base_profit_pool=payload.base_profit_pool,
        atr_14_pct=payload.atr_14_pct,
        atr_50_pct=payload.atr_50_pct,
        holdings=tuple(
            HoldingLotInput(
                id=lot.id,
                type=lot.type,
                price=lot.price,
                shares=lot.shares,
                filled_at=lot.filled_at,
                note=lot.note,
            )
            for lot in payload.holdings
        ),
        current_price=payload.current_price,
    )
    res = compute_strategy(strategy_input)

    ps = res.params_summary
    db = res.dashboard
    return CalculatorComputeResponse(
        symbol=res.symbol,
        mode=res.mode,
        params_summary=StrategyParamsSummarySchema(
            atr_eff_pct=fmt_ratio(ps.atr_eff_pct),
            x=fmt_ratio(ps.x),
            y=fmt_ratio(ps.y),
            z=fmt_ratio(ps.z),
            N=ps.N,
            N_rem=ps.N_rem,
            max_safe_drop=fmt_ratio(ps.max_safe_drop),
        ),
        dashboard=StrategyDashboardSchema(
            total_shares=db.total_shares,
            base_shares=db.base_shares,
            grid_shares=db.grid_shares,
            avg_cost=fmt_price(db.avg_cost) if db.avg_cost is not None else None,
            B=fmt_price(db.B),
            realized_profit=fmt_price(db.realized_profit),
            B_eff=fmt_price(db.B_eff),
            base_profit_pool=fmt_price(db.base_profit_pool),
            C_now=fmt_price(db.C_now),
            remaining_cash=fmt_price(db.remaining_cash),
            utilization=fmt_ratio(db.utilization),
            remaining_cover=fmt_ratio(db.remaining_cover),
            P_anchor=fmt_price(db.P_anchor) if db.P_anchor is not None else None,
            warnings=[WarningSchema(code=w.code, message=w.message) for w in db.warnings],
        ),
        holdings=[
            ComputedLotSchema(
                id=lot.id,
                type=lot.type,
                price=fmt_price(lot.price),
                shares=lot.shares,
                filled_at=lot.filled_at,
                note=lot.note,
                tp=fmt_price(lot.tp) if lot.tp is not None else None,
                tp_trail_pct=fmt_ratio(lot.tp_trail_pct) if lot.tp_trail_pct is not None else None,
                tp_reached=lot.tp_reached,
                expected_profit=(
                    fmt_price(lot.expected_profit) if lot.expected_profit is not None else None
                ),
                proj_base_pool=(
                    fmt_price(lot.proj_base_pool) if lot.proj_base_pool is not None else None
                ),
                retain_shares=lot.retain_shares,
                sell_shares=lot.sell_shares,
                reverse_buy=(
                    ReverseBuySchema(
                        buy_trigger_price=fmt_price(lot.reverse_buy.buy_trigger_price),
                        buy_trail_pct=fmt_ratio(lot.reverse_buy.buy_trail_pct),
                        buy_max_price=fmt_price(lot.reverse_buy.buy_max_price),
                        shares=lot.reverse_buy.shares,
                    )
                    if lot.reverse_buy is not None
                    else None
                ),
            )
            for lot in res.holdings
        ],
        future_grid=[
            FutureGridLevelSchema(
                j=lvl.j,
                P_j=fmt_price(lvl.P_j),
                buy_trail_pct=fmt_ratio(lvl.buy_trail_pct),
                P_j_max=fmt_price(lvl.P_j_max),
                Q_j=lvl.Q_j,
                cum_invest=fmt_price(lvl.cum_invest),
                TP_j=fmt_price(lvl.TP_j),
                breached=lvl.breached,
                reverse_sell=ReverseSellSchema(
                    sell_trigger_price=fmt_price(lvl.reverse_sell.sell_trigger_price),
                    sell_trail_pct=fmt_ratio(lvl.reverse_sell.sell_trail_pct),
                    expected_profit=fmt_price(lvl.reverse_sell.expected_profit),
                    proj_base_pool=fmt_price(lvl.reverse_sell.proj_base_pool),
                    retain_shares=lvl.reverse_sell.retain_shares,
                    sell_shares=lvl.reverse_sell.sell_shares,
                ),
            )
            for lvl in res.future_grid
        ],
    )
