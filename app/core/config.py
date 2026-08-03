"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _read_int(environment: Mapping[str, str], name: str, default: int) -> int:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret V1 settings.

    Provider credentials will be added only with a selected provider adapter and
    must never be included in logs or API responses.
    """

    app_name: str = "Enterprise Knowledge Assistant"
    app_version: str = "0.1.0"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    upload_dir: Path = Path("data/uploads")
    sqlite_path: Path = Path("data/app.db")
    qdrant_path: Path = Path("data/qdrant")
    max_upload_bytes: int = 10 * 1024 * 1024
    chunk_size: int = 1000
    chunk_overlap: int = 150

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environment is None else environment
        return cls(
            environment=env.get("RAG_ENVIRONMENT", "development"),
            host=env.get("RAG_HOST", "127.0.0.1"),
            port=_read_int(env, "RAG_PORT", 8000),
            log_level=env.get("RAG_LOG_LEVEL", "INFO").upper(),
            upload_dir=Path(env.get("RAG_UPLOAD_DIR", "data/uploads")),
            sqlite_path=Path(env.get("RAG_SQLITE_PATH", "data/app.db")),
            qdrant_path=Path(env.get("RAG_QDRANT_PATH", "data/qdrant")),
            max_upload_bytes=_read_int(env, "RAG_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
            chunk_size=_read_int(env, "RAG_CHUNK_SIZE", 1000),
            chunk_overlap=_read_int(env, "RAG_CHUNK_OVERLAP", 150),
        )
