"""SQLite repositories for document metadata and asynchronous ingestion jobs."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.core.exceptions import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentProcessingError,
    DocumentRepositoryError,
    IngestionJobStateError,
)
from app.domain.models import (
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
    utc_now,
)
from app.storage.document_repository import DocumentRepository
from app.storage.ingestion_job_repository import IngestionJobRepository

SCHEMA_VERSION = 2
_ACTIVE_JOB_STATUSES = (
    IngestionJobStatus.PENDING.value,
    IngestionJobStatus.RUNNING.value,
)


class SQLiteDocumentRepository(DocumentRepository, IngestionJobRepository):
    """Persist document and Job state in short SQLite transactions."""

    def __init__(self, database_path: Path, busy_timeout_ms: int = 5000) -> None:
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")
        self._database_path = database_path
        self._busy_timeout_ms = busy_timeout_ms

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create or migrate the database without rebuilding existing documents."""
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                journal_mode = connection.execute(
                    "PRAGMA journal_mode = WAL"
                ).fetchone()
                if journal_mode is None or str(journal_mode[0]).lower() != "wal":
                    raise sqlite3.DatabaseError("WAL mode could not be enabled")

                version_row = connection.execute("PRAGMA user_version").fetchone()
                current_version = int(version_row[0]) if version_row is not None else 0
                if current_version > SCHEMA_VERSION:
                    raise sqlite3.DatabaseError(
                        "database schema is newer than this app"
                    )

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
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_jobs (
                        job_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL CHECK (
                            status IN ('pending', 'running', 'ready', 'failed')
                        ),
                        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (
                            attempt_count >= 0
                        ),
                        error_code TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        FOREIGN KEY(document_id) REFERENCES documents(document_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_claim
                    ON ingestion_jobs(status, created_at, job_id)
                    """
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except (OSError, sqlite3.DatabaseError) as exc:
            raise DocumentRepositoryError() from exc

    def health(self) -> bool:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT 1 AS healthy WHERE (SELECT user_version FROM pragma_user_version) = ?",
                    (SCHEMA_VERSION,),
                ).fetchone()
            return row is not None and row["healthy"] == 1
        except sqlite3.DatabaseError:
            return False

    def create(self, document: Document) -> None:
        try:
            with self._connection() as connection:
                self._insert_document(connection, document)
        except sqlite3.IntegrityError as exc:
            raise DocumentConflictError() from exc
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    def create_document_and_job(
        self,
        document: Document,
        job: IngestionJob,
    ) -> None:
        if document.document_id != job.document_id:
            raise ValueError("document and job must refer to the same document_id")
        if document.status is not DocumentStatus.PROCESSING:
            raise ValueError("new asynchronous documents must be processing")
        if job.status is not IngestionJobStatus.PENDING or job.attempt_count != 0:
            raise ValueError("new ingestion jobs must be pending and unattempted")

        try:
            with self._connection() as connection:
                self._insert_document(connection, document)
                connection.execute(
                    """
                    INSERT INTO ingestion_jobs (
                        job_id,
                        document_id,
                        status,
                        attempt_count,
                        error_code,
                        created_at,
                        updated_at,
                        started_at,
                        completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(job.job_id),
                        str(job.document_id),
                        job.status.value,
                        job.attempt_count,
                        job.error_code,
                        job.created_at.isoformat(),
                        job.updated_at.isoformat(),
                        self._format_optional_datetime(job.started_at),
                        self._format_optional_datetime(job.completed_at),
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

    def get_for_deletion(self, document_id: UUID) -> Document:
        """Check Document and active Job state under one SQLite write lock."""
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM documents WHERE document_id = ?",
                    (str(document_id),),
                ).fetchone()
                if row is None:
                    raise DocumentNotFoundError()
                active_job = connection.execute(
                    """
                    SELECT 1
                    FROM ingestion_jobs
                    WHERE document_id = ? AND status IN (?, ?)
                    LIMIT 1
                    """,
                    (str(document_id), *_ACTIVE_JOB_STATUSES),
                ).fetchone()
                document = self._to_document(row)
                if (
                    document.status is DocumentStatus.PROCESSING
                    or active_job is not None
                ):
                    raise DocumentProcessingError()
                return document
        except (DocumentNotFoundError, DocumentProcessingError):
            raise
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

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
                    (
                        status.value,
                        chunk_count,
                        utc_now().isoformat(),
                        str(document_id),
                    ),
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

    def get_job(self, job_id: UUID) -> IngestionJob | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM ingestion_jobs WHERE job_id = ?",
                    (str(job_id),),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc
        return self._to_job(row) if row is not None else None

    def claim_next_job(self) -> IngestionJob | None:
        """Serialize selection and claim, and require a processing Document."""
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT jobs.job_id
                    FROM ingestion_jobs AS jobs
                    JOIN documents AS documents
                        ON documents.document_id = jobs.document_id
                    WHERE jobs.status = ? AND documents.status = ?
                    ORDER BY jobs.created_at, jobs.job_id
                    LIMIT 1
                    """,
                    (
                        IngestionJobStatus.PENDING.value,
                        DocumentStatus.PROCESSING.value,
                    ),
                ).fetchone()
                if row is None:
                    return None

                now = utc_now().isoformat()
                cursor = connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = ?,
                        attempt_count = attempt_count + 1,
                        error_code = NULL,
                        started_at = ?,
                        completed_at = NULL,
                        updated_at = ?
                    WHERE job_id = ? AND status = ?
                      AND EXISTS (
                          SELECT 1 FROM documents
                          WHERE documents.document_id = ingestion_jobs.document_id
                            AND documents.status = ?
                      )
                    """,
                    (
                        IngestionJobStatus.RUNNING.value,
                        now,
                        now,
                        row["job_id"],
                        IngestionJobStatus.PENDING.value,
                        DocumentStatus.PROCESSING.value,
                    ),
                )
                if cursor.rowcount != 1:
                    raise IngestionJobStateError()
                claimed = connection.execute(
                    "SELECT * FROM ingestion_jobs WHERE job_id = ?",
                    (row["job_id"],),
                ).fetchone()
                if claimed is None:
                    raise IngestionJobStateError()
                return self._to_job(claimed)
        except IngestionJobStateError:
            raise
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    def complete_job(
        self,
        job_id: UUID,
        document_id: UUID,
        chunk_count: int,
    ) -> None:
        if chunk_count <= 0:
            raise ValueError("chunk_count must be positive")
        now = utc_now().isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                job_cursor = connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = ?, error_code = NULL, completed_at = ?, updated_at = ?
                    WHERE job_id = ? AND document_id = ? AND status = ?
                    """,
                    (
                        IngestionJobStatus.READY.value,
                        now,
                        now,
                        str(job_id),
                        str(document_id),
                        IngestionJobStatus.RUNNING.value,
                    ),
                )
                if job_cursor.rowcount != 1:
                    raise IngestionJobStateError()
                document_cursor = connection.execute(
                    """
                    UPDATE documents
                    SET status = ?, chunk_count = ?, updated_at = ?
                    WHERE document_id = ? AND status = ?
                    """,
                    (
                        DocumentStatus.READY.value,
                        chunk_count,
                        now,
                        str(document_id),
                        DocumentStatus.PROCESSING.value,
                    ),
                )
                if document_cursor.rowcount != 1:
                    raise IngestionJobStateError()
        except IngestionJobStateError:
            raise
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    def fail_job(
        self,
        job_id: UUID,
        document_id: UUID,
        error_code: str,
    ) -> None:
        normalized_error = error_code.strip()
        if not normalized_error:
            raise ValueError("error_code must not be blank")
        now = utc_now().isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                job_cursor = connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = ?, error_code = ?, completed_at = ?, updated_at = ?
                    WHERE job_id = ? AND document_id = ? AND status = ?
                    """,
                    (
                        IngestionJobStatus.FAILED.value,
                        normalized_error,
                        now,
                        now,
                        str(job_id),
                        str(document_id),
                        IngestionJobStatus.RUNNING.value,
                    ),
                )
                if job_cursor.rowcount != 1:
                    raise IngestionJobStateError()
                document_cursor = connection.execute(
                    """
                    UPDATE documents
                    SET status = ?, chunk_count = 0, updated_at = ?
                    WHERE document_id = ? AND status = ?
                    """,
                    (
                        DocumentStatus.FAILED.value,
                        now,
                        str(document_id),
                        DocumentStatus.PROCESSING.value,
                    ),
                )
                if document_cursor.rowcount != 1:
                    raise IngestionJobStateError()
        except IngestionJobStateError:
            raise
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    def recover_running_jobs(self) -> int:
        now = utc_now().isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = ?, error_code = NULL, started_at = NULL,
                        completed_at = NULL, updated_at = ?
                    WHERE status = ?
                      AND EXISTS (
                          SELECT 1 FROM documents
                          WHERE documents.document_id = ingestion_jobs.document_id
                            AND documents.status = ?
                      )
                    """,
                    (
                        IngestionJobStatus.PENDING.value,
                        now,
                        IngestionJobStatus.RUNNING.value,
                        DocumentStatus.PROCESSING.value,
                    ),
                )
                return cursor.rowcount
        except sqlite3.DatabaseError as exc:
            raise DocumentRepositoryError() from exc

    @staticmethod
    def _insert_document(
        connection: sqlite3.Connection,
        document: Document,
    ) -> None:
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

    @staticmethod
    def _to_document(row: sqlite3.Row) -> Document:
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

    @staticmethod
    def _to_job(row: sqlite3.Row) -> IngestionJob:
        return IngestionJob(
            job_id=UUID(row["job_id"]),
            document_id=UUID(row["document_id"]),
            status=IngestionJobStatus(row["status"]),
            attempt_count=row["attempt_count"],
            error_code=row["error_code"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            started_at=SQLiteDocumentRepository._parse_optional_datetime(
                row["started_at"]
            ),
            completed_at=SQLiteDocumentRepository._parse_optional_datetime(
                row["completed_at"]
            ),
        )

    @staticmethod
    def _format_optional_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _parse_optional_datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None
