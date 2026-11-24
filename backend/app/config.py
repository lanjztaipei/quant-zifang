"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://localhost:5173,"
    "http://localhost:8000,"
    "http://127.0.0.1:3000,"
    "http://127.0.0.1:5173,"
    "http://127.0.0.1:8000"
)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir_raw = os.getenv("DATA_DIR") or os.getenv("ZIFANG_DATA_DIR") or "data"
        cors_raw = os.getenv("CORS_ORIGINS") or os.getenv("ZIFANG_CORS_ORIGINS") or DEFAULT_CORS_ORIGINS
        origins = tuple(origin.strip() for origin in cors_raw.split(",") if origin.strip())
        return cls(
            data_dir=Path(data_dir_raw),
            cors_origins=origins,
        )
