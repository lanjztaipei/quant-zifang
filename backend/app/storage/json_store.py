"""Thread- and process-safe atomic JSON file storage using filelock."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar

from filelock import FileLock

T = TypeVar("T")


class JsonFileStore:
    """Locked, atomic JSON dictionary store."""

    def __init__(self, path: Path, timeout: float = 10.0) -> None:
        self.path = Path(path)
        self.lock_path = Path(f"{self.path}.lock")
        self.timeout = timeout

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        content = self.path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        data = json.loads(content)
        if not isinstance(data, dict):
            return {}
        return data

    def _write_atomic_unlocked(self, data: dict[str, Any]) -> None:
        self._ensure_parent()
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def read(self) -> dict[str, Any]:
        """Read the JSON object under a file lock."""
        self._ensure_parent()
        with FileLock(str(self.lock_path), timeout=self.timeout):
            return self._read_unlocked()

    def write(self, data: dict[str, Any]) -> None:
        """Atomically overwrite the JSON file under a file lock."""
        self._ensure_parent()
        with FileLock(str(self.lock_path), timeout=self.timeout):
            self._write_atomic_unlocked(data)

    def update(self, mutator: Callable[[dict[str, Any]], T]) -> T:
        """Perform an atomic read-modify-write cycle under a single file lock."""
        self._ensure_parent()
        with FileLock(str(self.lock_path), timeout=self.timeout):
            data = self._read_unlocked()
            result = mutator(data)
            self._write_atomic_unlocked(data)
            return result
