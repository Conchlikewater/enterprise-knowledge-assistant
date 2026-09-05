"""Independent deterministic Worker used only by the R4 evaluation."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from app.services.ingestion_processor import IngestionProcessor
from app.services.ingestion_worker import IngestionWorker
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from evaluation.ingestion_benchmark import ControlledDelayEmbeddingProvider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("serve", "crash", "recover"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--upload-dir", type=Path, required=True)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--vector-size", type=int, required=True)
    parser.add_argument("--chunk-size", type=int, required=True)
    parser.add_argument("--chunk-overlap", type=int, required=True)
    parser.add_argument("--embedding-delay-ms", type=int, required=True)
    parser.add_argument("--poll-interval-ms", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--max-jobs", type=int)
    arguments = parser.parse_args()

    if arguments.mode == "serve" and (
        arguments.max_jobs is None or arguments.max_jobs <= 0
    ):
        parser.error("serve mode requires a positive --max-jobs")

    repository = SQLiteDocumentRepository(arguments.database)
    vector_store = QdrantVectorStore(
        storage_path=None,
        url=arguments.qdrant_url,
        collection_name=arguments.collection,
        vector_size=arguments.vector_size,
    )
    provider = ControlledDelayEmbeddingProvider(
        arguments.vector_size,
        arguments.embedding_delay_ms,
    )
    repository.initialize()
    vector_store.initialize()
    processor = IngestionProcessor(
        vector_store=vector_store,
        embedding_provider=provider,
        upload_dir=arguments.upload_dir,
        chunk_size=arguments.chunk_size,
        chunk_overlap=arguments.chunk_overlap,
    )

    def crash_after_upsert(_) -> None:
        os._exit(91)

    worker = IngestionWorker(
        document_repository=repository,
        ingestion_job_repository=repository,
        processor=processor,
        upload_dir=arguments.upload_dir,
        poll_interval_seconds=arguments.poll_interval_ms / 1000,
        after_upsert_hook=(crash_after_upsert if arguments.mode == "crash" else None),
    )
    try:
        worker.recover_abandoned_jobs()
        if arguments.mode in {"crash", "recover"}:
            return 0 if worker.process_next() else 2

        processed = 0
        deadline = time.monotonic() + arguments.timeout_seconds
        while processed < arguments.max_jobs:
            if time.monotonic() >= deadline:
                return 3
            if worker.process_next():
                processed += 1
            else:
                time.sleep(arguments.poll_interval_ms / 1000)
        return 0
    finally:
        provider.close()
        vector_store.close()


if __name__ == "__main__":
    raise SystemExit(main())
