"""Pure bar filtering and Wilder ATR calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from app.core.decimal_utils import ZERO, decimal_context, round_ratio
from app.core.errors import ValidationError


@dataclass(frozen=True)
class OHLCBar:
    """Single daily OHLC bar using exact Decimal prices."""

    date: date
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class WilderATRResult:
    """Output of Wilder's ATR calculation."""

    period: int
    atr: Decimal
    atr_pct: Decimal
    atr_pct_rounded: Decimal
    atr_series: tuple[tuple[date, Decimal], ...]


def filter_closed_bars(bars: Sequence[OHLCBar], latest_session: date) -> list[OHLCBar]:
    """Keep only bars with date <= latest_session, sorted ascending by date."""
    closed = [bar for bar in bars if bar.date <= latest_session]
    closed.sort(key=lambda b: b.date)
    return closed


def compute_wilder_atr(bars: Sequence[OHLCBar], n: int) -> WilderATRResult:
    """Compute Wilder's original n-period ATR and ATR% on pre-filtered daily bars.

    Requires at least `n + 1` bars (1 bar for prior close + n TR values).
    TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|) for t = 1..len(bars)-1.
    First ATR (at bar index n) = simple average of first n TR values.
    Subsequent ATR_t = (ATR_{t-1} * (n - 1) + TR_t) / n.
    ATR% = latest ATR / latest close.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValidationError("ATR 期數 n 必須為正整數")
    if len(bars) < n + 1:
        raise ValidationError(f"K 棒數量不足，計算 ATR({n}) 至少需要 {n + 1} 根，實際僅 {len(bars)} 根")

    latest_close = bars[-1].close
    if latest_close <= ZERO:
        raise ValidationError("最新收盤價必須大於 0")

    with decimal_context():
        n_dec = Decimal(n)
        n_minus_1 = Decimal(n - 1)

        trs: list[tuple[date, Decimal]] = []
        for idx in range(1, len(bars)):
            curr = bars[idx]
            prev_close = bars[idx - 1].close
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev_close),
                abs(curr.low - prev_close),
            )
            trs.append((curr.date, tr))

        first_atr = sum((tr for _, tr in trs[:n]), ZERO) / n_dec
        atr = first_atr
        series: list[tuple[date, Decimal]] = [(trs[n - 1][0], atr)]

        for bar_date, tr in trs[n:]:
            atr = (atr * n_minus_1 + tr) / n_dec
            series.append((bar_date, atr))

        atr_pct = atr / latest_close
        atr_pct_rounded = round_ratio(atr_pct)

        return WilderATRResult(
            period=n,
            atr=atr,
            atr_pct=atr_pct,
            atr_pct_rounded=atr_pct_rounded,
            atr_series=tuple(series),
        )
