"""Tests for API_Guards (GC-05D..N), calculator HTTP formatting, holdings CRUD, and CORS."""

from __future__ import annotations

from pathlib import Path


def test_gc05d_levels_exceed_100_returns_422(make_client) -> None:
    client = make_client()
    resp = client.post(
        "/api/v1/calculator/compute",
        json={
            "symbol": "AAPL",
            "B": 10000,
            "initial_price": 100,
            "P0": 0.3,
            "a": 0.05,
            "b": 0.1,
            "c": 0.5,
            "K": 6,
            "atr_14_pct": 0.025,
            "atr_50_pct": 0.02,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_gc05e_step_x_ge_1_returns_422(make_client) -> None:
    client = make_client()
    resp = client.post(
        "/api/v1/calculator/compute",
        json={
            "symbol": "AAPL",
            "B": 10000,
            "initial_price": 100,
            "P0": 0.3,
            "a": 2.0,
            "b": 0.1,
            "c": 0.5,
            "K": 6,
            "atr_14_pct": 0.6,
            "atr_50_pct": 0.02,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_calculator_compute_outputs_decimal_strings_gc01(make_client) -> None:
    client = make_client()
    resp = client.post(
        "/api/v1/calculator/compute",
        json={
            "symbol": "aapl",
            "B": "10000",
            "initial_price": "100",
            "P0": "0.3",
            "a": "0.6",
            "b": "0.1",
            "c": "0.5",
            "K": "6",
            "atr_14_pct": "0.025",
            "atr_50_pct": "0.02",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["mode"] == "new"
    assert body["params_summary"] == {
        "atr_eff_pct": "0.025000",
        "x": "0.015000",
        "y": "0.002500",
        "z": "0.012500",
        "N": 10,
        "N_rem": 10,
        "max_safe_drop": "0.140270",
    }
    assert body["dashboard"]["C_now"] == "3000.00"
    assert body["dashboard"]["remaining_cash"] == "7000.00"
    assert body["dashboard"]["utilization"] == "0.300000"
    assert body["dashboard"]["remaining_cover"] == "0.140270"
    assert body["dashboard"]["avg_cost"] == "100.00"
    assert body["future_grid"][0]["P_j"] == "98.50"
    assert body["future_grid"][0]["P_j_max"] == "98.75"
    assert body["future_grid"][0]["cum_invest"] == "3295.87"
    assert body["future_grid"][9]["cum_invest"] == "9981.01"


def test_calculator_compute_rounds_trail_buffer_y_to_two_pct_decimals(make_client) -> None:
    client = make_client()
    resp = client.post(
        "/api/v1/calculator/compute",
        json={
            "symbol": "AAPL",
            "B": "100000",
            "initial_price": "1000",
            "P0": "0.3",
            "a": "0.6",
            "b": "0.1",
            "c": "0.5",
            "K": "1.2",
            "atr_14_pct": "0.02567",
            "atr_50_pct": "0.05",
            "holdings": [
                {"id": "lot-1", "type": "base", "price": "1000", "shares": 30},
                {"id": "lot-2", "type": "grid", "price": "970", "shares": 25},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # 0.1 * 0.02567 = 0.002567 (0.2567%) -> 0.0026 (0.26%), formatted to 6 decimals
    assert body["params_summary"]["y"] == "0.002600"
    assert body["holdings"][1]["tp_trail_pct"] == "0.002600"
    assert body["holdings"][1]["reverse_buy"]["buy_trail_pct"] == "0.002600"
    assert body["future_grid"][0]["buy_trail_pct"] == "0.002600"
    assert body["future_grid"][0]["reverse_sell"]["sell_trail_pct"] == "0.002600"
    assert body["future_grid"][0]["P_j_max"] == "943.35"


def test_gc05f_gc05h_gc05i_gc05j_gc05k_holdings_lifecycle(tmp_path: Path, make_client) -> None:
    client = make_client()

    # GC-05H: PUT /holdings/AAPL (no lots yet) -> auto-creates base lot 30 @ 100.00
    resp_h = client.put(
        "/api/v1/holdings/AAPL",
        json={
            "B": 10000,
            "initial_price": 100,
            "P0": 0.3,
            "a": 0.6,
            "b": 0.1,
            "c": 0.5,
            "K": 6,
        },
    )
    assert resp_h.status_code == 200
    body_h = resp_h.json()
    assert body_h["symbol"] == "AAPL"
    assert len(body_h["lots"]) == 1
    base_lot = body_h["lots"][0]
    assert base_lot["type"] == "base"
    assert base_lot["price"] == "100.00"
    assert base_lot["shares"] == 30
    assert base_lot["id"]

    # GC-05F: POST /holdings/AAPL/lots adding second base lot -> 409 BASE_LOT_EXISTS & file untouched
    holdings_file = tmp_path / "holdings.json"
    before_text = holdings_file.read_text(encoding="utf-8")
    resp_f = client.post(
        "/api/v1/holdings/AAPL/lots",
        json={"type": "base", "price": 95, "shares": 10},
    )
    assert resp_f.status_code == 409
    assert resp_f.json()["code"] == "BASE_LOT_EXISTS"
    assert holdings_file.read_text(encoding="utf-8") == before_text

    # GC-05I: PUT /holdings/AAPL changing initial_price to 90 -> existing base lot untouched
    resp_i = client.put(
        "/api/v1/holdings/AAPL",
        json={
            "B": 10000,
            "initial_price": 90,
            "P0": 0.3,
            "a": 0.6,
            "b": 0.1,
            "c": 0.5,
            "K": 6,
        },
    )
    assert resp_i.status_code == 200
    body_i = resp_i.json()
    assert body_i["initial_price"] == "90.00"
    assert len(body_i["lots"]) == 1
    assert body_i["lots"][0]["price"] == "100.00"
    assert body_i["lots"][0]["shares"] == 30

    # GC-05J: PUT /holdings/NVDA with Q0=0 -> lots == []
    resp_j = client.put(
        "/api/v1/holdings/NVDA",
        json={
            "B": 100,
            "initial_price": 500,
            "P0": 0.3,
            "a": 0.6,
            "b": 0.1,
            "c": 0.5,
            "K": 6,
        },
    )
    assert resp_j.status_code == 200
    assert resp_j.json()["lots"] == []

    # GET /holdings lists both AAPL and NVDA
    resp_list = client.get("/api/v1/holdings")
    assert resp_list.status_code == 200
    assert resp_list.json() == {"symbols": ["AAPL", "NVDA"]}

    # GC-05K: DELETE all lots of AAPL, then PUT /holdings/AAPL -> re-creates base lot 30 @ 100.00
    del_lot = client.delete(f"/api/v1/holdings/AAPL/lots/{base_lot['id']}")
    assert del_lot.status_code == 200
    assert del_lot.json()["lots"] == []

    resp_k = client.put(
        "/api/v1/holdings/AAPL",
        json={"B": 10000, "initial_price": 100, "P0": 0.3},
    )
    assert resp_k.status_code == 200
    body_k = resp_k.json()
    assert len(body_k["lots"]) == 1
    assert body_k["lots"][0]["type"] == "base"
    assert body_k["lots"][0]["price"] == "100.00"
    assert body_k["lots"][0]["shares"] == 30

    # DELETE /holdings/NVDA
    resp_del_sym = client.delete("/api/v1/holdings/NVDA")
    assert resp_del_sym.status_code == 200
    assert resp_del_sym.json() == {"deleted": True, "symbol": "NVDA"}
    assert client.get("/api/v1/holdings").json() == {"symbols": ["AAPL"]}


def test_gc05l_not_found_404(make_client) -> None:
    client = make_client()

    # Nonexistent symbol
    assert client.get("/api/v1/holdings/MISSING").status_code == 404
    assert client.get("/api/v1/holdings/MISSING").json()["code"] == "NOT_FOUND"
    assert client.delete("/api/v1/holdings/MISSING").status_code == 404
    assert (
        client.post(
            "/api/v1/holdings/MISSING/lots",
            json={"type": "grid", "price": 90, "shares": 5},
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/api/v1/holdings/MISSING/lots/fake-id",
            json={"type": "grid", "price": 90, "shares": 5},
        ).status_code
        == 404
    )
    assert client.delete("/api/v1/holdings/MISSING/lots/fake-id").status_code == 404
    assert (
        client.post(
            "/api/v1/holdings/MISSING/lots/fake-id/settle",
            json={"exit_price": 105},
        ).status_code
        == 404
    )

    # Existing symbol, nonexistent lot_id
    client.put("/api/v1/holdings/AAPL", json={"B": 10000, "initial_price": 100, "P0": 0.3})
    r_put = client.put(
        "/api/v1/holdings/AAPL/lots/no-such-lot",
        json={"type": "grid", "price": 95, "shares": 10},
    )
    assert r_put.status_code == 404
    assert r_put.json()["code"] == "NOT_FOUND"

    r_del = client.delete("/api/v1/holdings/AAPL/lots/no-such-lot")
    assert r_del.status_code == 404
    assert r_del.json()["code"] == "NOT_FOUND"

    r_settle = client.post(
        "/api/v1/holdings/AAPL/lots/no-such-lot/settle",
        json={"exit_price": 105},
    )
    assert r_settle.status_code == 404
    assert r_settle.json()["code"] == "NOT_FOUND"


def test_gc05m_and_gc05n_settle(make_client) -> None:
    client = make_client()

    # Setup GC-06 initial state: B=10000, P0=0.3, realized_profit=500, base_profit_pool=90
    # Create with B=10000, initial_price=100, P0=0.3 -> base lot 30 @ 100
    r_init = client.put(
        "/api/v1/holdings/AAPL",
        json={
            "B": 10000,
            "initial_price": 100,
            "P0": 0.3,
            "a": 0.6,
            "b": 0.1,
            "c": 0.5,
            "K": 1.2,
            "atr_14_pct": 0.04,
            "atr_50_pct": 0.05,
            "atr_source": "manual",
            "atr_date": "2026-11-20",
        },
    )
    assert r_init.status_code == 200
    base_id = r_init.json()["lots"][0]["id"]

    # Update realized_profit=500, base_profit_pool=90 without altering existing base lot (30 @ 100)
    r_upd = client.put(
        "/api/v1/holdings/AAPL",
        json={
            "B": 10000,
            "initial_price": 100,
            "P0": 0.3,
            "a": 0.6,
            "b": 0.1,
            "c": 0.5,
            "K": 1.2,
            "realized_profit": 500,
            "base_profit_pool": 90,
        },
    )
    assert r_upd.status_code == 200
    # Retained ATR fields when omitted on update
    assert r_upd.json()["atr_14_pct"] == "0.040000"
    assert r_upd.json()["atr_50_pct"] == "0.050000"
    assert r_upd.json()["atr_source"] == "manual"
    assert r_upd.json()["atr_date"] == "2026-11-20"

    # Add grid lot-2: 25 shares @ 96.5
    r_add = client.post(
        "/api/v1/holdings/AAPL/lots",
        json={"type": "grid", "price": 96.5, "shares": 25, "filled_at": "2026-11-20", "note": "L1"},
    )
    assert r_add.status_code == 200
    lot2_id = r_add.json()["id"]

    # GC-05M (1): settle on base lot -> 422
    r_m1 = client.post(
        f"/api/v1/holdings/AAPL/lots/{base_id}/settle",
        json={"exit_price": 110},
    )
    assert r_m1.status_code == 422
    assert r_m1.json()["code"] == "VALIDATION_ERROR"

    # GC-05M (2): exit_price <= lot.price -> 422
    r_m2 = client.post(
        f"/api/v1/holdings/AAPL/lots/{lot2_id}/settle",
        json={"exit_price": 96.50},
    )
    assert r_m2.status_code == 422
    assert r_m2.json()["code"] == "VALIDATION_ERROR"

    # GC-05M (3): retain_shares * exit_price > Pool_proj (pool_avail = 104.475; 2 * 98.43 = 196.86) -> 422
    r_m3 = client.post(
        f"/api/v1/holdings/AAPL/lots/{lot2_id}/settle",
        json={"exit_price": 98.43, "retain_shares": 2},
    )
    assert r_m3.status_code == 422
    assert r_m3.json()["code"] == "VALIDATION_ERROR"

    # GC-05N: settle lot-2 at exit_price=98.43 with retain_shares omitted
    r_n = client.post(
        f"/api/v1/holdings/AAPL/lots/{lot2_id}/settle",
        json={"exit_price": 98.43},
    )
    assert r_n.status_code == 200
    body_n = r_n.json()
    assert body_n["settlement"] == {
        "lot_id": lot2_id,
        "exit_price": "98.43",
        "realized_gain": "48.25",
        "retain_shares": 1,
        "sell_shares": 24,
        "realized_profit": "548.25",
        "base_profit_pool": "6.04",
    }
    holding = body_n["holding"]
    assert holding["realized_profit"] == "548.25"
    assert holding["base_profit_pool"] == "6.04"
    assert len(holding["lots"]) == 1
    assert holding["lots"][0]["id"] == base_id
    assert holding["lots"][0]["type"] == "base"
    assert holding["lots"][0]["shares"] == 31
    assert holding["lots"][0]["price"] == "99.95"


def test_settle_creates_base_lot_when_none_exists(make_client) -> None:
    client = make_client()
    # Create NVDA with Q0=0 (no base lot), then add a grid lot and settle with retain_shares=1
    client.put(
        "/api/v1/holdings/NVDA",
        json={
            "B": 100,
            "initial_price": 500,
            "P0": 0.3,
            "realized_profit": 0,
            "base_profit_pool": 90,
        },
    )
    r_add = client.post(
        "/api/v1/holdings/NVDA/lots",
        json={"type": "grid", "price": 96.5, "shares": 25},
    )
    lot_id = r_add.json()["id"]

    r_settle = client.post(
        f"/api/v1/holdings/NVDA/lots/{lot_id}/settle",
        json={"exit_price": 98.43},
    )
    assert r_settle.status_code == 200
    body = r_settle.json()
    assert body["settlement"]["retain_shares"] == 1
    assert body["settlement"]["sell_shares"] == 24
    assert len(body["holding"]["lots"]) == 1
    new_base = body["holding"]["lots"][0]
    assert new_base["type"] == "base"
    assert new_base["shares"] == 1
    assert new_base["price"] == "98.43"


def test_update_lot_conflict_and_put_holdings_atr_validation(make_client) -> None:
    client = make_client()
    client.put(
        "/api/v1/holdings/AAPL",
        json={
            "B": 10000,
            "initial_price": 100,
            "P0": 0.3,
            "atr_14_pct": 0.04,
            "atr_50_pct": 0.05,
        },
    )
    grid_id = client.post(
        "/api/v1/holdings/AAPL/lots",
        json={"type": "grid", "price": 96.5, "shares": 10},
    ).json()["id"]

    # Updating grid lot to type=base when base already exists -> 409 BASE_LOT_EXISTS
    r_conflict = client.put(
        f"/api/v1/holdings/AAPL/lots/{grid_id}",
        json={"type": "base", "price": 96.5, "shares": 10},
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["code"] == "BASE_LOT_EXISTS"

    # Normal grid lot update succeeds
    r_ok = client.put(
        f"/api/v1/holdings/AAPL/lots/{grid_id}",
        json={"type": "grid", "price": 96.0, "shares": 12, "note": "updated"},
    )
    assert r_ok.status_code == 200
    updated_lot = next(lot for lot in r_ok.json()["lots"] if lot["id"] == grid_id)
    assert updated_lot["price"] == "96.00"
    assert updated_lot["shares"] == 12
    assert updated_lot["note"] == "updated"

    # Partial ATR (only atr_14_pct) -> 422
    r_partial = client.put(
        "/api/v1/holdings/AAPL",
        json={"B": 10000, "initial_price": 100, "P0": 0.3, "atr_14_pct": 0.03},
    )
    assert r_partial.status_code == 422
    assert r_partial.json()["code"] == "VALIDATION_ERROR"

    # Updating `a` such that a * existing ATR_eff >= 1 (25 * 0.05 = 1.25 >= 1) -> 422
    r_bad_x = client.put(
        "/api/v1/holdings/AAPL",
        json={"B": 10000, "initial_price": 100, "P0": 0.3, "a": 25},
    )
    assert r_bad_x.status_code == 422
    assert r_bad_x.json()["code"] == "VALIDATION_ERROR"


def test_cors_and_request_validation_error_format(make_client) -> None:
    client = make_client(cors_origins=("http://localhost:5173",))

    # CORS preflight
    r_opt = client.options(
        "/api/v1/holdings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r_opt.status_code == 200
    assert r_opt.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # Pydantic validation error returns standardized {code, message}
    r_bad = client.post("/api/v1/calculator/compute", json={"symbol": "AAPL"})
    assert r_bad.status_code == 422
    body = r_bad.json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "VALIDATION_ERROR"

    # Health check
    assert client.get("/health").json() == {"status": "ok"}
