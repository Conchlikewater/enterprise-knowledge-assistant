import asyncio
import tempfile
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.exceptions import AnswerProviderError
from app.document_processing.file_validation import build_storage_path
from app.domain.models import Document, DocumentStatus
from app.main import create_app
from app.providers.llm_provider import LLMProvider
from app.services.answer_service import NO_EVIDENCE_ANSWER
from tests.fakes import DeterministicEmbeddingProvider, DeterministicLLMProvider


class FailingLLMProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "failing-test"

    @property
    def model(self) -> str:
        return "failing-test-model"

    def generate_answer(
        self,
        question: str,
        context_blocks: Sequence[str],
    ) -> str:
        raise AnswerProviderError()

    def close(self) -> None:
        pass


def test_answer_api_returns_grounded_application_built_citations() -> None:
    async def exercise() -> tuple[httpx.Response, DeterministicLLMProvider, str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            llm = DeterministicLLMProvider(
                "Privileged access is reviewed quarterly [1]."
            )
            application = create_app(
                _settings(root),
                embedding_provider=DeterministicEmbeddingProvider(),
                llm_provider=llm,
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    upload = await _upload(
                        client,
                        "access-policy.txt",
                        b"Privileged access is reviewed every quarter.",
                    )
                    document_id = upload.json()["document_id"]
                    response = await client.post(
                        "/api/v1/answers",
                        json={
                            "question": "How often is privileged access reviewed?",
                            "document_ids": [document_id],
                            "top_k": 5,
                        },
                    )
            assert llm.closed
            return response, llm, document_id

    response, llm, document_id = asyncio.run(exercise())

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Privileged access is reviewed quarterly [1]."
    assert body["retrieval_count"] == 1
    assert len(body["citations"]) == 1
    citation = body["citations"][0]
    assert citation["citation_number"] == 1
    assert citation["filename"] == "access-policy.txt"
    assert citation["document_id"] == document_id
    assert document_id not in llm.calls[0][1][0]
    assert "Privileged access" in citation["excerpt"]
    assert "stored_path" not in body
    assert "question" not in body


def test_answer_api_returns_no_evidence_without_calling_llm() -> None:
    async def exercise() -> tuple[httpx.Response, DeterministicLLMProvider]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            llm = DeterministicLLMProvider()
            application = create_app(
                _settings(root),
                embedding_provider=DeterministicEmbeddingProvider(),
                llm_provider=llm,
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                document_id = uuid4()
                application.state.document_repository.create(
                    Document(
                        document_id=document_id,
                        filename="empty-index.txt",
                        media_type="text/plain",
                        size_bytes=10,
                        sha256="d" * 64,
                        status=DocumentStatus.READY,
                        stored_path=build_storage_path(
                            root / "uploads",
                            document_id,
                            ".txt",
                        ),
                        chunk_count=1,
                    )
                )
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    response = await client.post(
                        "/api/v1/answers",
                        json={
                            "question": "What evidence exists?",
                            "document_ids": [str(document_id)],
                        },
                    )
            return response, llm

    response, llm = asyncio.run(exercise())

    assert response.status_code == 200
    assert response.json() == {
        "answer": NO_EVIDENCE_ANSWER,
        "citations": [],
        "retrieval_count": 0,
    }
    assert llm.calls == []


def test_answer_api_maps_llm_failure_and_missing_configuration() -> None:
    async def llm_failure() -> httpx.Response:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(
                _settings(root),
                embedding_provider=DeterministicEmbeddingProvider(),
                llm_provider=FailingLLMProvider(),
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    upload = await _upload(
                        client,
                        "failure.txt",
                        b"Evidence that reaches the failing answer provider.",
                    )
                    return await client.post(
                        "/api/v1/answers",
                        json={
                            "question": "What does the evidence say?",
                            "document_ids": [upload.json()["document_id"]],
                        },
                    )

    async def missing_configuration() -> httpx.Response:
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
                    return await client.post(
                        "/api/v1/answers",
                        json={
                            "question": "question",
                            "document_ids": [str(uuid4())],
                        },
                    )

    failed = asyncio.run(llm_failure())
    unconfigured = asyncio.run(missing_configuration())

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "ANSWER_PROVIDER_ERROR"
    assert unconfigured.status_code == 503
    assert unconfigured.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_answer_request_validation_uses_stable_error_contract() -> None:
    async def exercise() -> tuple[httpx.Response, httpx.Response]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(
                _settings(root),
                embedding_provider=DeterministicEmbeddingProvider(),
                llm_provider=DeterministicLLMProvider(),
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    document_id = str(uuid4())
                    blank = await client.post(
                        "/api/v1/answers",
                        json={"question": "   ", "document_ids": [document_id]},
                    )
                    duplicate = await client.post(
                        "/api/v1/answers",
                        json={
                            "question": "question",
                            "document_ids": [document_id, document_id],
                        },
                    )
                    return blank, duplicate

    blank, duplicate = asyncio.run(exercise())

    for response in (blank, duplicate):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


async def _upload(
    client: httpx.AsyncClient,
    filename: str,
    content: bytes,
) -> httpx.Response:
    response = await client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201
    return response


def _settings(root: Path) -> Settings:
    return Settings(
        sqlite_path=root / "app.db",
        qdrant_path=root / "qdrant",
        upload_dir=root / "uploads",
        qdrant_collection="answers_api_test_chunks",
        embedding_dimensions=3,
        max_upload_bytes=4096,
        chunk_size=100,
        chunk_overlap=10,
    )
