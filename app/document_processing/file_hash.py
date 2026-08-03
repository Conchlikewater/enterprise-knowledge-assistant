"""Streaming content hashing utilities."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def calculate_sha256(file_path: Path, buffer_size: int = 64 * 1024) -> str:
    if buffer_size <= 0:
        raise ValueError("buffer_size must be positive")

    digest = sha256()
    with file_path.open("rb") as source:
        while block := source.read(buffer_size):
            digest.update(block)
    return digest.hexdigest()
