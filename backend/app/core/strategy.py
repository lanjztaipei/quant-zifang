"""Pure VAG Grid strategy engine and settlement math (no I/O, no FastAPI)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.core.decimal_utils import (
    ONE,
    ZERO,
    decimal_context,
    floor_int,
    round_price,
    round_ratio,
)
from app.core.errors import ValidationError

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$")

HALF = Decimal("0.5")
MAX_GRID_LEVELS = 100

WARNING_MESSAGES: dict[str, str] = {
    "NO_POSITION": "目前無持股部位（底倉股數為 0），無法計算未來加碼網格。",
    "BUDGET_EXHAUSTED": "目前已投入資金已達或超過有效總預算，無法產生未來加碼網格。",
    "GRID_FULL": "已成交網格層數已達上限，無剩餘可掛單網格層數。",
}


@dataclass(frozen=True)
class WarningItem:
    code: str
    message: str


@dataclass(frozen=True)
class HoldingLotInput:
    type: Literal["base", "grid"]
    price: Decimal
    shares: int
    id: str | None = None
    filled_at: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class StrategyInput:
    symbol: str
    B: Decimal
    initial_price: Decimal
    atr_14_pct: Decimal
    atr_50_pct: Decimal
    P0: Decimal = Decimal("0.30")
    a: Decimal = Decimal("0.6")
    b: Decimal = Decimal("0.1")
    c: Decimal = Decimal("0.5")
    K: Decimal = Decimal("6")
    realized_profit: Decimal = ZERO
    base_profit_pool: Decimal = ZERO
    holdings: tuple[HoldingLotInput, ...] = field(default_factory=tuple)
    current_price: Decimal | None = None


@dataclass(frozen=True)
class ReverseBuyOrder:
    buy_trigger_price: Decimal
    buy_trail_pct: Decimal
    buy_max_price: Decimal
    shares: int


@dataclass(frozen=True)
class ComputedLot:
    id: str | None
    type: Literal["base", "grid"]
    price: Decimal
    shares: int
    filled_at: str | None
    note: str | None
    tp: Decimal | None
    tp_trail_pct: Decimal | None
    tp_reached: bool | None
    expected_profit: Decimal | None
    proj_base_pool: Decimal | None
    retain_shares: int
    sell_shares: int
    reverse_buy: ReverseBuyOrder | None


@dataclass(frozen=True)
class ReverseSellOrder:
    sell_trigger_price: Decimal
    sell_trail_pct: Decimal
    expected_profit: Decimal
    proj_base_pool: Decimal
    retain_shares: int
    sell_shares: int


@dataclass(frozen=True)
class FutureGridLevel:
    j: int
    P_j: Decimal
    buy_trail_pct: Decimal
    P_j_max: Decimal
    Q_j: int
    cum_invest: Decimal
    TP_j: Decimal
    breached: bool | None
    reverse_sell: ReverseSellOrder


@dataclass(frozen=True)
class StrategyParamsSummary:
    atr_eff_pct: Decimal
    x: Decimal
    y: Decimal
    z: Decimal
    N: int
    N_rem: int
    max_safe_drop: Decimal


@dataclass(frozen=True)
class StrategyDashboard:
    total_shares: int
    base_shares: int
    grid_shares: int
    avg_cost: Decimal | None
    B: Decimal
    realized_profit: Decimal
    B_eff: Decimal
    base_profit_pool: Decimal
    C_now: Decimal
    remaining_cash: Decimal
    utilization: Decimal
    remaining_cover: Decimal
    P_anchor: Decimal | None
    warnings: tuple[WarningItem, ...]


@dataclass(frozen=True)
class StrategyResult:
    symbol: str
    mode: Literal["new", "rebalance"]
    Q0: int | None
    m: int
    r_new: Decimal | None
    params_summary: StrategyParamsSummary
    dashboard: StrategyDashboard
    holdings: tuple[ComputedLot, ...]
    future_grid: tuple[FutureGridLevel, ...]


@dataclass(frozen=True)
class SettlementCalculation:
    delta_pi: Decimal
    retain_shares: int
    sell_shares: int
    new_realized_profit: Decimal
    new_base_profit_pool: Decimal
    new_base_shares: int | None
    new_base_price: Decimal | None


def validate_symbol(symbol: str) -> str:
    """Normalize symbol to uppercase and validate against ^[A-Z0-9.\\-]{1,10}$."""
    if not isinstance(symbol, str):
        raise ValidationError("symbol 必須為字串")
    normalized = symbol.upper()
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ValidationError("symbol 格式不合法，須符合 ^[A-Z0-9.\\-]{1,10}$")
    return normalized


def _ensure_finite(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError(f"{name} 必須為有限數值")


def validate_core_params(
    *,
    B: Decimal,
    initial_price: Decimal,
    P0: Decimal,
    a: Decimal,
    b: Decimal,
    c: Decimal,
    K: Decimal,
    realized_profit: Decimal,
    base_profit_pool: Decimal,
) -> int:
    """Validate strategy parameters (excluding ATR) and return N = max(1, floor(K/a))."""
    for val, name in (
        (B, "B"),
        (initial_price, "initial_price"),
        (P0, "P0"),
        (a, "a"),
        (b, "b"),
        (c, "c"),
        (K, "K"),
        (realized_profit, "realized_profit"),
        (base_profit_pool, "base_profit_pool"),
    ):
        _ensure_finite(val, name)

    if B <= ZERO:
        raise ValidationError("B 必須大於 0")
    if initial_price <= ZERO:
        raise ValidationError("initial_price 必須大於 0")
    if P0 <= ZERO or P0 > ONE:
        raise ValidationError("P0 必須介於 (0, 1]")
    if a <= ZERO:
        raise ValidationError("a 必須大於 0")
    if b < ZERO:
        raise ValidationError("b 必須大於或等於 0")
    if c <= ZERO:
        raise ValidationError("c 必須大於 0")
    if K <= ZERO:
        raise ValidationError("K 必須大於 0")
    if realized_profit < ZERO:
        raise ValidationError("realized_profit 必須大於或等於 0")
    if base_profit_pool < ZERO:
        raise ValidationError("base_profit_pool 必須大於或等於 0")

    with decimal_context():
        raw_n = floor_int(K / a)
    if raw_n > MAX_GRID_LEVELS:
        raise ValidationError(f"⌊K/a⌋ = {raw_n} 不可超過 {MAX_GRID_LEVELS}")
    return max(1, raw_n)


def validate_atr_params(
    *,
    atr_14_pct: Decimal,
    atr_50_pct: Decimal,
    a: Decimal,
) -> tuple[Decimal, Decimal]:
    """Validate ATR percentages and x = a * max(atr_50_pct, atr_14_pct) < 1."""
    _ensure_finite(atr_14_pct, "atr_14_pct")
    _ensure_finite(atr_50_pct, "atr_50_pct")
    _ensure_finite(a, "a")

    if atr_14_pct <= ZERO or atr_14_pct >= ONE:
        raise ValidationError("atr_14_pct 必須介於 (0, 1)")
    if atr_50_pct <= ZERO or atr_50_pct >= ONE:
        raise ValidationError("atr_50_pct 必須介於 (0, 1)")

    with decimal_context():
        atr_eff = max(atr_50_pct, atr_14_pct)
        x = a * atr_eff
    if x >= ONE:
        raise ValidationError("單層網格間距 x = a × ATR_eff 必須小於 1")
    return atr_eff, x


def validate_lot_fields(lot_type: str, price: Decimal, shares: int) -> None:
    """Validate a single holding lot."""
    if lot_type not in ("base", "grid"):
        raise ValidationError("lot.type 只能為 'base' 或 'grid'")
    _ensure_finite(price, "lot.price")
    if price <= ZERO:
        raise ValidationError("lot.price 必須大於 0")
    if isinstance(shares, bool) or not isinstance(shares, int) or shares < 1:
        raise ValidationError("lot.shares 必須為 >= 1 的整數")


def validate_holdings_list(holdings: Sequence[HoldingLotInput]) -> None:
    """Validate all holdings lots and ensure at most one base lot."""
    base_count = 0
    for lot in holdings:
        validate_lot_fields(lot.type, lot.price, lot.shares)
        if lot.type == "base":
            base_count += 1
            if base_count > 1:
                raise ValidationError("holdings 中最多只能有一筆 type='base' 的底倉")


def compute_initial_base_shares(
    *,
    B: Decimal,
    realized_profit: Decimal,
    P0: Decimal,
    initial_price: Decimal,
) -> int:
    """Compute Q0 = floor((B + realized_profit) * P0 / initial_price)."""
    with decimal_context():
        b_eff = B + realized_profit
        return floor_int((b_eff * P0) / initial_price)


def compute_strategy(inp: StrategyInput) -> StrategyResult:
    """Execute the pure VAG Grid strategy calculation."""
    symbol = validate_symbol(inp.symbol)
    N = validate_core_params(
        B=inp.B,
        initial_price=inp.initial_price,
        P0=inp.P0,
        a=inp.a,
        b=inp.b,
        c=inp.c,
        K=inp.K,
        realized_profit=inp.realized_profit,
        base_profit_pool=inp.base_profit_pool,
    )
    atr_eff, x = validate_atr_params(
        atr_14_pct=inp.atr_14_pct,
        atr_50_pct=inp.atr_50_pct,
        a=inp.a,
    )
    if inp.current_price is not None:
        _ensure_finite(inp.current_price, "current_price")
        if inp.current_price <= ZERO:
            raise ValidationError("current_price 必須大於 0")
    validate_holdings_list(inp.holdings)

    with decimal_context():
        b_eff = inp.B + inp.realized_profit
        y = inp.b * inp.atr_14_pct
        z = inp.c * inp.atr_14_pct
        y_rounded = round_ratio(y)

        # Mode and anchor
        if len(inp.holdings) == 0:
            mode: Literal["new", "rebalance"] = "new"
            q0 = floor_int((b_eff * inp.P0) / inp.initial_price)
            c_now = Decimal(q0) * inp.initial_price
            p_anchor: Decimal | None = inp.initial_price if q0 > 0 else None
            m = 0
            effective_lots: list[HoldingLotInput] = (
                [
                    HoldingLotInput(
                        id=None,
                        type="base",
                        price=inp.initial_price,
                        shares=q0,
                        filled_at=None,
                        note=None,
                    )
                ]
                if q0 > 0
                else []
            )
        else:
            mode = "rebalance"
            q0 = None
            c_now = sum((lot.price * Decimal(lot.shares) for lot in inp.holdings), ZERO)
            p_anchor = min(lot.price for lot in inp.holdings)
            m = sum(1 for lot in inp.holdings if lot.type == "grid")
            effective_lots = list(inp.holdings)

        # Computed lots (parent TP sell order + reverse buy child order)
        computed_lots: list[ComputedLot] = []
        base_shares = 0
        grid_shares = 0
        for lot in effective_lots:
            if lot.type == "base":
                base_shares += lot.shares
                computed_lots.append(
                    ComputedLot(
                        id=lot.id,
                        type="base",
                        price=round_price(lot.price),
                        shares=lot.shares,
                        filled_at=lot.filled_at,
                        note=lot.note,
                        tp=None,
                        tp_trail_pct=None,
                        tp_reached=None,
                        expected_profit=None,
                        proj_base_pool=None,
                        retain_shares=0,
                        sell_shares=0,
                        reverse_buy=None,
                    )
                )
            else:
                grid_shares += lot.shares
                tp = round_price(lot.price * (ONE + z))
                tp_reached = (inp.current_price >= tp) if inp.current_price is not None else None
                delta_pi_lot = Decimal(lot.shares) * (tp - lot.price)
                pool_proj = inp.base_profit_pool + delta_pi_lot * inp.P0
                retain_shares = (
                    min(lot.shares, max(0, floor_int(pool_proj / tp))) if tp > ZERO else 0
                )
                sell_shares = lot.shares - retain_shares
                buy_trigger = round_price(tp * (ONE - x))
                buy_max = round_price(buy_trigger * (ONE + y))
                computed_lots.append(
                    ComputedLot(
                        id=lot.id,
                        type="grid",
                        price=round_price(lot.price),
                        shares=lot.shares,
                        filled_at=lot.filled_at,
                        note=lot.note,
                        tp=tp,
                        tp_trail_pct=y_rounded,
                        tp_reached=tp_reached,
                        expected_profit=round_price(delta_pi_lot),
                        proj_base_pool=round_price(pool_proj),
                        retain_shares=retain_shares,
                        sell_shares=sell_shares,
                        reverse_buy=ReverseBuyOrder(
                            buy_trigger_price=buy_trigger,
                            buy_trail_pct=y_rounded,
                            buy_max_price=buy_max,
                            shares=sell_shares,
                        ),
                    )
                )

        total_shares = base_shares + grid_shares
        avg_cost = round_price(c_now / Decimal(total_shares)) if total_shares > 0 else None

        # Boundary checks & warnings in required order:
        # NO_POSITION, BUDGET_EXHAUSTED, GRID_FULL
        n_rem = N - m
        warnings: list[WarningItem] = []
        if c_now <= ZERO:
            warnings.append(
                WarningItem(code="NO_POSITION", message=WARNING_MESSAGES["NO_POSITION"])
            )
        if c_now >= b_eff:
            warnings.append(
                WarningItem(
                    code="BUDGET_EXHAUSTED",
                    message=WARNING_MESSAGES["BUDGET_EXHAUSTED"],
                )
            )
        if n_rem <= 0:
            warnings.append(WarningItem(code="GRID_FULL", message=WARNING_MESSAGES["GRID_FULL"]))

        # Future grid levels
        future_grid: list[FutureGridLevel] = []
        r_new: Decimal | None = None
        if not warnings:
            assert p_anchor is not None
            r_new = (b_eff / c_now) ** (ONE / Decimal(n_rem)) - ONE
            cum_e = ZERO
            one_minus_x = ONE - x
            one_plus_y = ONE + y
            one_plus_half_y = ONE + HALF * y
            one_plus_z = ONE + z
            one_plus_r = ONE + r_new

            for j in range(1, n_rem + 1):
                p_j = round_price(p_anchor * (one_minus_x**j))
                p_j_max = round_price(p_j * one_plus_y)
                c_theo_j = b_eff if j == n_rem else c_now * (one_plus_r**j)
                budget_j = c_theo_j - (c_now + cum_e)
                denom = p_j * one_plus_y
                q_j = max(0, floor_int(budget_j / denom)) if denom > ZERO else 0
                e_j = Decimal(q_j) * p_j * one_plus_half_y
                cum_e += e_j
                cum_invest = round_price(c_now + cum_e)
                tp_j = round_price(p_j * one_plus_z)
                delta_pi_j = Decimal(q_j) * (tp_j - p_j)
                pool_proj_j = inp.base_profit_pool + delta_pi_j * inp.P0
                retain_j = min(q_j, max(0, floor_int(pool_proj_j / tp_j))) if tp_j > ZERO else 0
                sell_j = q_j - retain_j
                breached = (inp.current_price <= p_j) if inp.current_price is not None else None
                future_grid.append(
                    FutureGridLevel(
                        j=j,
                        P_j=p_j,
                        buy_trail_pct=y_rounded,
                        P_j_max=p_j_max,
                        Q_j=q_j,
                        cum_invest=cum_invest,
                        TP_j=tp_j,
                        breached=breached,
                        reverse_sell=ReverseSellOrder(
                            sell_trigger_price=tp_j,
                            sell_trail_pct=y_rounded,
                            expected_profit=round_price(delta_pi_j),
                            proj_base_pool=round_price(pool_proj_j),
                            retain_shares=retain_j,
                            sell_shares=sell_j,
                        ),
                    )
                )

        max_safe_drop = round_ratio(ONE - (ONE - x) ** N)
        remaining_cover = (
            Decimal("0.000000") if n_rem <= 0 else round_ratio(ONE - (ONE - x) ** n_rem)
        )

        params_summary = StrategyParamsSummary(
            atr_eff_pct=round_ratio(atr_eff),
            x=round_ratio(x),
            y=y_rounded,
            z=round_ratio(z),
            N=N,
            N_rem=n_rem,
            max_safe_drop=max_safe_drop,
        )
        dashboard = StrategyDashboard(
            total_shares=total_shares,
            base_shares=base_shares,
            grid_shares=grid_shares,
            avg_cost=avg_cost,
            B=round_price(inp.B),
            realized_profit=round_price(inp.realized_profit),
            B_eff=round_price(b_eff),
            base_profit_pool=round_price(inp.base_profit_pool),
            C_now=round_price(c_now),
            remaining_cash=round_price(b_eff - c_now),
            utilization=round_ratio(c_now / b_eff),
            remaining_cover=remaining_cover,
            P_anchor=round_price(p_anchor) if p_anchor is not None else None,
            warnings=tuple(warnings),
        )

        return StrategyResult(
            symbol=symbol,
            mode=mode,
            Q0=q0,
            m=m,
            r_new=r_new,
            params_summary=params_summary,
            dashboard=dashboard,
            holdings=tuple(computed_lots),
            future_grid=tuple(future_grid),
        )


def compute_settlement(
    *,
    lot_type: str,
    lot_price: Decimal,
    lot_shares: int,
    exit_price: Decimal,
    retain_shares: int | None,
    P0: Decimal,
    realized_profit: Decimal,
    base_profit_pool: Decimal,
    existing_base_shares: int | None,
    existing_base_price: Decimal | None,
) -> SettlementCalculation:
    """Pure settlement calculation for closing a grid lot at `exit_price`."""
    if lot_type != "grid":
        raise ValidationError("僅可對 type='grid' 的持股進行停利結算")
    _ensure_finite(exit_price, "exit_price")
    if exit_price <= lot_price:
        raise ValidationError("exit_price 必須大於該筆持股成交價")

    with decimal_context():
        q = lot_shares
        delta_pi = Decimal(q) * (exit_price - lot_price)
        pool_avail = base_profit_pool + delta_pi * P0

        if retain_shares is None:
            actual_retain = min(q, max(0, floor_int(pool_avail / exit_price)))
        else:
            if isinstance(retain_shares, bool) or not isinstance(retain_shares, int):
                raise ValidationError("retain_shares 必須為整數")
            if retain_shares < 0 or retain_shares > q:
                raise ValidationError(f"retain_shares 必須介於 0 與 {q} 之間")
            if Decimal(retain_shares) * exit_price > pool_avail:
                raise ValidationError("retain_shares × exit_price 超過可用底倉獲利池金額")
            actual_retain = retain_shares

        sell_shares = q - actual_retain
        new_realized_profit = round_price(realized_profit + delta_pi)
        new_base_profit_pool = round_price(pool_avail - Decimal(actual_retain) * exit_price)

        new_base_shares: int | None = existing_base_shares
        new_base_price: Decimal | None = existing_base_price
        if actual_retain > 0:
            if existing_base_shares is not None and existing_base_price is not None:
                total_base = existing_base_shares + actual_retain
                weighted_cost = (
                    Decimal(existing_base_shares) * existing_base_price
                    + Decimal(actual_retain) * exit_price
                )
                new_base_shares = total_base
                new_base_price = round_price(weighted_cost / Decimal(total_base))
            else:
                new_base_shares = actual_retain
                new_base_price = round_price(exit_price)

        return SettlementCalculation(
            delta_pi=round_price(delta_pi),
            retain_shares=actual_retain,
            sell_shares=sell_shares,
            new_realized_profit=new_realized_profit,
            new_base_profit_pool=new_base_profit_pool,
            new_base_shares=new_base_shares,
            new_base_price=new_base_price,
        )
