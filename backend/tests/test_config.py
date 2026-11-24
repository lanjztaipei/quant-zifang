"""Tests for pydantic-settings configuration and .env loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_CORS_ORIGINS, Settings

_SETTINGS_ENV_KEYS = (
    "ENV",
    "ZIFANG_ENV",
    "LOG_LEVEL",
    "ZIFANG_LOG_LEVEL",
    "DATA_DIR",
    "ZIFANG_DATA_DIR",
    "CORS_ORIGINS",
    "ZIFANG_CORS_ORIGINS",
)


@pytest.fixture
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_defaults_without_env_file(clean_settings_env: None) -> None:
    cfg = Settings.from_env(env_file=None)
    assert cfg.env == "dev"
    assert cfg.log_level == "INFO"
    assert cfg.data_dir == Path("data")
    assert cfg.cors_origins == DEFAULT_CORS_ORIGINS


def test_settings_loads_dotenv_and_env_overrides_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clean_settings_env: None,
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "ENV=prod",
                "LOG_LEVEL=debug",
                "DATA_DIR=custom_data",
                "CORS_ORIGINS=https://app.example.com, http://localhost:5173",
                "UNRELATED_FRONTEND_VAR=ignored",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cfg = Settings.from_env(env_file=dotenv)
    assert cfg.env == "prod"
    assert cfg.log_level == "DEBUG"
    assert cfg.data_dir == Path("custom_data")
    assert cfg.cors_origins == ("https://app.example.com", "http://localhost:5173")

    # Process environment variable must override .env file
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("DATA_DIR", "env_override_data")
    cfg_override = Settings.from_env(env_file=dotenv)
    assert cfg_override.log_level == "WARNING"
    assert cfg_override.data_dir == Path("env_override_data")
    assert cfg_override.env == "prod"


def test_settings_supports_zifang_prefix_aliases_and_json_cors(
    monkeypatch: pytest.MonkeyPatch,
    clean_settings_env: None,
) -> None:
    monkeypatch.setenv("ZIFANG_ENV", "PROD")
    monkeypatch.setenv("ZIFANG_LOG_LEVEL", "error")
    monkeypatch.setenv("ZIFANG_DATA_DIR", "zifang_dir")
    monkeypatch.setenv(
        "ZIFANG_CORS_ORIGINS",
        '["https://trade.example.com", "http://127.0.0.1:5173"]',
    )

    cfg = Settings.from_env(env_file=None)
    assert cfg.env == "prod"
    assert cfg.log_level == "ERROR"
    assert cfg.data_dir == Path("zifang_dir")
    assert cfg.cors_origins == ("https://trade.example.com", "http://127.0.0.1:5173")


def test_settings_is_immutable(clean_settings_env: None) -> None:
    cfg = Settings.from_env(env_file=None)
    with pytest.raises(ValidationError):
        cfg.env = "prod"


@pytest.mark.parametrize(
    ("env_var", "value"),
    [
        ("ENV", "staging"),
        ("ENV", ""),
        ("LOG_LEVEL", "VERBOSE"),
        ("DATA_DIR", "   "),
        ("CORS_ORIGINS", ""),
        ("CORS_ORIGINS", "*"),
        ("CORS_ORIGINS", "http://localhost:5173,*"),
        ("CORS_ORIGINS", "localhost:5173"),
        ("CORS_ORIGINS", "ftp://localhost:5173"),
        ("CORS_ORIGINS", "http://localhost:5173/"),
        ("CORS_ORIGINS", "http://localhost:5173/api"),
        ("CORS_ORIGINS", "http://user:pass@localhost:5173"),
        ("CORS_ORIGINS", "[invalid-json"),
        ("CORS_ORIGINS", '{"not": "a-list"}'),
        ("CORS_ORIGINS", "[123]"),
    ],
)
def test_settings_rejects_invalid_env_values(
    env_var: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    clean_settings_env: None,
) -> None:
    monkeypatch.setenv(env_var, value)
    with pytest.raises(ValidationError):
        Settings.from_env(env_file=None)


def test_settings_rejects_invalid_direct_types(clean_settings_env: None) -> None:
    with pytest.raises(ValidationError):
        Settings(env="dev", log_level="INFO", data_dir=Path("data"), cors_origins=123)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(env="dev", log_level="INFO", data_dir=Path("data"), cors_origins=[123])  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(env="dev", log_level="INFO", data_dir=Path("data"), cors_origins=())
