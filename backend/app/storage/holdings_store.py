"""Holdings repository protocol and JSON-backed implementation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from app.core.decimal_utils import ZERO, fmt_price, fmt_ratio, round_price, round_ratio, to_decimal
from app.core.errors import BaseLotExistsError, NotFoundError, ValidationError
from app.core.strategy import (
    compute_initial_base_shares,
    compute_settlement,
    validate_atr_params,
    validate_core_params,
    validate_lot_fields,
    validate_symbol,
)
from app.storage.json_store import JsonFileStore

UNSET = object()


@dataclass(frozen=True)
class StoredLot:
    id: str
    type: Literal["base", "grid"]
    price: Decimal
    shares: int
    filled_at: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "price": fmt_price(self.price),
            "shares": self.shares,
            "filled_at": self.filled_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StoredLot:
        return cls(
            id=str(raw["id"]),
            type=raw["type"],
            price=to_decimal(raw["price"], "lot.price"),
            shares=int(raw["shares"]),
            filled_at=raw.get("filled_at"),
            note=raw.get("note"),
        )


@dataclass(frozen=True)
class StoredHolding:
    symbol: str
    B: Decimal
    initial_price: Decimal
    P0: Decimal
    a: Decimal
    b: Decimal
    c: Decimal
    K: Decimal
    realized_profit: Decimal
    base_profit_pool: Decimal
    atr_14_pct: Decimal | None
    atr_50_pct: Decimal | None
    atr_source: Literal["fetched", "manual"] | None
    atr_date: str | None
    lots: tuple[StoredLot, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "B": fmt_price(self.B),
            "initial_price": fmt_price(self.initial_price),
            "P0": str(self.P0),
            "a": str(self.a),
            "b": str(self.b),
            "c": str(self.c),
            "K": str(self.K),
            "realized_profit": fmt_price(self.realized_profit),
            "base_profit_pool": fmt_price(self.base_profit_pool),
            "atr_14_pct": fmt_ratio(self.atr_14_pct) if self.atr_14_pct is not None else None,
            "atr_50_pct": fmt_ratio(self.atr_50_pct) if self.atr_50_pct is not None else None,
            "atr_source": self.atr_source,
            "atr_date": self.atr_date,
            "lots": [lot.to_dict() for lot in self.lots],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StoredHolding:
        return cls(
            symbol=str(raw["symbol"]),
            B=to_decimal(raw["B"], "B"),
            initial_price=to_decimal(raw["initial_price"], "initial_price"),
            P0=to_decimal(raw["P0"], "P0"),
            a=to_decimal(raw["a"], "a"),
            b=to_decimal(raw["b"], "b"),
            c=to_decimal(raw["c"], "c"),
            K=to_decimal(raw["K"], "K"),
            realized_profit=to_decimal(raw.get("realized_profit", "0"), "realized_profit"),
            base_profit_pool=to_decimal(raw.get("base_profit_pool", "0"), "base_profit_pool"),
            atr_14_pct=(
                to_decimal(raw["atr_14_pct"], "atr_14_pct")
                if raw.get("atr_14_pct") is not None
                else None
            ),
            atr_50_pct=(
                to_decimal(raw["atr_50_pct"], "atr_50_pct")
                if raw.get("atr_50_pct") is not None
                else None
            ),
            atr_source=raw.get("atr_source"),
            atr_date=raw.get("atr_date"),
            lots=tuple(StoredLot.from_dict(item) for item in raw.get("lots", [])),
        )


@dataclass(frozen=True)
class SettlementSummary:
    lot_id: str
    exit_price: Decimal
    realized_gain: Decimal
    retain_shares: int
    sell_shares: int
    realized_profit: Decimal
    base_profit_pool: Decimal


class HoldingsRepository(Protocol):
    def list_symbols(self) -> list[str]: ...
    def get(self, symbol: str) -> StoredHolding: ...
    def upsert_params(
        self,
        symbol: str,
        *,
        B: Decimal,
        initial_price: Decimal,
        P0: Decimal,
        a: Decimal,
        b: Decimal,
        c: Decimal,
        K: Decimal,
        realized_profit: Any = UNSET,
        base_profit_pool: Any = UNSET,
        atr_14_pct: Any = UNSET,
        atr_50_pct: Any = UNSET,
        atr_source: Any = UNSET,
        atr_date: Any = UNSET,
    ) -> StoredHolding: ...
    def delete_symbol(self, symbol: str) -> None: ...
    def add_lot(
        self,
        symbol: str,
        *,
        lot_type: Literal["base", "grid"],
        price: Decimal,
        shares: int,
        filled_at: str | None = None,
        note: str | None = None,
    ) -> tuple[str, StoredHolding]: ...
    def update_lot(
        self,
        symbol: str,
        lot_id: str,
        *,
        lot_type: Literal["base", "grid"],
        price: Decimal,
        shares: int,
        filled_at: str | None = None,
        note: str | None = None,
    ) -> StoredHolding: ...
    def delete_lot(self, symbol: str, lot_id: str) -> StoredHolding: ...
    def settle_lot(
        self,
        symbol: str,
        lot_id: str,
        *,
        exit_price: Decimal,
        retain_shares: int | None = None,
    ) -> tuple[SettlementSummary, StoredHolding]: ...


class JsonHoldingsStore:
    """JSON-file implementation of HoldingsRepository."""

    def __init__(self, path: Path) -> None:
        self._store = JsonFileStore(path)

    def list_symbols(self) -> list[str]:
        data = self._store.read()
        return sorted(data.keys())

    def get(self, symbol: str) -> StoredHolding:
        sym = symbol.upper()
        data = self._store.read()
        if sym not in data:
            raise NotFoundError(f"找不到代號 {sym} 的持股設定")
        return StoredHolding.from_dict(data[sym])

    def upsert_params(
        self,
        symbol: str,
        *,
        B: Decimal,
        initial_price: Decimal,
        P0: Decimal,
        a: Decimal,
        b: Decimal,
        c: Decimal,
        K: Decimal,
        realized_profit: Any = UNSET,
        base_profit_pool: Any = UNSET,
        atr_14_pct: Any = UNSET,
        atr_50_pct: Any = UNSET,
        atr_source: Any = UNSET,
        atr_date: Any = UNSET,
    ) -> StoredHolding:
        sym = validate_symbol(symbol)

        # Validate paired ATR presence before acquiring lock
        atr14_provided = atr_14_pct is not UNSET
        atr50_provided = atr_50_pct is not UNSET
        if atr14_provided != atr50_provided:
            raise ValidationError("atr_14_pct 與 atr_50_pct 必須同時提供或同時省略")
        if atr14_provided and ((atr_14_pct is None) != (atr_50_pct is None)):
            raise ValidationError("atr_14_pct 與 atr_50_pct 必須同時有值或同時為空")

        if (
            atr_source is not UNSET
            and atr_source is not None
            and atr_source not in ("fetched", "manual")
        ):
            raise ValidationError("atr_source 只能為 'fetched' 或 'manual'")

        def _mutate(data: dict[str, Any]) -> StoredHolding:
            existing = StoredHolding.from_dict(data[sym]) if sym in data else None

            eff_realized = (
                realized_profit
                if realized_profit is not UNSET and realized_profit is not None
                else (existing.realized_profit if existing is not None else ZERO)
            )
            eff_pool = (
                base_profit_pool
                if base_profit_pool is not UNSET and base_profit_pool is not None
                else (existing.base_profit_pool if existing is not None else ZERO)
            )
            eff_atr14 = (
                atr_14_pct
                if atr14_provided
                else (existing.atr_14_pct if existing is not None else None)
            )
            eff_atr50 = (
                atr_50_pct
                if atr50_provided
                else (existing.atr_50_pct if existing is not None else None)
            )
            eff_atr_source = (
                atr_source
                if atr_source is not UNSET
                else (existing.atr_source if existing is not None else None)
            )
            eff_atr_date = (
                atr_date
                if atr_date is not UNSET
                else (existing.atr_date if existing is not None else None)
            )

            validate_core_params(
                B=B,
                initial_price=initial_price,
                P0=P0,
                a=a,
                b=b,
                c=c,
                K=K,
                realized_profit=eff_realized,
                base_profit_pool=eff_pool,
            )
            if eff_atr14 is not None and eff_atr50 is not None:
                validate_atr_params(atr_14_pct=eff_atr14, atr_50_pct=eff_atr50, a=a)

            existing_lots = list(existing.lots) if existing is not None else []
            if len(existing_lots) == 0:
                q0 = compute_initial_base_shares(
                    B=B,
                    realized_profit=eff_realized,
                    P0=P0,
                    initial_price=initial_price,
                )
                if q0 > 0:
                    existing_lots = [
                        StoredLot(
                            id=str(uuid.uuid4()),
                            type="base",
                            price=round_price(initial_price),
                            shares=q0,
                            filled_at=None,
                            note=None,
                        )
                    ]

            updated = StoredHolding(
                symbol=sym,
                B=round_price(B),
                initial_price=round_price(initial_price),
                P0=P0,
                a=a,
                b=b,
                c=c,
                K=K,
                realized_profit=round_price(eff_realized),
                base_profit_pool=round_price(eff_pool),
                atr_14_pct=round_ratio(eff_atr14) if eff_atr14 is not None else None,
                atr_50_pct=round_ratio(eff_atr50) if eff_atr50 is not None else None,
                atr_source=eff_atr_source,
                atr_date=eff_atr_date,
                lots=tuple(existing_lots),
            )
            data[sym] = updated.to_dict()
            return updated

        return self._store.update(_mutate)

    def delete_symbol(self, symbol: str) -> None:
        sym = symbol.upper()

        def _mutate(data: dict[str, Any]) -> None:
            if sym not in data:
                raise NotFoundError(f"找不到代號 {sym} 的持股設定")
            del data[sym]

        self._store.update(_mutate)

    def add_lot(
        self,
        symbol: str,
        *,
        lot_type: Literal["base", "grid"],
        price: Decimal,
        shares: int,
        filled_at: str | None = None,
        note: str | None = None,
    ) -> tuple[str, StoredHolding]:
        sym = symbol.upper()
        validate_lot_fields(lot_type, price, shares)

        def _mutate(data: dict[str, Any]) -> tuple[str, StoredHolding]:
            if sym not in data:
                raise NotFoundError(f"找不到代號 {sym} 的持股設定")
            holding = StoredHolding.from_dict(data[sym])
            if lot_type == "base" and any(lot.type == "base" for lot in holding.lots):
                raise BaseLotExistsError(f"代號 {sym} 已存在底倉（base lot），不可重複新增")

            new_id = str(uuid.uuid4())
            new_lot = StoredLot(
                id=new_id,
                type=lot_type,
                price=round_price(price),
                shares=shares,
                filled_at=filled_at,
                note=note,
            )
            updated = StoredHolding(
                symbol=holding.symbol,
                B=holding.B,
                initial_price=holding.initial_price,
                P0=holding.P0,
                a=holding.a,
                b=holding.b,
                c=holding.c,
                K=holding.K,
                realized_profit=holding.realized_profit,
                base_profit_pool=holding.base_profit_pool,
                atr_14_pct=holding.atr_14_pct,
                atr_50_pct=holding.atr_50_pct,
                atr_source=holding.atr_source,
                atr_date=holding.atr_date,
                lots=holding.lots + (new_lot,),
            )
            data[sym] = updated.to_dict()
            return new_id, updated

        return self._store.update(_mutate)

    def update_lot(
        self,
        symbol: str,
        lot_id: str,
        *,
        lot_type: Literal["base", "grid"],
        price: Decimal,
        shares: int,
        filled_at: str | None = None,
        note: str | None = None,
    ) -> StoredHolding:
        sym = symbol.upper()
        validate_lot_fields(lot_type, price, shares)

        def _mutate(data: dict[str, Any]) -> StoredHolding:
            if sym not in data:
                raise NotFoundError(f"找不到代號 {sym} 的持股設定")
            holding = StoredHolding.from_dict(data[sym])
            target_idx = next(
                (i for i, lot in enumerate(holding.lots) if lot.id == lot_id),
                None,
            )
            if target_idx is None:
                raise NotFoundError(f"找不到持股編號 {lot_id}")

            if lot_type == "base" and any(
                lot.type == "base" and lot.id != lot_id for lot in holding.lots
            ):
                raise BaseLotExistsError(f"代號 {sym} 已存在其他底倉（base lot）")

            new_lots = list(holding.lots)
            new_lots[target_idx] = StoredLot(
                id=lot_id,
                type=lot_type,
                price=round_price(price),
                shares=shares,
                filled_at=filled_at,
                note=note,
            )
            updated = StoredHolding(
                symbol=holding.symbol,
                B=holding.B,
                initial_price=holding.initial_price,
                P0=holding.P0,
                a=holding.a,
                b=holding.b,
                c=holding.c,
                K=holding.K,
                realized_profit=holding.realized_profit,
                base_profit_pool=holding.base_profit_pool,
                atr_14_pct=holding.atr_14_pct,
                atr_50_pct=holding.atr_50_pct,
                atr_source=holding.atr_source,
                atr_date=holding.atr_date,
                lots=tuple(new_lots),
            )
            data[sym] = updated.to_dict()
            return updated

        return self._store.update(_mutate)

    def delete_lot(self, symbol: str, lot_id: str) -> StoredHolding:
        sym = symbol.upper()

        def _mutate(data: dict[str, Any]) -> StoredHolding:
            if sym not in data:
                raise NotFoundError(f"找不到代號 {sym} 的持股設定")
            holding = StoredHolding.from_dict(data[sym])
            new_lots = [lot for lot in holding.lots if lot.id != lot_id]
            if len(new_lots) == len(holding.lots):
                raise NotFoundError(f"找不到持股編號 {lot_id}")

            updated = StoredHolding(
                symbol=holding.symbol,
                B=holding.B,
                initial_price=holding.initial_price,
                P0=holding.P0,
                a=holding.a,
                b=holding.b,
                c=holding.c,
                K=holding.K,
                realized_profit=holding.realized_profit,
                base_profit_pool=holding.base_profit_pool,
                atr_14_pct=holding.atr_14_pct,
                atr_50_pct=holding.atr_50_pct,
                atr_source=holding.atr_source,
                atr_date=holding.atr_date,
                lots=tuple(new_lots),
            )
            data[sym] = updated.to_dict()
            return updated

        return self._store.update(_mutate)

    def settle_lot(
        self,
        symbol: str,
        lot_id: str,
        *,
        exit_price: Decimal,
        retain_shares: int | None = None,
    ) -> tuple[SettlementSummary, StoredHolding]:
        sym = symbol.upper()

        def _mutate(data: dict[str, Any]) -> tuple[SettlementSummary, StoredHolding]:
            if sym not in data:
                raise NotFoundError(f"找不到代號 {sym} 的持股設定")
            holding = StoredHolding.from_dict(data[sym])

            target_lot = next((lot for lot in holding.lots if lot.id == lot_id), None)
            if target_lot is None:
                raise NotFoundError(f"找不到持股編號 {lot_id}")

            base_lot = next((lot for lot in holding.lots if lot.type == "base"), None)
            calc = compute_settlement(
                lot_type=target_lot.type,
                lot_price=target_lot.price,
                lot_shares=target_lot.shares,
                exit_price=exit_price,
                retain_shares=retain_shares,
                P0=holding.P0,
                realized_profit=holding.realized_profit,
                base_profit_pool=holding.base_profit_pool,
                existing_base_shares=base_lot.shares if base_lot is not None else None,
                existing_base_price=base_lot.price if base_lot is not None else None,
            )

            new_lots: list[StoredLot] = []
            for lot in holding.lots:
                if lot.id == lot_id:
                    continue
                if base_lot is not None and lot.id == base_lot.id and calc.retain_shares > 0:
                    assert calc.new_base_shares is not None
                    assert calc.new_base_price is not None
                    new_lots.append(
                        StoredLot(
                            id=lot.id,
                            type="base",
                            price=calc.new_base_price,
                            shares=calc.new_base_shares,
                            filled_at=lot.filled_at,
                            note=lot.note,
                        )
                    )
                else:
                    new_lots.append(lot)

            if base_lot is None and calc.retain_shares > 0:
                assert calc.new_base_shares is not None
                assert calc.new_base_price is not None
                new_lots.insert(
                    0,
                    StoredLot(
                        id=str(uuid.uuid4()),
                        type="base",
                        price=calc.new_base_price,
                        shares=calc.new_base_shares,
                        filled_at=None,
                        note=None,
                    ),
                )

            updated = StoredHolding(
                symbol=holding.symbol,
                B=holding.B,
                initial_price=holding.initial_price,
                P0=holding.P0,
                a=holding.a,
                b=holding.b,
                c=holding.c,
                K=holding.K,
                realized_profit=calc.new_realized_profit,
                base_profit_pool=calc.new_base_profit_pool,
                atr_14_pct=holding.atr_14_pct,
                atr_50_pct=holding.atr_50_pct,
                atr_source=holding.atr_source,
                atr_date=holding.atr_date,
                lots=tuple(new_lots),
            )
            data[sym] = updated.to_dict()

            summary = SettlementSummary(
                lot_id=lot_id,
                exit_price=round_price(exit_price),
                realized_gain=calc.delta_pi,
                retain_shares=calc.retain_shares,
                sell_shares=calc.sell_shares,
                realized_profit=calc.new_realized_profit,
                base_profit_pool=calc.new_base_profit_pool,
            )
            return summary, updated

        return self._store.update(_mutate)
