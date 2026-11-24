"""Golden case tests for StrategyEngine (GC-01..04, GC-05A/B/C/G, GC-06)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.core.decimal_utils import round_trail_pct
from app.core.errors import ValidationError
from app.core.strategy import HoldingLotInput, StrategyInput, compute_strategy


def test_gc01_new_position_n10() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="aapl",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("6"),
            atr_14_pct=Decimal("0.025"),
            atr_50_pct=Decimal("0.02"),
            realized_profit=Decimal("0"),
            base_profit_pool=Decimal("0"),
        )
    )

    assert res.symbol == "AAPL"
    assert res.mode == "new"
    assert res.Q0 == 30
    assert res.m == 0
    assert res.r_new is not None
    assert abs(res.r_new - Decimal("0.1279448730054994")) < Decimal("1e-14")

    ps = res.params_summary
    assert ps.atr_eff_pct == Decimal("0.025000")
    assert ps.x == Decimal("0.015000")
    assert ps.y == Decimal("0.002500")
    assert ps.z == Decimal("0.012500")
    assert ps.N == 10
    assert ps.N_rem == 10
    assert ps.max_safe_drop == Decimal("0.140270")

    db = res.dashboard
    assert db.B_eff == Decimal("10000.00")
    assert db.C_now == Decimal("3000.00")
    assert db.P_anchor == Decimal("100.00")
    assert db.total_shares == 30
    assert db.base_shares == 30
    assert db.grid_shares == 0
    assert db.avg_cost == Decimal("100.00")
    assert db.remaining_cash == Decimal("7000.00")
    assert db.utilization == Decimal("0.300000")
    assert db.remaining_cover == Decimal("0.140270")
    assert db.warnings == ()

    # Suggested base lot
    assert len(res.holdings) == 1
    lot0 = res.holdings[0]
    assert lot0.id is None
    assert lot0.type == "base"
    assert lot0.price == Decimal("100.00")
    assert lot0.shares == 30
    assert lot0.tp is None
    assert lot0.tp_trail_pct is None
    assert lot0.tp_reached is None
    assert lot0.expected_profit is None
    assert lot0.proj_base_pool is None
    assert lot0.retain_shares == 0
    assert lot0.sell_shares == 0
    assert lot0.reverse_buy is None

    # All 10 future grid levels: (j, P_j, P_j_max, Q_j, cum_invest, TP_j, retain_j, sell_j)
    expected_grid = [
        (1, Decimal("98.50"), Decimal("98.75"), 3, Decimal("3295.87"), Decimal("99.73"), 0, 3),
        (2, Decimal("97.02"), Decimal("97.26"), 5, Decimal("3781.58"), Decimal("98.23"), 0, 5),
        (3, Decimal("95.57"), Decimal("95.81"), 5, Decimal("4260.02"), Decimal("96.76"), 0, 5),
        (4, Decimal("94.13"), Decimal("94.37"), 6, Decimal("4825.51"), Decimal("95.31"), 0, 6),
        (5, Decimal("92.72"), Decimal("92.95"), 7, Decimal("5475.36"), Decimal("93.88"), 0, 7),
        (6, Decimal("91.33"), Decimal("91.56"), 7, Decimal("6115.47"), Decimal("92.47"), 0, 7),
        (7, Decimal("89.96"), Decimal("90.18"), 9, Decimal("6926.12"), Decimal("91.08"), 0, 9),
        (8, Decimal("88.61"), Decimal("88.83"), 10, Decimal("7813.33"), Decimal("89.72"), 0, 10),
        (9, Decimal("87.28"), Decimal("87.50"), 12, Decimal("8862.00"), Decimal("88.37"), 0, 12),
        (10, Decimal("85.97"), Decimal("86.18"), 13, Decimal("9981.01"), Decimal("87.04"), 0, 13),
    ]
    assert len(res.future_grid) == len(expected_grid)
    for lvl, exp in zip(res.future_grid, expected_grid, strict=True):
        j, p_j, p_j_max, q_j, cum, tp_j, ret_j, sell_j = exp
        assert lvl.j == j
        assert lvl.P_j == p_j
        assert lvl.buy_trail_pct == Decimal("0.002500")
        assert lvl.P_j_max == p_j_max
        assert lvl.Q_j == q_j
        assert lvl.cum_invest == cum
        assert lvl.TP_j == tp_j
        assert lvl.breached is None
        assert lvl.reverse_sell.sell_trigger_price == tp_j
        assert lvl.reverse_sell.sell_trail_pct == Decimal("0.002500")
        assert lvl.reverse_sell.retain_shares == ret_j
        assert lvl.reverse_sell.sell_shares == sell_j


def test_gc02_atr50_gt_atr14() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="MSFT",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
        )
    )

    assert res.mode == "new"
    assert res.Q0 == 30
    assert res.r_new is not None
    assert abs(res.r_new - Decimal("0.8257418583505537")) < Decimal("1e-14")

    ps = res.params_summary
    assert ps.atr_eff_pct == Decimal("0.050000")
    assert ps.x == Decimal("0.030000")
    assert ps.y == Decimal("0.004000")
    assert ps.z == Decimal("0.020000")
    assert ps.N == 2
    assert ps.N_rem == 2
    assert ps.max_safe_drop == Decimal("0.059100")

    db = res.dashboard
    assert db.C_now == Decimal("3000.00")
    assert db.remaining_cash == Decimal("7000.00")
    assert db.utilization == Decimal("0.300000")
    assert db.remaining_cover == Decimal("0.059100")
    assert db.warnings == ()

    expected_grid = [
        (1, Decimal("97.00"), Decimal("97.39"), 25, Decimal("5429.85"), Decimal("98.94"), 0, 25),
        (2, Decimal("94.09"), Decimal("94.47"), 48, Decimal("9955.20"), Decimal("95.97"), 0, 48),
    ]
    assert len(res.future_grid) == 2
    for lvl, exp in zip(res.future_grid, expected_grid, strict=True):
        j, p_j, p_j_max, q_j, cum, tp_j, ret_j, sell_j = exp
        assert lvl.j == j
        assert lvl.P_j == p_j
        assert lvl.P_j_max == p_j_max
        assert lvl.Q_j == q_j
        assert lvl.cum_invest == cum
        assert lvl.TP_j == tp_j
        assert lvl.reverse_sell.retain_shares == ret_j
        assert lvl.reverse_sell.sell_shares == sell_j


def test_gc03_high_price_q0_rollover() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="NVDA",
            B=Decimal("1000"),
            initial_price=Decimal("500"),
            P0=Decimal("0.9"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
        )
    )

    assert res.mode == "new"
    assert res.Q0 == 1
    assert res.r_new is not None
    assert abs(res.r_new - Decimal("0.414213562373095")) < Decimal("1e-14")

    db = res.dashboard
    assert db.C_now == Decimal("500.00")
    assert db.P_anchor == Decimal("500.00")
    assert db.total_shares == 1
    assert db.base_shares == 1
    assert db.grid_shares == 0
    assert db.avg_cost == Decimal("500.00")
    assert db.remaining_cash == Decimal("500.00")
    assert db.utilization == Decimal("0.500000")
    assert db.remaining_cover == Decimal("0.059100")
    assert db.warnings == ()

    expected_grid = [
        (1, Decimal("485.00"), Decimal("486.94"), 0, Decimal("500.00"), Decimal("494.70"), 0, 0),
        (2, Decimal("470.45"), Decimal("472.33"), 1, Decimal("971.39"), Decimal("479.86"), 0, 1),
    ]
    assert len(res.future_grid) == 2
    for lvl, exp in zip(res.future_grid, expected_grid, strict=True):
        j, p_j, p_j_max, q_j, cum, tp_j, ret_j, sell_j = exp
        assert lvl.j == j
        assert lvl.P_j == p_j
        assert lvl.P_j_max == p_j_max
        assert lvl.Q_j == q_j
        assert lvl.cum_invest == cum
        assert lvl.TP_j == tp_j
        assert lvl.reverse_sell.retain_shares == ret_j
        assert lvl.reverse_sell.sell_shares == sell_j


def test_gc04_rebalance_bankers_rounding_and_bidirectional_orders() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
            holdings=(
                HoldingLotInput(id="lot-1", type="base", price=Decimal("100"), shares=30),
                HoldingLotInput(id="lot-2", type="grid", price=Decimal("96.5"), shares=25),
            ),
            current_price=Decimal("98.43"),
        )
    )

    assert res.mode == "rebalance"
    assert res.Q0 is None
    assert res.m == 1
    assert res.params_summary.N == 2
    assert res.params_summary.N_rem == 1
    assert res.r_new is not None
    assert abs(res.r_new - Decimal("0.8475750577367206")) < Decimal("1e-14")

    db = res.dashboard
    assert db.C_now == Decimal("5412.50")
    assert db.P_anchor == Decimal("96.50")
    assert db.total_shares == 55
    assert db.base_shares == 30
    assert db.grid_shares == 25
    assert db.avg_cost == Decimal("98.41")
    assert db.remaining_cash == Decimal("4587.50")
    assert db.utilization == Decimal("0.541250")
    assert db.remaining_cover == Decimal("0.030000")
    assert db.warnings == ()

    # Holdings verification
    assert len(res.holdings) == 2
    base_lot, grid_lot = res.holdings
    assert base_lot.id == "lot-1"
    assert base_lot.tp is None
    assert base_lot.reverse_buy is None

    assert grid_lot.id == "lot-2"
    assert grid_lot.tp == Decimal("98.43")
    assert grid_lot.tp_trail_pct == Decimal("0.004000")
    assert grid_lot.tp_reached is True
    assert grid_lot.expected_profit == Decimal("48.25")
    assert grid_lot.proj_base_pool == Decimal("14.48")
    assert grid_lot.retain_shares == 0
    assert grid_lot.sell_shares == 25
    assert grid_lot.reverse_buy is not None
    assert grid_lot.reverse_buy.buy_trigger_price == Decimal("95.48")
    assert grid_lot.reverse_buy.buy_trail_pct == Decimal("0.004000")
    assert grid_lot.reverse_buy.buy_max_price == Decimal("95.86")
    assert grid_lot.reverse_buy.shares == 25

    # Future grid L1: 96.5 * 0.97 = 93.605 -> banker's rounding = 93.60
    assert len(res.future_grid) == 1
    lvl1 = res.future_grid[0]
    assert lvl1.j == 1
    assert lvl1.P_j == Decimal("93.60")
    assert lvl1.P_j_max == Decimal("93.97")
    assert lvl1.Q_j == 48
    assert lvl1.cum_invest == Decimal("9914.29")
    assert lvl1.TP_j == Decimal("95.47")
    assert lvl1.breached is False
    assert lvl1.reverse_sell.retain_shares == 0
    assert lvl1.reverse_sell.sell_shares == 48


def test_gc05a_no_position() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="NVDA",
            B=Decimal("100"),
            initial_price=Decimal("500"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("6"),
            atr_14_pct=Decimal("0.025"),
            atr_50_pct=Decimal("0.02"),
        )
    )
    assert res.mode == "new"
    assert res.Q0 == 0
    assert res.r_new is None
    assert res.holdings == ()
    assert res.future_grid == ()
    db = res.dashboard
    assert db.C_now == Decimal("0.00")
    assert db.P_anchor is None
    assert db.total_shares == 0
    assert db.avg_cost is None
    assert db.remaining_cash == Decimal("100.00")
    assert db.utilization == Decimal("0.000000")
    assert db.remaining_cover == Decimal("0.140270")
    assert [w.code for w in db.warnings] == ["NO_POSITION"]


def test_gc05b_budget_exhausted() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
            holdings=(HoldingLotInput(id="lot-1", type="base", price=Decimal("100"), shares=100),),
        )
    )
    assert res.mode == "rebalance"
    assert res.r_new is None
    assert res.future_grid == ()
    db = res.dashboard
    assert db.C_now == Decimal("10000.00")
    assert db.P_anchor == Decimal("100.00")
    assert db.total_shares == 100
    assert db.base_shares == 100
    assert db.grid_shares == 0
    assert db.avg_cost == Decimal("100.00")
    assert db.remaining_cash == Decimal("0.00")
    assert db.utilization == Decimal("1.000000")
    assert db.remaining_cover == Decimal("0.059100")
    assert [w.code for w in db.warnings] == ["BUDGET_EXHAUSTED"]


def test_gc05c_grid_full() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
            holdings=(
                HoldingLotInput(id="lot-1", type="base", price=Decimal("100"), shares=30),
                HoldingLotInput(id="lot-2", type="grid", price=Decimal("97"), shares=25),
                HoldingLotInput(id="lot-3", type="grid", price=Decimal("94.09"), shares=48),
            ),
        )
    )
    assert res.mode == "rebalance"
    assert res.m == 2
    assert res.params_summary.N_rem == 0
    assert res.r_new is None
    assert res.future_grid == ()

    db = res.dashboard
    assert db.C_now == Decimal("9941.32")
    assert db.P_anchor == Decimal("94.09")
    assert db.total_shares == 103
    assert db.base_shares == 30
    assert db.grid_shares == 73
    assert db.avg_cost == Decimal("96.52")
    assert db.remaining_cash == Decimal("58.68")
    assert db.utilization == Decimal("0.994132")
    assert db.remaining_cover == Decimal("0.000000")
    assert [w.code for w in db.warnings] == ["GRID_FULL"]

    lot1, lot2, lot3 = res.holdings
    assert lot1.tp is None
    assert lot2.tp == Decimal("98.94")
    assert lot2.retain_shares == 0
    assert lot2.sell_shares == 25
    assert lot2.reverse_buy is not None
    assert lot2.reverse_buy.buy_trigger_price == Decimal("95.97")
    assert lot2.reverse_buy.buy_max_price == Decimal("96.35")
    assert lot2.reverse_buy.shares == 25

    assert lot3.tp == Decimal("95.97")
    assert lot3.retain_shares == 0
    assert lot3.sell_shares == 48
    assert lot3.reverse_buy is not None
    assert lot3.reverse_buy.buy_trigger_price == Decimal("93.09")
    assert lot3.reverse_buy.buy_max_price == Decimal("93.46")
    assert lot3.reverse_buy.shares == 48


def test_gc05g_budget_exhausted_and_grid_full() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
            holdings=(
                HoldingLotInput(id="lot-1", type="base", price=Decimal("100"), shares=30),
                HoldingLotInput(id="lot-2", type="grid", price=Decimal("97"), shares=25),
                HoldingLotInput(id="lot-3", type="grid", price=Decimal("94.09"), shares=60),
            ),
        )
    )
    assert res.future_grid == ()
    db = res.dashboard
    assert db.C_now == Decimal("11070.40")
    assert db.P_anchor == Decimal("94.09")
    assert db.total_shares == 115
    assert db.base_shares == 30
    assert db.grid_shares == 85
    assert db.avg_cost == Decimal("96.26")
    assert db.remaining_cash == Decimal("-1070.40")
    assert db.utilization == Decimal("1.107040")
    assert db.remaining_cover == Decimal("0.000000")
    assert [w.code for w in db.warnings] == ["BUDGET_EXHAUSTED", "GRID_FULL"]

    lot3 = res.holdings[2]
    assert lot3.tp == Decimal("95.97")
    assert lot3.sell_shares == 60
    assert lot3.reverse_buy is not None
    assert lot3.reverse_buy.buy_trigger_price == Decimal("93.09")
    assert lot3.reverse_buy.buy_max_price == Decimal("93.46")
    assert lot3.reverse_buy.shares == 60


def test_gc06_profit_rollover_and_retain_shares() -> None:
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("10000"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.04"),
            atr_50_pct=Decimal("0.05"),
            realized_profit=Decimal("500"),
            base_profit_pool=Decimal("90"),
            holdings=(
                HoldingLotInput(id="lot-1", type="base", price=Decimal("100"), shares=30),
                HoldingLotInput(id="lot-2", type="grid", price=Decimal("96.5"), shares=25),
            ),
            current_price=Decimal("93.60"),
        )
    )

    assert res.mode == "rebalance"
    assert res.r_new is not None
    assert abs(res.r_new - Decimal("0.9399538106235565")) < Decimal("1e-14")

    db = res.dashboard
    assert db.B_eff == Decimal("10500.00")
    assert db.C_now == Decimal("5412.50")
    assert db.P_anchor == Decimal("96.50")
    assert db.total_shares == 55
    assert db.base_shares == 30
    assert db.grid_shares == 25
    assert db.avg_cost == Decimal("98.41")
    assert db.remaining_cash == Decimal("5087.50")
    assert db.utilization == Decimal("0.515476")
    assert db.remaining_cover == Decimal("0.030000")
    assert db.warnings == ()

    lot2 = res.holdings[1]
    assert lot2.tp == Decimal("98.43")
    assert lot2.tp_reached is False
    assert lot2.retain_shares == 1
    assert lot2.sell_shares == 24
    assert lot2.reverse_buy is not None
    assert lot2.reverse_buy.buy_trigger_price == Decimal("95.48")
    assert lot2.reverse_buy.buy_max_price == Decimal("95.86")
    assert lot2.reverse_buy.shares == 24

    assert len(res.future_grid) == 1
    lvl1 = res.future_grid[0]
    assert lvl1.j == 1
    assert lvl1.P_j == Decimal("93.60")
    assert lvl1.P_j_max == Decimal("93.97")
    assert lvl1.Q_j == 54
    assert lvl1.cum_invest == Decimal("10477.01")
    assert lvl1.TP_j == Decimal("95.47")
    assert lvl1.breached is True
    assert lvl1.reverse_sell.retain_shares == 1
    assert lvl1.reverse_sell.sell_shares == 53


@pytest.mark.parametrize(
    "kwargs",
    [
        {"symbol": "INVALID SYMBOL!"},
        {"symbol": "TOOLONGSYMBOL1"},
        {"B": Decimal("0")},
        {"initial_price": Decimal("-1")},
        {"P0": Decimal("0")},
        {"P0": Decimal("1.01")},
        {"a": Decimal("0")},
        {"b": Decimal("-0.01")},
        {"c": Decimal("0")},
        {"K": Decimal("0")},
        {"realized_profit": Decimal("-1")},
        {"base_profit_pool": Decimal("-0.01")},
        {"atr_14_pct": Decimal("0")},
        {"atr_14_pct": Decimal("1")},
        {"atr_50_pct": Decimal("0")},
        {"atr_50_pct": Decimal("1")},
        {"current_price": Decimal("0")},
        {
            "holdings": (
                HoldingLotInput(type="base", price=Decimal("100"), shares=10),
                HoldingLotInput(type="base", price=Decimal("95"), shares=5),
            )
        },
        {"holdings": (HoldingLotInput(type="grid", price=Decimal("100"), shares=0),)},
    ],
)
def test_strategy_validation_rejects_invalid_inputs(kwargs: dict[str, Any]) -> None:
    base: dict[str, Any] = {
        "symbol": "AAPL",
        "B": Decimal("10000"),
        "initial_price": Decimal("100"),
        "P0": Decimal("0.3"),
        "a": Decimal("0.6"),
        "b": Decimal("0.1"),
        "c": Decimal("0.5"),
        "K": Decimal("6"),
        "atr_14_pct": Decimal("0.025"),
        "atr_50_pct": Decimal("0.02"),
    }
    base.update(kwargs)
    with pytest.raises(ValidationError):
        compute_strategy(StrategyInput(**base))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (Decimal("0.002567"), Decimal("0.0026")),
        (Decimal("0.002549"), Decimal("0.0025")),
        (Decimal("0.00255"), Decimal("0.0026")),  # banker's rounding -> even
        (Decimal("0.00245"), Decimal("0.0024")),  # banker's rounding -> even
        (Decimal("0.00004"), Decimal("0.0000")),
        (Decimal("0"), Decimal("0.0000")),
    ],
)
def test_round_trail_pct_bankers_rounding(raw: Decimal, expected: Decimal) -> None:
    assert round_trail_pct(raw) == expected


def test_trail_buffer_y_rounded_before_downstream_calculations() -> None:
    # b * atr_14_pct = 0.1 * 0.0255 = 0.00255 -> banker's rounding to 0.0026 (0.26%)
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("100000"),
            initial_price=Decimal("1000"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.0255"),
            atr_50_pct=Decimal("0.05"),
            holdings=(
                HoldingLotInput(id="lot-1", type="base", price=Decimal("1000"), shares=30),
                HoldingLotInput(id="lot-2", type="grid", price=Decimal("970"), shares=25),
            ),
        )
    )

    assert res.params_summary.y == Decimal("0.002600")

    grid_lot = res.holdings[1]
    assert grid_lot.tp == Decimal("982.37")
    assert grid_lot.tp_trail_pct == Decimal("0.002600")
    assert grid_lot.reverse_buy is not None
    assert grid_lot.reverse_buy.buy_trigger_price == Decimal("952.90")
    assert grid_lot.reverse_buy.buy_trail_pct == Decimal("0.002600")
    # 952.90 * (1 + 0.0026) = 955.37754 -> 955.38 (raw 0.00255 would give 955.33)
    assert grid_lot.reverse_buy.buy_max_price == Decimal("955.38")

    assert len(res.future_grid) == 1
    lvl1 = res.future_grid[0]
    assert lvl1.P_j == Decimal("940.90")
    assert lvl1.buy_trail_pct == Decimal("0.002600")
    # 940.90 * (1 + 0.0026) = 943.34634 -> 943.35 (raw 0.00255 would give 943.30)
    assert lvl1.P_j_max == Decimal("943.35")
    assert lvl1.Q_j == 48
    # 54250 + 48 * 940.90 * (1 + 0.0013) = 99471.91216 -> 99471.91 (raw 0.00255 would give 99470.78)
    assert lvl1.cum_invest == Decimal("99471.91")
    assert lvl1.reverse_sell.sell_trail_pct == Decimal("0.002600")


def test_trail_buffer_y_rounded_affects_q_j_denominator() -> None:
    # Budget_1 = 2072.50 - 1100 = 972.50, P_1 = 97.00
    # With raw y=0.00255: 972.50 / (97 * 1.00255) = 10.00027 -> Q_1 = 10
    # With rounded y=0.0026: 972.50 / (97 * 1.0026) = 9.99977 -> Q_1 = 9
    res = compute_strategy(
        StrategyInput(
            symbol="AAPL",
            B=Decimal("2072.50"),
            initial_price=Decimal("100"),
            P0=Decimal("0.3"),
            a=Decimal("0.6"),
            b=Decimal("0.1"),
            c=Decimal("0.5"),
            K=Decimal("1.2"),
            atr_14_pct=Decimal("0.0255"),
            atr_50_pct=Decimal("0.05"),
            holdings=(
                HoldingLotInput(id="lot-1", type="base", price=Decimal("100"), shares=10),
                HoldingLotInput(id="lot-2", type="grid", price=Decimal("100"), shares=1),
            ),
        )
    )

    assert res.params_summary.y == Decimal("0.002600")
    assert len(res.future_grid) == 1
    assert res.future_grid[0].Q_j == 9
