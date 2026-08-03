import asyncio
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.exceptions import EmbeddingProviderError
from app.main import create_app
from tests.fakes import DeterministicEmbeddingProvider


class QueryFailingEmbeddingProvider(DeterministicEmbeddingProvider):
    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingProviderError()


def test_search_api_enforces_single_and_multi_document_scope() -> None:
    async def exercise() -> tuple[httpx.Response, httpx.Response, str, str]:
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
                    first = await _upload(
                        client,
                        "finance.txt",
                        b"Finance evidence: invoices require approval.",
                    )
                    second = await _upload(
                        client,
                        "security.txt",
                        b"Security evidence: access reviews occur quarterly.",
                    )
                    first_id = first.json()["document_id"]
                    second_id = second.json()["document_id"]
                    single_scope = await client.post(
                        "/api/v1/search",
                        json={
                            "query": "What approval is required?",
                            "document_ids": [first_id],
                            "top_k": 10,
                        },
                    )
                    multi_scope = await client.post(
                        "/api/v1/search",
                        json={
                            "query": "What controls are described?",
                            "document_ids": [first_id, second_id],
                            "top_k": 10,
                        },
                    )
                    return single_scope, multi_scope, first_id, second_id

    single_scope, multi_scope, first_id, second_id = asyncio.run(exercise())

    assert single_scope.status_code == 200
    assert single_scope.json()["count"] == 1
    assert single_scope.json()["searched_document_ids"] == [first_id]
    assert {item["document_id"] for item in single_scope.json()["results"]} == {
        first_id
    }
    assert "query" not in single_scope.json()

    assert multi_scope.status_code == 200
    assert multi_scope.json()["count"] == 2
    assert set(multi_scope.json()["searched_document_ids"]) == {first_id, second_id}
    assert {item["document_id"] for item in multi_scope.json()["results"]} == {
        first_id,
        second_id,
    }


def test_search_api_maps_document_state_and_schema_errors() -> None:
    async def exercise() -> tuple[httpx.Response, ...]:
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
                    blank_upload = await _upload(client, "blank.txt", b"   \n")
                    assert blank_upload.status_code == 400
                    listing = await client.get("/api/v1/documents")
                    failed_id = listing.json()["documents"][0]["document_id"]
                    not_ready = await client.post(
                        "/api/v1/search",
                        json={"query": "question", "document_ids": [failed_id]},
                    )
                    missing = await client.post(
                        "/api/v1/search",
                        json={"query": "question", "document_ids": [str(uuid4())]},
                    )
                    duplicate_ids = await client.post(
                        "/api/v1/search",
                        json={
                            "query": "question",
                            "document_ids": [failed_id, failed_id],
                        },
                    )
                    blank_query = await client.post(
                        "/api/v1/search",
                        json={"query": "   ", "document_ids": [failed_id]},
                    )
                    invalid_top_k = await client.post(
                        "/api/v1/search",
                        json={
                            "query": "question",
                            "document_ids": [failed_id],
                            "top_k": 51,
                        },
                    )
                    return (
                        not_ready,
                        missing,
                        duplicate_ids,
                        blank_query,
                        invalid_top_k,
                    )

    not_ready, missing, duplicate_ids, blank_query, invalid_top_k = asyncio.run(
        exercise()
    )

    assert not_ready.status_code == 409
    assert not_ready.json()["error"]["code"] == "DOCUMENT_NOT_READY"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
    for response in (duplicate_ids, blank_query, invalid_top_k):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


def test_search_api_maps_provider_failure_and_missing_configuration() -> None:
    async def provider_failure() -> httpx.Response:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(
                _settings(root),
                embedding_provider=QueryFailingEmbeddingProvider(),
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    uploaded = await _upload(
                        client,
                        "provider.txt",
                        b"Provider failure test evidence.",
                    )
                    document_id = uploaded.json()["document_id"]
                    return await client.post(
                        "/api/v1/search",
                        json={"query": "question", "document_ids": [document_id]},
                    )

    async def missing_configuration() -> httpx.Response:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(_settings(root))
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    return await client.post(
                        "/api/v1/search",
                        json={"query": "question", "document_ids": [str(uuid4())]},
                    )

    failed = asyncio.run(provider_failure())
    unconfigured = asyncio.run(missing_configuration())

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "EMBEDDING_PROVIDER_ERROR"
    assert unconfigured.status_code == 503
    assert unconfigured.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


async def _upload(
    client: httpx.AsyncClient,
    filename: str,
    content: bytes,
) -> httpx.Response:
    return await client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "text/plain")},
    )


def _settings(root: Path) -> Settings:
    return Settings(
        sqlite_path=root / "app.db",
        qdrant_path=root / "qdrant",
        upload_dir=root / "uploads",
        qdrant_collection="retrieval_api_test_chunks",
        embedding_dimensions=3,
        max_upload_bytes=4096,
        chunk_size=100,
        chunk_overlap=10,
    )
