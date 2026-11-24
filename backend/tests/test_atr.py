"""Tests for ATR_A_Basic and ATR_B_60bars golden cases."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.core.atr import OHLCBar, compute_wilder_atr, filter_closed_bars
from app.core.calendar import get_latest_closed_session
from app.core.errors import ValidationError

ET = ZoneInfo("America/New_York")

# Hardcoded directly from Quant_Zifang_Golden_Cases.xlsx -> ATR_A_Basic
ATR_A_RAW_BARS = [
    OHLCBar(date(2026, 10, 30), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 2), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 3), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 4), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 5), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 6), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 9), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 10), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 11), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 12), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 13), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 16), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 17), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 18), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 19), Decimal("102"), Decimal("100"), Decimal("101")),
    OHLCBar(date(2026, 11, 20), Decimal("105"), Decimal("101"), Decimal("104")),
    # Bar 17: intraday bar to be filtered out
    OHLCBar(date(2026, 11, 23), Decimal("120"), Decimal("90"), Decimal("115")),
]

# Hardcoded directly from Quant_Zifang_Golden_Cases.xlsx -> ATR_B_60bars
ATR_B_RAW_BARS = [
    OHLCBar(date(2026, 8, 28), Decimal("100.8"), Decimal("99.3"), Decimal("100")),
    OHLCBar(date(2026, 8, 31), Decimal("102.86"), Decimal("100.81"), Decimal("101.76")),
    OHLCBar(date(2026, 9, 1), Decimal("104.72"), Decimal("102.12"), Decimal("103.32")),
    OHLCBar(date(2026, 9, 2), Decimal("106.19"), Decimal("103.04"), Decimal("104.49")),
    OHLCBar(date(2026, 9, 3), Decimal("107.13"), Decimal("104.43"), Decimal("105.13")),
    OHLCBar(date(2026, 9, 4), Decimal("109.97"), Decimal("108.22"), Decimal("109.17")),
    OHLCBar(date(2026, 9, 8), Decimal("109.72"), Decimal("107.42"), Decimal("108.62")),
    OHLCBar(date(2026, 9, 9), Decimal("108.94"), Decimal("106.09"), Decimal("107.54")),
    OHLCBar(date(2026, 9, 10), Decimal("104.77"), Decimal("102.37"), Decimal("103.07")),
    OHLCBar(date(2026, 9, 11), Decimal("103.41"), Decimal("100.46"), Decimal("101.41")),
    OHLCBar(date(2026, 9, 14), Decimal("100.55"), Decimal("98.55"), Decimal("99.75")),
    OHLCBar(date(2026, 9, 15), Decimal("99.4"), Decimal("96.85"), Decimal("98.3")),
    OHLCBar(date(2026, 9, 16), Decimal("98.64"), Decimal("96.54"), Decimal("97.24")),
    OHLCBar(date(2026, 9, 17), Decimal("98.42"), Decimal("95.77"), Decimal("96.72")),
    OHLCBar(date(2026, 9, 18), Decimal("98.79"), Decimal("95.59"), Decimal("96.79")),
    OHLCBar(date(2026, 9, 21), Decimal("98.26"), Decimal("96.01"), Decimal("97.46")),
    OHLCBar(date(2026, 9, 22), Decimal("103.74"), Decimal("101.94"), Decimal("102.64")),
    OHLCBar(date(2026, 9, 23), Decimal("105.61"), Decimal("103.26"), Decimal("104.21")),
    OHLCBar(date(2026, 9, 24), Decimal("107.68"), Decimal("104.78"), Decimal("105.98")),
    OHLCBar(date(2026, 9, 25), Decimal("109.74"), Decimal("106.29"), Decimal("107.74")),
    OHLCBar(date(2026, 9, 28), Decimal("110.08"), Decimal("108.58"), Decimal("109.28")),
    OHLCBar(date(2026, 9, 29), Decimal("108.53"), Decimal("106.48"), Decimal("107.43")),
    OHLCBar(date(2026, 9, 30), Decimal("109.44"), Decimal("106.84"), Decimal("108.04")),
    OHLCBar(date(2026, 10, 1), Decimal("109.75"), Decimal("106.6"), Decimal("108.05")),
    OHLCBar(date(2026, 10, 2), Decimal("109.47"), Decimal("106.77"), Decimal("107.47")),
    OHLCBar(date(2026, 10, 5), Decimal("107.17"), Decimal("105.42"), Decimal("106.37")),
    OHLCBar(date(2026, 10, 6), Decimal("106"), Decimal("103.7"), Decimal("104.9")),
    OHLCBar(date(2026, 10, 7), Decimal("108.62"), Decimal("105.77"), Decimal("107.22")),
    OHLCBar(date(2026, 10, 8), Decimal("107.27"), Decimal("104.87"), Decimal("105.57")),
    OHLCBar(date(2026, 10, 9), Decimal("106.13"), Decimal("103.18"), Decimal("104.13")),
    OHLCBar(date(2026, 10, 12), Decimal("103.9"), Decimal("101.9"), Decimal("103.1")),
    OHLCBar(date(2026, 10, 13), Decimal("103.7"), Decimal("101.15"), Decimal("102.6")),
    OHLCBar(date(2026, 10, 14), Decimal("104.1"), Decimal("102"), Decimal("102.7")),
    OHLCBar(date(2026, 10, 15), Decimal("105.1"), Decimal("102.45"), Decimal("103.4")),
    OHLCBar(date(2026, 10, 16), Decimal("103.61"), Decimal("100.41"), Decimal("101.61")),
    OHLCBar(date(2026, 10, 19), Decimal("103.99"), Decimal("101.74"), Decimal("103.19")),
    OHLCBar(date(2026, 10, 20), Decimal("106.07"), Decimal("104.27"), Decimal("104.97")),
    OHLCBar(date(2026, 10, 21), Decimal("108.12"), Decimal("105.77"), Decimal("106.72")),
    OHLCBar(date(2026, 10, 22), Decimal("113.95"), Decimal("111.05"), Decimal("112.25")),
    OHLCBar(date(2026, 10, 23), Decimal("115.37"), Decimal("111.92"), Decimal("113.37")),
    OHLCBar(date(2026, 10, 26), Decimal("114.75"), Decimal("113.25"), Decimal("113.95")),
    OHLCBar(date(2026, 10, 27), Decimal("115.04"), Decimal("112.99"), Decimal("113.94")),
    OHLCBar(date(2026, 10, 28), Decimal("114.73"), Decimal("112.13"), Decimal("113.33")),
    OHLCBar(date(2026, 10, 29), Decimal("113.91"), Decimal("110.76"), Decimal("112.21")),
    OHLCBar(date(2026, 10, 30), Decimal("112.72"), Decimal("110.02"), Decimal("110.72")),
    OHLCBar(date(2026, 11, 2), Decimal("109.84"), Decimal("108.09"), Decimal("109.04")),
    OHLCBar(date(2026, 11, 3), Decimal("108.49"), Decimal("106.19"), Decimal("107.39")),
    OHLCBar(date(2026, 11, 4), Decimal("104.37"), Decimal("101.52"), Decimal("102.97")),
    OHLCBar(date(2026, 11, 5), Decimal("103.66"), Decimal("101.26"), Decimal("101.96")),
    OHLCBar(date(2026, 11, 6), Decimal("107.49"), Decimal("104.54"), Decimal("105.49")),
    OHLCBar(date(2026, 11, 9), Decimal("106.42"), Decimal("104.42"), Decimal("105.62")),
    OHLCBar(date(2026, 11, 10), Decimal("107.44"), Decimal("104.89"), Decimal("106.34")),
    OHLCBar(date(2026, 11, 11), Decimal("108.98"), Decimal("106.88"), Decimal("107.58")),
    OHLCBar(date(2026, 11, 12), Decimal("110.87"), Decimal("108.22"), Decimal("109.17")),
    OHLCBar(date(2026, 11, 13), Decimal("112.95"), Decimal("109.75"), Decimal("110.95")),
    OHLCBar(date(2026, 11, 16), Decimal("113.5"), Decimal("111.25"), Decimal("112.7")),
    OHLCBar(date(2026, 11, 17), Decimal("115.31"), Decimal("113.51"), Decimal("114.21")),
    OHLCBar(date(2026, 11, 18), Decimal("116.71"), Decimal("114.36"), Decimal("115.31")),
    OHLCBar(date(2026, 11, 19), Decimal("117.56"), Decimal("114.66"), Decimal("115.86")),
    OHLCBar(date(2026, 11, 20), Decimal("117.82"), Decimal("114.37"), Decimal("115.82")),
    # Bar 61: intraday bar to be filtered out
    OHLCBar(date(2026, 11, 23), Decimal("125.82"), Decimal("105.82"), Decimal("120.82")),
]

ATR_B_GT_ATR14 = [
    (date(2026, 9, 18), Decimal("3.106428571428571")),
    (date(2026, 9, 21), Decimal("3.045255102040816")),
    (date(2026, 9, 22), Decimal("3.276308309037901")),
    (date(2026, 9, 23), Decimal("3.254429144106622")),
    (date(2026, 9, 24), Decimal("3.269827062384721")),
    (date(2026, 9, 25), Decimal("3.304839415071526")),
    (date(2026, 9, 28), Decimal("3.235922313994989")),
    (date(2026, 9, 29), Decimal("3.204785005852489")),
    (date(2026, 9, 30), Decimal("3.161586076863026")),
    (date(2026, 10, 1), Decimal("3.160758499944238")),
    (date(2026, 10, 2), Decimal("3.12784717851965")),
    (date(2026, 10, 5), Decimal("3.050858094339675")),
    (date(2026, 10, 6), Decimal("3.023653944743984")),
    (date(2026, 10, 7), Decimal("3.073392948690842")),
    (date(2026, 10, 8), Decimal("3.025293452355782")),
    (date(2026, 10, 9), Decimal("3.019915348616083")),
    (date(2026, 10, 12), Decimal("2.963492823714934")),
    (date(2026, 10, 13), Decimal("2.933957622021011")),
    (date(2026, 10, 14), Decimal("2.874389220448081")),
    (date(2026, 10, 15), Decimal("2.858361418987504")),
    (date(2026, 10, 16), Decimal("2.882764174774111")),
    (date(2026, 10, 19), Decimal("2.846852448004531")),
    (date(2026, 10, 20), Decimal("2.849220130289922")),
    (date(2026, 10, 21), Decimal("2.870704406697785")),
    (date(2026, 10, 22), Decimal("3.182082663362229")),
    (date(2026, 10, 23), Decimal("3.201219615979213")),
    (date(2026, 10, 26), Decimal("3.079703929123554")),
    (date(2026, 10, 27), Decimal("3.006153648471872")),
    (date(2026, 10, 28), Decimal("2.977142673581024")),
    (date(2026, 10, 29), Decimal("2.989489625468094")),
    (date(2026, 10, 30), Decimal("2.968811795077515")),
    (date(2026, 11, 2), Decimal("2.944610952571979")),
    (date(2026, 11, 3), Decimal("2.937853027388266")),
    (date(2026, 11, 4), Decimal("3.147292096860533")),
    (date(2026, 11, 5), Decimal("3.093914089941923")),
    (date(2026, 11, 6), Decimal("3.267920226374643")),
    (date(2026, 11, 9), Decimal("3.177354495919311")),
    (date(2026, 11, 10), Decimal("3.132543460496503")),
    (date(2026, 11, 11), Decimal("3.097361784746753")),
    (date(2026, 11, 12), Decimal("3.111121657264842")),
    (date(2026, 11, 13), Decimal("3.158898681745925")),
    (date(2026, 11, 16), Decimal("3.115405918764073")),
    (date(2026, 11, 17), Decimal("3.079305495995211")),
    (date(2026, 11, 18), Decimal("3.037926531995553")),
    (date(2026, 11, 19), Decimal("3.028074636853013")),
    (date(2026, 11, 20), Decimal("3.058212162792084")),
]

ATR_B_GT_ATR50 = [
    (date(2026, 11, 9), Decimal("3.094")),
    (date(2026, 11, 10), Decimal("3.08312")),
    (date(2026, 11, 11), Decimal("3.0742576")),
    (date(2026, 11, 12), Decimal("3.078572448")),
    (date(2026, 11, 13), Decimal("3.09260099904")),
    (date(2026, 11, 16), Decimal("3.0817489790592")),
    (date(2026, 11, 17), Decimal("3.072313999478016")),
    (date(2026, 11, 18), Decimal("3.060867719488455")),
    (date(2026, 11, 19), Decimal("3.057650365098687")),
    (date(2026, 11, 20), Decimal("3.065497357796713")),
]


def test_atr_a_basic_golden() -> None:
    mock_now = datetime(2026, 11, 23, 11, 0, tzinfo=ET)
    latest_session = get_latest_closed_session(mock_now)
    assert latest_session == date(2026, 11, 20)

    closed_bars = filter_closed_bars(ATR_A_RAW_BARS, latest_session)
    assert len(closed_bars) == 16
    assert closed_bars[-1].date == date(2026, 11, 20)
    assert closed_bars[-1].close == Decimal("104")

    res = compute_wilder_atr(closed_bars, 14)
    assert len(res.atr_series) == 2
    assert res.atr_series[0] == (date(2026, 11, 19), Decimal("2"))
    assert res.atr_series[1][0] == date(2026, 11, 20)
    assert abs(res.atr_series[1][1] - Decimal("2.142857142857143")) < Decimal("1e-14")

    assert res.atr_pct_rounded == Decimal("0.020604")
    assert str(res.atr_pct) == "0.02060439560439560439560439560439560439561"


def test_atr_b_60bars_golden() -> None:
    mock_now = datetime(2026, 11, 23, 11, 0, tzinfo=ET)
    latest_session = get_latest_closed_session(mock_now)
    assert latest_session == date(2026, 11, 20)

    closed_bars = filter_closed_bars(ATR_B_RAW_BARS, latest_session)
    assert len(closed_bars) == 60
    assert closed_bars[-1].date == date(2026, 11, 20)
    assert closed_bars[-1].close == Decimal("115.82")

    res14 = compute_wilder_atr(closed_bars, 14)
    assert len(res14.atr_series) == len(ATR_B_GT_ATR14)
    for (actual_date, actual_atr), (exp_date, exp_atr) in zip(res14.atr_series, ATR_B_GT_ATR14):
        assert actual_date == exp_date
        assert abs(actual_atr - exp_atr) < Decimal("1e-13")

    assert res14.atr_pct_rounded == Decimal("0.026405")
    assert str(res14.atr_pct) == "0.02640487103084168393664599047630160658344"

    res50 = compute_wilder_atr(closed_bars, 50)
    assert len(res50.atr_series) == len(ATR_B_GT_ATR50)
    for (actual_date, actual_atr), (exp_date, exp_atr) in zip(res50.atr_series, ATR_B_GT_ATR50):
        assert actual_date == exp_date
        assert abs(actual_atr - exp_atr) < Decimal("1e-13")

    assert res50.atr_pct_rounded == Decimal("0.026468")
    assert str(res50.atr_pct) == "0.02646777204106987424513900880676912450354"


def test_atr_insufficient_bars_raises() -> None:
    with pytest.raises(ValidationError):
        compute_wilder_atr(ATR_A_RAW_BARS[:14], 14)
