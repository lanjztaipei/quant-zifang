"""Tests for thread-safe CA bundle startup initialization and FastAPI lifespan."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.yfinance_provider import ensure_ascii_ca_bundle
from tests.conftest import FakeMarketDataFetcher


def test_ensure_ascii_ca_bundle_skips_when_already_set_or_ascii(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURL_CA_BUNDLE", "/already/set.pem")
    assert ensure_ascii_ca_bundle() is None

    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.setattr(
        "app.providers.yfinance_provider.certifi.where",
        lambda: "/ascii/path/cacert.pem",
    )
    assert ensure_ascii_ca_bundle() is None
    assert "CURL_CA_BUNDLE" not in os.environ


def test_ensure_ascii_ca_bundle_copies_atomically_for_non_ascii_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    non_ascii_dir = tmp_path / "張良_certs"
    non_ascii_dir.mkdir()
    src_cert = non_ascii_dir / "cacert.pem"
    src_cert.write_text("DUMMY-CERT-V1", encoding="utf-8")

    ascii_temp_dir = tmp_path / "ascii_tmp"
    ascii_temp_dir.mkdir()

    monkeypatch.setattr(
        "app.providers.yfinance_provider.certifi.where",
        lambda: str(src_cert),
    )
    monkeypatch.setattr(
        "app.providers.yfinance_provider.tempfile.gettempdir",
        lambda: str(ascii_temp_dir),
    )

    dst = ensure_ascii_ca_bundle()
    assert dst == ascii_temp_dir / "quant_zifang_cacert.pem"
    assert dst.read_text(encoding="utf-8") == "DUMMY-CERT-V1"
    assert os.environ["CURL_CA_BUNDLE"] == str(dst)

    # Second call with updated source size (after clearing env var) atomically refreshes file
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    src_cert.write_text("DUMMY-CERT-V2-LONGER", encoding="utf-8")
    dst2 = ensure_ascii_ca_bundle()
    assert dst2 == dst
    assert dst2.read_text(encoding="utf-8") == "DUMMY-CERT-V2-LONGER"


def test_lifespan_initializes_resources_logging_and_ca_bundle_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ca_calls = 0

    def fake_ensure_ca() -> Path:
        nonlocal ca_calls
        ca_calls += 1
        return tmp_path / "quant_zifang_cacert.pem"

    monkeypatch.setattr("app.main.ensure_ascii_ca_bundle", fake_ensure_ca)

    nested_data_dir = tmp_path / "nested" / "data"
    cfg = Settings(
        env="prod",
        log_level="DEBUG",
        data_dir=nested_data_dir,
        cors_origins=("https://app.example.com",),
    )
    app = create_app(settings=cfg, fetcher=FakeMarketDataFetcher())

    assert app.debug is False
    # Lifespan has not started yet at app creation time
    assert ca_calls == 0
    assert not nested_data_dir.exists()

    with caplog.at_level(logging.INFO, logger="app"), TestClient(app) as client:
        assert ca_calls == 1
        assert nested_data_dir.is_dir()
        assert logging.getLogger("app").level == logging.DEBUG
        assert app.state.settings is cfg
        assert app.state.market_provider is not None
        assert app.state.holdings_repo is not None

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    assert ca_calls == 1
    assert any("Quant Zifang API started" in rec.message for rec in caplog.records)
    assert any("Quant Zifang API shutting down" in rec.message for rec in caplog.records)
