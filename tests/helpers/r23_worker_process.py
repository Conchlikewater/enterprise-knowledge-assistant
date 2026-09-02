"""Crashable deterministic Worker process for the R23 server integration test."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.services.ingestion_processor import IngestionProcessor
from app.services.ingestion_worker import IngestionWorker
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from tests.fakes import DeterministicEmbeddingProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("crash", "recover"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--upload-dir", type=Path, required=True)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--collection", required=True)
    arguments = parser.parse_args()

    repository = SQLiteDocumentRepository(arguments.database, busy_timeout_ms=1000)
    vector_store = QdrantVectorStore(
        storage_path=None,
        url=arguments.qdrant_url,
        collection_name=arguments.collection,
        vector_size=3,
    )
    provider = DeterministicEmbeddingProvider()
    repository.initialize()
    vector_store.initialize()
    processor = IngestionProcessor(
        vector_store=vector_store,
        embedding_provider=provider,
        upload_dir=arguments.upload_dir,
        chunk_size=32,
        chunk_overlap=5,
    )

    def crash_after_upsert(_) -> None:
        os._exit(91)

    worker = IngestionWorker(
        document_repository=repository,
        ingestion_job_repository=repository,
        processor=processor,
        upload_dir=arguments.upload_dir,
        poll_interval_seconds=0.01,
        after_upsert_hook=(crash_after_upsert if arguments.mode == "crash" else None),
    )
    try:
        worker.recover_abandoned_jobs()
        return 0 if worker.process_next() else 2
    finally:
        provider.close()
        vector_store.close()


if __name__ == "__main__":
    raise SystemExit(main())
