"""Common schema types and strict Decimal/int validators."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator


def _parse_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("不可為布林值")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"不是合法數值: {value!r}") from exc
    elif isinstance(value, float):
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"不是合法數值: {value!r}") from exc
    else:
        raise ValueError(f"不支援的數值型別: {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("必須為有限數值")
    return result


def _parse_strict_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("必須為整數")
    return value


DecimalInput = Annotated[Decimal, BeforeValidator(_parse_decimal)]
StrictIntInput = Annotated[int, BeforeValidator(_parse_strict_int)]


class WarningSchema(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
