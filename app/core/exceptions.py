"""Typed application exceptions independent of FastAPI."""

from __future__ import annotations


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"
    message = "The request could not be completed."
    status_code = 500

    def __init__(self) -> None:
        # Public messages are class-level constants so callers cannot
        # accidentally expose raw provider, parser, or filesystem errors.
        self.safe_message = self.message
        super().__init__(self.safe_message)


class DocumentNotFoundError(ApplicationError):
    code = "DOCUMENT_NOT_FOUND"
    message = "The requested document was not found."
    status_code = 404


class UnsupportedFileTypeError(ApplicationError):
    code = "UNSUPPORTED_FILE_TYPE"
    message = "Only supported TXT and PDF files can be uploaded."
    status_code = 415


class FileTooLargeError(ApplicationError):
    code = "FILE_TOO_LARGE"
    message = "The uploaded file exceeds the configured size limit."
    status_code = 413


class EmptyFileError(ApplicationError):
    code = "EMPTY_FILE"
    message = "The uploaded file is empty."
    status_code = 400


class InvalidFilenameError(ApplicationError):
    code = "INVALID_FILENAME"
    message = "The uploaded filename is invalid."
    status_code = 400


class DocumentParseError(ApplicationError):
    code = "DOCUMENT_PARSE_ERROR"
    message = "The document could not be parsed."
    status_code = 400


class DocumentConflictError(ApplicationError):
    code = "DOCUMENT_CONFLICT"
    message = "The document conflicts with an existing record or state."
    status_code = 409


class EmbeddingProviderError(ApplicationError):
    code = "EMBEDDING_PROVIDER_ERROR"
    message = "The embedding provider could not complete the request."
    status_code = 502


class AnswerProviderError(ApplicationError):
    code = "ANSWER_PROVIDER_ERROR"
    message = "The answer provider could not complete the request."
    status_code = 502


class VectorStoreError(ApplicationError):
    code = "VECTOR_STORE_ERROR"
    message = "The vector store is unavailable."
    status_code = 503


class DocumentRepositoryError(ApplicationError):
    code = "DOCUMENT_REPOSITORY_ERROR"
    message = "The document repository is unavailable."
    status_code = 503
