import os
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.domain.models import DocumentStatus, IngestionJobStatus
from app.services.async_ingestion_service import AsyncIngestionService
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository

QDRANT_SERVER_URL = os.environ.get("RAG_TEST_QDRANT_URL")

pytestmark = pytest.mark.skipif(
    not QDRANT_SERVER_URL,
    reason="RAG_TEST_QDRANT_URL is required for the Worker process test",
)


def _wait_until_ready(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url.rstrip('/')}/readyz", timeout=1.0) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    pytest.fail("Qdrant Server did not become ready")


def test_independent_worker_process_recovers_fixed_crash_point() -> None:
    assert QDRANT_SERVER_URL is not None
    _wait_until_ready(QDRANT_SERVER_URL)
    collection_name = f"r23_worker_{uuid4().hex}"
    cleanup_client = QdrantClient(url=QDRANT_SERVER_URL)
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        database_path = root / "app.db"
        upload_dir = root / "uploads"
        repository = SQLiteDocumentRepository(database_path, busy_timeout_ms=1000)
        repository.initialize()
        submitter = AsyncIngestionService(repository, upload_dir, 4096)
        document, job = submitter.submit(
            BytesIO(
                b"First server evidence. Second server evidence. Third server evidence."
            ),
            "server-recovery.txt",
            "text/plain",
        )
        command = [
            sys.executable,
            "-m",
            "tests.helpers.r23_worker_process",
            "crash",
            "--database",
            str(database_path),
            "--upload-dir",
            str(upload_dir),
            "--qdrant-url",
            QDRANT_SERVER_URL,
            "--collection",
            collection_name,
        ]
        try:
            crashed = subprocess.run(command, check=False, timeout=30)
            assert crashed.returncode == 91
            assert repository.get_job(job.job_id).status is IngestionJobStatus.RUNNING
            assert (
                repository.get(document.document_id).status is DocumentStatus.PROCESSING
            )

            command[3] = "recover"
            recovered = subprocess.run(command, check=False, timeout=30)
            assert recovered.returncode == 0

            ready_job = repository.get_job(job.job_id)
            ready_document = repository.get(document.document_id)
            assert ready_job.status is IngestionJobStatus.READY
            assert ready_job.attempt_count == 2
            assert ready_document.status is DocumentStatus.READY

            store = QdrantVectorStore(
                storage_path=None,
                url=QDRANT_SERVER_URL,
                collection_name=collection_name,
                vector_size=3,
            )
            try:
                store.initialize()
                results = store.search(
                    [1.0, 0.0, 0.0],
                    [document.document_id],
                    limit=100,
                )
                assert len(results) == ready_document.chunk_count
                assert len({result.chunk_id for result in results}) == len(results)
            finally:
                store.close()
        finally:
            if cleanup_client.collection_exists(collection_name):
                cleanup_client.delete_collection(collection_name=collection_name)
            cleanup_client.close()
