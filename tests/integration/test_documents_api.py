import asyncio
import tempfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.config import Settings
from app.main import create_app
from tests.fakes import DeterministicEmbeddingProvider


def test_document_api_full_txt_lifecycle() -> None:
    async def exercise() -> tuple[httpx.Response, ...]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            provider = DeterministicEmbeddingProvider()
            application = create_app(_settings(root), embedding_provider=provider)
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    upload = await client.post(
                        "/api/v1/documents",
                        files={
                            "file": (
                                "policy.txt",
                                b"Quarterly access reviews are mandatory.",
                                "text/plain",
                            )
                        },
                    )
                    document_id = upload.json()["document_id"]
                    listing = await client.get("/api/v1/documents")
                    detail = await client.get(f"/api/v1/documents/{document_id}")
                    deletion = await client.delete(f"/api/v1/documents/{document_id}")
                    missing = await client.get(f"/api/v1/documents/{document_id}")
                    empty_listing = await client.get("/api/v1/documents")
            assert provider.closed
            assert not list((root / "uploads").glob("*"))
            return upload, listing, detail, deletion, missing, empty_listing

    upload, listing, detail, deletion, missing, empty_listing = asyncio.run(exercise())

    assert upload.status_code == 201
    body = upload.json()
    assert body["filename"] == "policy.txt"
    assert body["status"] == "ready"
    assert body["chunk_count"] == 1
    assert body["sha256"] == sha256(
        b"Quarterly access reviews are mandatory."
    ).hexdigest()
    assert "stored_path" not in body
    assert upload.headers["X-Request-ID"]

    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["documents"][0]["document_id"] == body["document_id"]
    assert detail.status_code == 200
    assert detail.json() == body
    assert deletion.status_code == 204
    assert deletion.content == b""
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
    assert empty_listing.json() == {"documents": [], "count": 0}


def test_pdf_upload_preserves_public_metadata() -> None:
    async def exercise() -> httpx.Response:
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
                        "/api/v1/documents",
                        files={
                            "file": (
                                "evidence.pdf",
                                _make_text_pdf("PDF evidence"),
                                "application/pdf",
                            )
                        },
                    )

    response = asyncio.run(exercise())

    assert response.status_code == 201
    assert response.json()["filename"] == "evidence.pdf"
    assert response.json()["media_type"] == "application/pdf"
    assert response.json()["status"] == "ready"


def test_upload_errors_keep_the_stable_contract() -> None:
    async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(
                _settings(root, max_upload_bytes=12),
                embedding_provider=DeterministicEmbeddingProvider(),
            )
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    unsupported = await client.post(
                        "/api/v1/documents",
                        files={"file": ("notes.md", b"content", "text/markdown")},
                        headers={"X-Request-ID": "safe-test-request"},
                    )
                    oversized = await client.post(
                        "/api/v1/documents",
                        files={"file": ("large.txt", b"x" * 13, "text/plain")},
                    )
                    first = await client.post(
                        "/api/v1/documents",
                        files={"file": ("first.txt", b"same content", "text/plain")},
                    )
                    duplicate = await client.post(
                        "/api/v1/documents",
                        files={"file": ("second.txt", b"same content", "text/plain")},
                    )
                    assert first.status_code == 201
                    return unsupported, oversized, duplicate

    unsupported, oversized, duplicate = asyncio.run(exercise())

    assert unsupported.status_code == 415
    assert unsupported.headers["X-Request-ID"] == "safe-test-request"
    assert unsupported.json()["error"] == {
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": "Only supported TXT and PDF files can be uploaded.",
        "request_id": "safe-test-request",
    }
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DOCUMENT_CONFLICT"


def test_missing_provider_reports_service_unavailable_without_crashing_startup() -> None:
    async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            application = create_app(_settings(root))
            transport = httpx.ASGITransport(app=application)
            async with application.router.lifespan_context(application):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    health = await client.get("/health")
                    upload = await client.post(
                        "/api/v1/documents",
                        files={"file": ("notes.txt", b"content", "text/plain")},
                    )
                    listing = await client.get("/api/v1/documents")
                    return health, upload, listing

    health, upload, listing = asyncio.run(exercise())

    assert health.status_code == 503
    assert health.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    assert upload.status_code == 503
    assert upload.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    assert listing.status_code == 200
    assert listing.json() == {"documents": [], "count": 0}


def _settings(root: Path, max_upload_bytes: int = 4096) -> Settings:
    return Settings(
        sqlite_path=root / "app.db",
        qdrant_path=root / "qdrant",
        upload_dir=root / "uploads",
        qdrant_collection="api_test_chunks",
        embedding_dimensions=3,
        max_upload_bytes=max_upload_bytes,
        chunk_size=80,
        chunk_overlap=10,
    )


def _make_text_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    target = BytesIO()
    writer.write(target)
    return target.getvalue()
