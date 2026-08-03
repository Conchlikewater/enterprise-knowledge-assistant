"""SQLite implementation of the document metadata repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from app.core.exceptions import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentRepositoryError,
)
from app.domain.models import Document, DocumentStatus, utc_now
from app.storage.document_repository import DocumentRepository


class SQLiteDocumentRepository(DocumentRepository):
    """Persist document-level records without storing document text."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the parent directory and V1 schema when absent."""
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                        sha256 TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL CHECK (
                            status IN ('processing', 'ready', 'failed')
                        ),
                        chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
                        stored_path TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
                )
        except (OSError, sqlite3.DatabaseError) as exc:
            raise DocumentRepositoryError() from exc

    def health(self) -> bool:
        try:
            with self._connection() as connection:
                row = connection.execute("SELECT 1 AS healthy").fetchone()
            return row is not None and row["healthy"] == 1
        except sqlite3.DatabaseError:
            return False

    def create(self, document: Document) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO documents (
                        document_id,
                        filename,
                        media_type,
                        size_bytes,
                        sha256,
                        status,
                        chunk_count,
                        stored_path,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(document.document_id),
                        document.filename,
                        document.media_type,
                        document.size_bytes,
                        document.sha256,
                        document.status.value,
                        document.chunk_count,
                        str(document.stored_path),
                        document.created_at.isoformat(),
                        document.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DocumentConflictError() from exc
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    def get(self, document_id: UUID) -> Document | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM documents WHERE document_id = ?",
                    (str(document_id),),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc
        return self._to_document(row) if row is not None else None

    def list(self) -> Sequence[Document]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT * FROM documents ORDER BY created_at, document_id"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc
        return tuple(self._to_document(row) for row in rows)

    def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        chunk_count: int,
    ) -> None:
        if chunk_count < 0:
            raise ValueError("chunk_count must not be negative")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE documents
                    SET status = ?, chunk_count = ?, updated_at = ?
                    WHERE document_id = ?
                    """,
                    (status.value, chunk_count, utc_now().isoformat(), str(document_id)),
                )
                if cursor.rowcount == 0:
                    raise DocumentNotFoundError()
        except DocumentNotFoundError:
            raise
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    def delete(self, document_id: UUID) -> None:
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "DELETE FROM documents WHERE document_id = ?",
                    (str(document_id),),
                )
                if cursor.rowcount == 0:
                    raise DocumentNotFoundError()
        except DocumentNotFoundError:
            raise
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    @staticmethod
    def _to_document(row: sqlite3.Row) -> Document:
        from datetime import datetime

        return Document(
            document_id=UUID(row["document_id"]),
            filename=row["filename"],
            media_type=row["media_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            status=DocumentStatus(row["status"]),
            chunk_count=row["chunk_count"],
            stored_path=Path(row["stored_path"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
