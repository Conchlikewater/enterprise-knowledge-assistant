"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

_LLM_REASONING_EFFORTS = frozenset(
    {"none", "low", "medium", "high", "xhigh", "max"}
)
_LLM_VERBOSITY_LEVELS = frozenset({"low", "medium", "high"})


def _read_int(environment: Mapping[str, str], name: str, default: int) -> int:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _read_float(environment: Mapping[str, str], name: str, default: float) -> float:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """Typed V1 settings with credentials excluded from repr and comparisons."""

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
    qdrant_collection: str = "knowledge_chunks"
    openai_api_key: str | None = field(default=None, repr=False, compare=False)
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 64
    openai_timeout_seconds: float = 30.0
    llm_model: str = "gpt-5.6-sol"
    llm_reasoning_effort: str = "low"
    llm_verbosity: str = "low"
    llm_max_output_tokens: int = 800
    llm_timeout_seconds: float = 60.0
    max_upload_bytes: int = 10 * 1024 * 1024
    chunk_size: int = 1000
    chunk_overlap: int = 150

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        if not self.qdrant_collection.strip():
            raise ValueError("qdrant_collection must not be empty")
        if not self.embedding_model.strip():
            raise ValueError("embedding_model must not be empty")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        if self.openai_timeout_seconds <= 0:
            raise ValueError("openai_timeout_seconds must be positive")
        if not self.llm_model.strip():
            raise ValueError("llm_model must not be empty")
        if self.llm_reasoning_effort not in _LLM_REASONING_EFFORTS:
            raise ValueError("llm_reasoning_effort is not supported")
        if self.llm_verbosity not in _LLM_VERBOSITY_LEVELS:
            raise ValueError("llm_verbosity is not supported")
        if self.llm_max_output_tokens <= 0:
            raise ValueError("llm_max_output_tokens must be positive")
        if self.llm_timeout_seconds <= 0:
            raise ValueError("llm_timeout_seconds must be positive")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
        env_file: Path = Path(".env"),
    ) -> "Settings":
        if environment is None:
            file_values = {
                key: value
                for key, value in dotenv_values(env_file).items()
                if value is not None
            }
            env: Mapping[str, str] = {**file_values, **os.environ}
        else:
            env = environment
        api_key = env.get("OPENAI_API_KEY")
        return cls(
            environment=env.get("RAG_ENVIRONMENT", "development"),
            host=env.get("RAG_HOST", "127.0.0.1"),
            port=_read_int(env, "RAG_PORT", 8000),
            log_level=env.get("RAG_LOG_LEVEL", "INFO").upper(),
            upload_dir=Path(env.get("RAG_UPLOAD_DIR", "data/uploads")),
            sqlite_path=Path(env.get("RAG_SQLITE_PATH", "data/app.db")),
            qdrant_path=Path(env.get("RAG_QDRANT_PATH", "data/qdrant")),
            qdrant_collection=env.get("RAG_QDRANT_COLLECTION", "knowledge_chunks"),
            openai_api_key=api_key.strip() if api_key and api_key.strip() else None,
            embedding_model=env.get(
                "RAG_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            embedding_dimensions=_read_int(
                env, "RAG_EMBEDDING_DIMENSIONS", 1536
            ),
            embedding_batch_size=_read_int(env, "RAG_EMBEDDING_BATCH_SIZE", 64),
            openai_timeout_seconds=_read_float(
                env, "RAG_OPENAI_TIMEOUT_SECONDS", 30.0
            ),
            llm_model=env.get("RAG_LLM_MODEL", "gpt-5.6-sol"),
            llm_reasoning_effort=env.get(
                "RAG_LLM_REASONING_EFFORT", "low"
            ).lower(),
            llm_verbosity=env.get("RAG_LLM_VERBOSITY", "low").lower(),
            llm_max_output_tokens=_read_int(
                env, "RAG_LLM_MAX_OUTPUT_TOKENS", 800
            ),
            llm_timeout_seconds=_read_float(
                env, "RAG_LLM_TIMEOUT_SECONDS", 60.0
            ),
            max_upload_bytes=_read_int(env, "RAG_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
            chunk_size=_read_int(env, "RAG_CHUNK_SIZE", 1000),
            chunk_overlap=_read_int(env, "RAG_CHUNK_OVERLAP", 150),
        )
