"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.routers.health import router as health_router
from app.core.config import Settings
from app.core.error_handlers import register_error_handlers
from app.storage.sqlite_document_repository import SQLiteDocumentRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    document_repository = SQLiteDocumentRepository(resolved_settings.sqlite_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        document_repository.initialize()
        application.state.document_repository = document_repository
        yield

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Local, document-scoped RAG API.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_error_handlers(application)
    application.include_router(health_router)
    return application


app = create_app()
