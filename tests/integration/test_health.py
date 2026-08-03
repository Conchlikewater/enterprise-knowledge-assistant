import asyncio
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")
pytest.importorskip("httpx")

import httpx

from app.core.config import Settings
from app.main import create_app
from tests.fakes import DeterministicEmbeddingProvider, DeterministicLLMProvider


def test_health_endpoint() -> None:
    async def send_request() -> httpx.Response:
        with tempfile.TemporaryDirectory() as temporary_directory:
            application = create_app(
                Settings(
                    app_name="Test Assistant",
                    sqlite_path=Path(temporary_directory) / "app.db",
                    qdrant_path=Path(temporary_directory) / "qdrant",
                    upload_dir=Path(temporary_directory) / "uploads",
                    embedding_dimensions=3,
                ),
                embedding_provider=DeterministicEmbeddingProvider(),
                llm_provider=DeterministicLLMProvider(),
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    return await client.get("/health")

    response = asyncio.run(send_request())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Test Assistant",
        "version": "0.1.0",
        "components": {
            "application": "ok",
            "document_repository": "ok",
            "vector_store": "ok",
            "embedding_provider": "configured",
            "llm_provider": "configured",
        },
    }
    assert response.headers["X-Request-ID"]
