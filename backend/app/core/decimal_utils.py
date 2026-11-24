"""Decimal arithmetic configuration and banker's rounding helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Decimal,
    DefaultContext,
    InvalidOperation,
    getcontext,
    localcontext,
)

from app.core.errors import ValidationError

DECIMAL_PREC = 40

# Configure both current thread context and default context for worker threads.
getcontext().prec = DECIMAL_PREC
DefaultContext.prec = DECIMAL_PREC

PRICE_QUANT = Decimal("0.01")
TRAIL_PCT_QUANT = Decimal("0.0001")
RATIO_QUANT = Decimal("0.000001")
FLOOR_QUANT = Decimal("0.0000000001")
ZERO = Decimal("0")
ONE = Decimal("1")


@contextmanager
def decimal_context() -> Iterator[None]:
    """Ensure 40-digit Decimal precision in any thread."""
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PREC
        yield


def to_decimal(value: Decimal | int | str | float, field_name: str = "value") -> Decimal:
    """Convert an external number to a finite Decimal via string conversion for floats."""
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} 不可為布林值")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValidationError(f"{field_name} 不是合法數值: {value!r}") from exc
    elif isinstance(value, float):
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValidationError(f"{field_name} 不是合法數值: {value!r}") from exc
    else:
        raise ValidationError(f"{field_name} 型別不支援: {type(value).__name__}")

    if not result.is_finite():
        raise ValidationError(f"{field_name} 必須為有限數值")
    return result


def round_price(value: Decimal) -> Decimal:
    """Round price/amount to 2 decimal places using banker's rounding (ROUND_HALF_EVEN)."""
    with decimal_context():
        rounded = value.quantize(PRICE_QUANT, rounding=ROUND_HALF_EVEN)
        return Decimal("0.00") if rounded == ZERO else rounded


def round_ratio(value: Decimal) -> Decimal:
    """Round ratio/percentage to 6 decimal places using banker's rounding (ROUND_HALF_EVEN)."""
    with decimal_context():
        rounded = value.quantize(RATIO_QUANT, rounding=ROUND_HALF_EVEN)
        return Decimal("0.000000") if rounded == ZERO else rounded


def round_trail_pct(value: Decimal) -> Decimal:
    """Round trailing buffer ratio to 4 decimal places (0.01% = 2 pct decimals) via ROUND_HALF_EVEN."""
    with decimal_context():
        rounded = value.quantize(TRAIL_PCT_QUANT, rounding=ROUND_HALF_EVEN)
        return Decimal("0.0000") if rounded == ZERO else rounded


def floor_int(value: Decimal) -> int:
    """Quantize to 10 decimal places with ROUND_HALF_EVEN, then floor to int."""
    with decimal_context():
        quantized = value.quantize(FLOOR_QUANT, rounding=ROUND_HALF_EVEN)
        return int(quantized.to_integral_value(rounding=ROUND_FLOOR))


def fmt_price(value: Decimal) -> str:
    """Format a Decimal price/amount as a 2-decimal string."""
    return f"{round_price(value):.2f}"


def fmt_ratio(value: Decimal) -> str:
    """Format a Decimal ratio as a 6-decimal string."""
    return f"{round_ratio(value):.6f}"
