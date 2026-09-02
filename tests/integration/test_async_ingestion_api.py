import asyncio
import tempfile
from pathlib import Path

import httpx

from app.core.config import Settings
from app.main import create_app
from app.services.ingestion_processor import IngestionProcessor
from app.services.ingestion_worker import IngestionWorker
from tests.fakes import DeterministicEmbeddingProvider


def test_v2_async_api_exposes_observable_job_lifecycle_without_blocking_on_embedding() -> (
    None
):
    async def exercise() -> tuple[httpx.Response, ...]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            provider = DeterministicEmbeddingProvider()
            application = create_app(
                _settings(root),
                embedding_provider=provider,
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    accepted = await client.post(
                        "/api/v2/documents",
                        files={
                            "file": (
                                "policy.txt",
                                b"Quarterly access reviews are mandatory.",
                                "text/plain",
                            )
                        },
                    )
                    accepted_body = accepted.json()
                    job_id = accepted_body["job_id"]
                    document_id = accepted_body["document_id"]
                    pending_job = await client.get(f"/api/v2/jobs/{job_id}")
                    processing_document = await client.get(
                        f"/api/v1/documents/{document_id}"
                    )
                    rejected_delete = await client.delete(
                        f"/api/v1/documents/{document_id}"
                    )
                    assert provider.embedded_document_batches == []

                    processor = IngestionProcessor(
                        vector_store=application.state.vector_store,
                        embedding_provider=provider,
                        upload_dir=root / "uploads",
                        chunk_size=80,
                        chunk_overlap=10,
                    )
                    worker = IngestionWorker(
                        document_repository=application.state.document_repository,
                        ingestion_job_repository=(
                            application.state.ingestion_job_repository
                        ),
                        processor=processor,
                        upload_dir=root / "uploads",
                        poll_interval_seconds=0.01,
                    )
                    processed = await asyncio.to_thread(worker.process_next)
                    assert processed
                    ready_job = await client.get(f"/api/v2/jobs/{job_id}")
                    ready_document = await client.get(
                        f"/api/v1/documents/{document_id}"
                    )
                    deletion = await client.delete(f"/api/v1/documents/{document_id}")
                    deleted_job = await client.get(f"/api/v2/jobs/{job_id}")
                    missing_job = await client.get(
                        "/api/v2/jobs/00000000-0000-0000-0000-000000000000"
                    )
                    return (
                        accepted,
                        pending_job,
                        processing_document,
                        rejected_delete,
                        ready_job,
                        ready_document,
                        deletion,
                        deleted_job,
                        missing_job,
                    )

    responses = asyncio.run(exercise())
    (
        accepted,
        pending_job,
        processing_document,
        rejected_delete,
        ready_job,
        ready_document,
        deletion,
        deleted_job,
        missing_job,
    ) = responses

    assert accepted.status_code == 202
    accepted_body = accepted.json()
    assert accepted_body["document_status"] == "processing"
    assert accepted_body["job_status"] == "pending"
    assert accepted_body["status_url"] == f"/api/v2/jobs/{accepted_body['job_id']}"
    assert pending_job.status_code == 200
    assert pending_job.json()["status"] == "pending"
    assert pending_job.json()["attempt_count"] == 0
    assert processing_document.json()["status"] == "processing"
    assert rejected_delete.status_code == 409
    assert rejected_delete.json()["error"]["code"] == "DOCUMENT_PROCESSING"
    assert ready_job.json()["status"] == "ready"
    assert ready_job.json()["attempt_count"] == 1
    assert ready_document.json()["status"] == "ready"
    assert ready_document.json()["chunk_count"] == 1
    assert deletion.status_code == 204
    assert deleted_job.status_code == 404
    assert deleted_job.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert missing_job.status_code == 404
    assert missing_job.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_v2_duplicate_sha_returns_existing_conflict_contract_without_orphan_file() -> (
    None
):
    async def exercise() -> tuple[httpx.Response, httpx.Response, int, int]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(
                _settings(root),
                embedding_provider=DeterministicEmbeddingProvider(),
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    first = await client.post(
                        "/api/v2/documents",
                        files={"file": ("first.txt", b"same", "text/plain")},
                    )
                    duplicate = await client.post(
                        "/api/v2/documents",
                        files={"file": ("second.txt", b"same", "text/plain")},
                    )
                    file_count = len(list((root / "uploads").glob("*")))
                    document_count = len(application.state.document_repository.list())
                    return first, duplicate, file_count, document_count

    first, duplicate, file_count, document_count = asyncio.run(exercise())

    assert first.status_code == 202
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DOCUMENT_CONFLICT"
    assert file_count == 1
    assert document_count == 1


def _settings(root: Path) -> Settings:
    return Settings(
        sqlite_path=root / "app.db",
        qdrant_path=root / "qdrant",
        upload_dir=root / "uploads",
        qdrant_collection="async_api_chunks",
        embedding_dimensions=3,
        max_upload_bytes=4096,
        chunk_size=80,
        chunk_overlap=10,
    )
