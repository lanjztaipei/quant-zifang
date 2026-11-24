"""Application configuration loaded from environment variables and .env files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_DEFAULT_ENV_FILES: Final[tuple[Path, Path]] = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")

EnvName = Literal["dev", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
)


def _validate_origin(origin: str) -> str:
    if origin == "*":
        raise ValueError("CORS_ORIGINS cannot contain wildcard '*' when allow_credentials=True")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != ""
        or parsed.query != ""
        or parsed.fragment != ""
    ):
        raise ValueError(
            f"Invalid CORS origin {origin!r}: expected 'http(s)://host[:port]' "
            "without path, query, or trailing slash"
        )
    return origin


class Settings(BaseSettings):
    """Validated runtime settings for Quant Zifang backend."""

    model_config = SettingsConfigDict(
        env_file=_DEFAULT_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    env: EnvName = Field(
        default="dev",
        validation_alias=AliasChoices("ENV", "ZIFANG_ENV"),
    )
    log_level: LogLevel = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "ZIFANG_LOG_LEVEL"),
    )
    data_dir: Path = Field(
        default=Path("data"),
        validation_alias=AliasChoices("DATA_DIR", "ZIFANG_DATA_DIR"),
    )
    cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=DEFAULT_CORS_ORIGINS,
        validation_alias=AliasChoices("CORS_ORIGINS", "ZIFANG_CORS_ORIGINS"),
    )

    @field_validator("env", mode="before")
    @classmethod
    def _normalize_env(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("data_dir", mode="before")
    @classmethod
    def _validate_data_dir(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("DATA_DIR must not be empty")
            return Path(stripped)
        if isinstance(value, Path) and not str(value).strip():
            raise ValueError("DATA_DIR must not be empty")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> tuple[str, ...]:
        items: list[str]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                raise ValueError("CORS_ORIGINS must not be empty")
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in CORS_ORIGINS: {exc.msg}") from exc
                if not isinstance(parsed, list) or not all(
                    isinstance(item, str) for item in parsed
                ):
                    raise ValueError("CORS_ORIGINS JSON must be a list of origin strings")
                items = [item.strip() for item in parsed if item.strip()]
            else:
                items = [part.strip() for part in raw.split(",") if part.strip()]
        elif isinstance(value, (list, tuple, set)):
            if not all(isinstance(item, str) for item in value):
                raise ValueError("CORS_ORIGINS elements must be strings")
            items = [item.strip() for item in value if item.strip()]
        else:
            raise ValueError("CORS_ORIGINS must be a comma-separated string or sequence of origins")

        if not items:
            raise ValueError("CORS_ORIGINS must contain at least one valid origin")
        return tuple(_validate_origin(origin) for origin in items)

    @classmethod
    def from_env(
        cls,
        *,
        env_file: Path | str | tuple[Path | str, ...] | None = _DEFAULT_ENV_FILES,
    ) -> Settings:
        """Load and validate settings from environment variables and optional .env file(s)."""
        return cls(_env_file=env_file)  # type: ignore[call-arg]
