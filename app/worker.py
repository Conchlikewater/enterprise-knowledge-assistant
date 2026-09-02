"""Executable entry point for the independent R23 ingestion Worker."""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.core.exceptions import ApplicationError, ProviderConfigurationError
from app.core.logging import configure_logging
from app.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from app.services.ingestion_processor import IngestionProcessor
from app.services.ingestion_worker import IngestionWorker
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository

logger = logging.getLogger(__name__)


def run_worker(settings: Settings) -> None:
    """Initialize Worker-owned resources and process jobs until interrupted."""
    if settings.openai_api_key is None:
        raise ProviderConfigurationError()

    repository = SQLiteDocumentRepository(
        settings.sqlite_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )
    vector_store = QdrantVectorStore(
        storage_path=None if settings.qdrant_url is not None else settings.qdrant_path,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dimensions,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout_seconds=settings.qdrant_timeout_seconds,
    )
    provider = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    try:
        repository.initialize()
        vector_store.initialize()
        processor = IngestionProcessor(
            vector_store=vector_store,
            embedding_provider=provider,
            upload_dir=settings.upload_dir,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        worker = IngestionWorker(
            document_repository=repository,
            ingestion_job_repository=repository,
            processor=processor,
            upload_dir=settings.upload_dir,
            poll_interval_seconds=settings.worker_poll_interval_seconds,
        )
        worker.run_forever()
    finally:
        try:
            provider.close()
        finally:
            vector_store.close()


def main() -> int:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    try:
        run_worker(settings)
    except KeyboardInterrupt:
        logger.info("event=ingestion_worker_stopped reason=keyboard_interrupt")
        return 0
    except ApplicationError as exc:
        logger.error(
            "event=ingestion_worker_start_failed error_code=%s error_type=%s",
            exc.code,
            type(exc).__name__,
        )
        return 1
    except Exception as exc:
        logger.error(
            "event=ingestion_worker_start_failed error_code=INTERNAL_SERVER_ERROR "
            "error_type=%s",
            type(exc).__name__,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
