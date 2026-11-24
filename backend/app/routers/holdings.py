"""Holdings CRUD and grid lot settlement routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.decimal_utils import fmt_price
from app.dependencies import get_holdings_repo
from app.schemas.holdings import (
    AddLotResponse,
    DeleteHoldingResponse,
    HoldingResponse,
    HoldingsListResponse,
    LotMutationRequest,
    SettleLotRequest,
    SettleLotResponse,
    SettlementSummarySchema,
    UpsertHoldingRequest,
)
from app.storage.holdings_store import UNSET, HoldingsRepository, StoredHolding

router = APIRouter(prefix="/holdings", tags=["holdings"])


def _to_holding_response(holding: StoredHolding) -> HoldingResponse:
    return HoldingResponse.model_validate(holding.to_dict())


@router.get("", response_model=HoldingsListResponse)
def list_holdings(
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> HoldingsListResponse:
    return HoldingsListResponse(symbols=repo.list_symbols())


@router.get("/{symbol}", response_model=HoldingResponse)
def get_holding(
    symbol: str,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> HoldingResponse:
    return _to_holding_response(repo.get(symbol))


@router.put("/{symbol}", response_model=HoldingResponse)
def upsert_holding(
    symbol: str,
    payload: UpsertHoldingRequest,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> HoldingResponse:
    fields = payload.model_fields_set
    holding = repo.upsert_params(
        symbol,
        B=payload.B,
        initial_price=payload.initial_price,
        P0=payload.P0,
        a=payload.a,
        b=payload.b,
        c=payload.c,
        K=payload.K,
        realized_profit=payload.realized_profit if "realized_profit" in fields else UNSET,
        base_profit_pool=payload.base_profit_pool if "base_profit_pool" in fields else UNSET,
        atr_14_pct=payload.atr_14_pct if "atr_14_pct" in fields else UNSET,
        atr_50_pct=payload.atr_50_pct if "atr_50_pct" in fields else UNSET,
        atr_source=payload.atr_source if "atr_source" in fields else UNSET,
        atr_date=payload.atr_date if "atr_date" in fields else UNSET,
    )
    return _to_holding_response(holding)


@router.delete("/{symbol}", response_model=DeleteHoldingResponse)
def delete_holding(
    symbol: str,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> DeleteHoldingResponse:
    sym = symbol.upper()
    repo.delete_symbol(sym)
    return DeleteHoldingResponse(deleted=True, symbol=sym)


@router.post("/{symbol}/lots", response_model=AddLotResponse)
def add_lot(
    symbol: str,
    payload: LotMutationRequest,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> AddLotResponse:
    lot_id, holding = repo.add_lot(
        symbol,
        lot_type=payload.type,
        price=payload.price,
        shares=payload.shares,
        filled_at=payload.filled_at,
        note=payload.note,
    )
    return AddLotResponse(id=lot_id, holding=_to_holding_response(holding))


@router.put("/{symbol}/lots/{lot_id}", response_model=HoldingResponse)
def update_lot(
    symbol: str,
    lot_id: str,
    payload: LotMutationRequest,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> HoldingResponse:
    holding = repo.update_lot(
        symbol,
        lot_id,
        lot_type=payload.type,
        price=payload.price,
        shares=payload.shares,
        filled_at=payload.filled_at,
        note=payload.note,
    )
    return _to_holding_response(holding)


@router.delete("/{symbol}/lots/{lot_id}", response_model=HoldingResponse)
def delete_lot(
    symbol: str,
    lot_id: str,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> HoldingResponse:
    holding = repo.delete_lot(symbol, lot_id)
    return _to_holding_response(holding)


@router.post("/{symbol}/lots/{lot_id}/settle", response_model=SettleLotResponse)
def settle_lot(
    symbol: str,
    lot_id: str,
    payload: SettleLotRequest,
    repo: HoldingsRepository = Depends(get_holdings_repo),
) -> SettleLotResponse:
    summary, holding = repo.settle_lot(
        symbol,
        lot_id,
        exit_price=payload.exit_price,
        retain_shares=payload.retain_shares,
    )
    return SettleLotResponse(
        settlement=SettlementSummarySchema(
            lot_id=summary.lot_id,
            exit_price=fmt_price(summary.exit_price),
            realized_gain=fmt_price(summary.realized_gain),
            retain_shares=summary.retain_shares,
            sell_shares=summary.sell_shares,
            realized_profit=fmt_price(summary.realized_profit),
            base_profit_pool=fmt_price(summary.base_profit_pool),
        ),
        holding=_to_holding_response(holding),
    )
