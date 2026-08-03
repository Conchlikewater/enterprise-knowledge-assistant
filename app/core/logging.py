"""Small, idempotent logging setup for privacy-safe application events."""

from __future__ import annotations

import logging

_HANDLER_MARKER = "_rag_v1_handler"
_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"


def configure_logging(level_name: str) -> logging.Logger:
    """Configure only the application logger without changing host loggers."""

    level = logging.getLevelNamesMapping().get(level_name.upper())
    if not isinstance(level, int):
        raise ValueError("log level is not supported")

    application_logger = logging.getLogger("app")
    application_logger.setLevel(level)
    application_logger.propagate = False

    handler = next(
        (
            existing
            for existing in application_logger.handlers
            if getattr(existing, _HANDLER_MARKER, False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        setattr(handler, _HANDLER_MARKER, True)
        application_logger.addHandler(handler)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    return application_logger
