"""Upload metadata validation and safe internal path construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final
from uuid import UUID

from app.core.exceptions import (
    DocumentStorageError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFilenameError,
    UnsupportedFileTypeError,
)

SUPPORTED_MEDIA_TYPES: Final[dict[str, str]] = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}


@dataclass(frozen=True, slots=True)
class ValidatedFileIdentity:
    filename: str
    suffix: str
    media_type: str


@dataclass(frozen=True, slots=True)
class ValidatedFile:
    filename: str
    suffix: str
    media_type: str
    size_bytes: int


def validate_file_identity(
    filename: str,
    declared_media_type: str,
) -> ValidatedFileIdentity:
    """Validate the client-supplied name and declared media type."""
    clean_filename = filename.strip()
    normalized_name = clean_filename.replace("\\", "/")
    posix_path = PurePosixPath(normalized_name)
    windows_path = PureWindowsPath(clean_filename)

    if (
        not clean_filename
        or "\x00" in clean_filename
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or len(posix_path.parts) != 1
        or clean_filename in {".", ".."}
    ):
        raise InvalidFilenameError()

    suffix = posix_path.suffix.lower()
    expected_media_type = SUPPORTED_MEDIA_TYPES.get(suffix)
    normalized_media_type = declared_media_type.partition(";")[0].strip().lower()
    if expected_media_type is None or normalized_media_type != expected_media_type:
        raise UnsupportedFileTypeError()

    return ValidatedFileIdentity(
        filename=clean_filename,
        suffix=suffix,
        media_type=expected_media_type,
    )


def validate_file(
    filename: str,
    declared_media_type: str,
    size_bytes: int,
    max_upload_bytes: int,
) -> ValidatedFile:
    """Validate metadata using the measured file size, not a request header."""
    identity = validate_file_identity(filename, declared_media_type)
    if size_bytes <= 0:
        raise EmptyFileError()
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes must be positive")
    if size_bytes > max_upload_bytes:
        raise FileTooLargeError()

    return ValidatedFile(
        filename=identity.filename,
        suffix=identity.suffix,
        media_type=identity.media_type,
        size_bytes=size_bytes,
    )


def build_storage_path(upload_dir: Path, document_id: UUID, suffix: str) -> Path:
    """Build a UUID-based path and prove that it remains under upload_dir."""
    normalized_suffix = suffix.lower()
    if normalized_suffix not in SUPPORTED_MEDIA_TYPES:
        raise UnsupportedFileTypeError()

    resolved_upload_dir = upload_dir.resolve(strict=False)
    storage_path = (resolved_upload_dir / f"{document_id}{normalized_suffix}").resolve(
        strict=False
    )
    if storage_path.parent != resolved_upload_dir:
        raise InvalidFilenameError()
    return storage_path


def validate_storage_path(
    upload_dir: Path,
    document_id: UUID,
    media_type: str,
    stored_path: Path,
) -> Path:
    """Return the canonical internal path or reject untrusted persisted metadata."""
    suffix = next(
        (
            extension
            for extension, supported_media_type in SUPPORTED_MEDIA_TYPES.items()
            if supported_media_type == media_type
        ),
        None,
    )
    if suffix is None:
        raise DocumentStorageError()
    expected_path = build_storage_path(upload_dir, document_id, suffix)
    if stored_path.resolve(strict=False) != expected_path:
        raise DocumentStorageError()
    return expected_path
