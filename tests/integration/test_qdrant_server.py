import os
import time
from hashlib import sha256
from urllib.request import urlopen
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.domain.models import Chunk
from app.storage.qdrant_vector_store import QdrantVectorStore

QDRANT_SERVER_URL = os.environ.get("RAG_TEST_QDRANT_URL")

pytestmark = pytest.mark.skipif(
    not QDRANT_SERVER_URL,
    reason="RAG_TEST_QDRANT_URL is required for the Qdrant Server test",
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


def test_server_mode_round_trip_and_delete() -> None:
    assert QDRANT_SERVER_URL is not None
    _wait_until_ready(QDRANT_SERVER_URL)
    collection_name = f"r1_test_{uuid4().hex}"
    document_id = uuid4()
    text = "server-backed evidence"
    chunk = Chunk(
        chunk_id=uuid4(),
        document_id=document_id,
        chunk_index=0,
        text=text,
        filename="server.txt",
        page_number=None,
        content_hash=sha256(text.encode("utf-8")).hexdigest(),
    )
    store = QdrantVectorStore(
        storage_path=None,
        url=QDRANT_SERVER_URL,
        collection_name=collection_name,
        vector_size=3,
    )
    cleanup_client = QdrantClient(url=QDRANT_SERVER_URL)
    try:
        store.initialize()
        assert store.health()
        store.upsert([chunk], [[1.0, 0.0, 0.0]])

        results = store.search([1.0, 0.0, 0.0], [document_id], limit=1)

        assert [result.chunk_id for result in results] == [chunk.chunk_id]
        store.delete_by_document(document_id)
        assert store.search([1.0, 0.0, 0.0], [document_id], limit=1) == []
    finally:
        store.close()
        cleanup_client.delete_collection(collection_name=collection_name)
        cleanup_client.close()
