"""Bounded streaming upload storage with atomic finalization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.exceptions import (
    DocumentStorageError,
    EmptyFileError,
    FileTooLargeError,
)


@dataclass(frozen=True, slots=True)
class StoredFileInfo:
    size_bytes: int
    sha256: str


def save_upload_stream(
    source: BinaryIO,
    destination: Path,
    max_upload_bytes: int,
    buffer_size: int = 64 * 1024,
) -> StoredFileInfo:
    """Stream an upload to a temporary file, then publish it without overwrite."""
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes must be positive")
    if buffer_size <= 0:
        raise ValueError("buffer_size must be positive")

    temporary_path = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
    digest = sha256()
    size_bytes = 0

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise DocumentStorageError()

        with temporary_path.open("xb") as target:
            while True:
                block = source.read(buffer_size)
                if block == b"":
                    break
                if not isinstance(block, bytes):
                    raise DocumentStorageError()

                size_bytes += len(block)
                if size_bytes > max_upload_bytes:
                    raise FileTooLargeError()
                target.write(block)
                digest.update(block)

        if size_bytes == 0:
            raise EmptyFileError()

        # Creating a hard link is an atomic, exclusive publish operation: an
        # existing destination is never replaced. Both names are in one folder.
        os.link(temporary_path, destination)
        _remove_if_present(temporary_path)
        return StoredFileInfo(size_bytes=size_bytes, sha256=digest.hexdigest())
    except (EmptyFileError, FileTooLargeError, DocumentStorageError):
        _remove_if_present(temporary_path)
        raise
    except Exception as exc:
        _remove_if_present(temporary_path)
        raise DocumentStorageError() from exc


def _remove_if_present(file_path: Path) -> None:
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass
