import logging

import pytest

from app.core.logging import configure_logging


def test_logging_configuration_is_scoped_and_idempotent() -> None:
    application_logger = logging.getLogger("app")
    unrelated_logger = logging.getLogger("portfolio-test-unrelated")
    original_unrelated_level = unrelated_logger.level

    configured = configure_logging("DEBUG")
    configure_logging("INFO")
    marked_handlers = [
        handler
        for handler in configured.handlers
        if getattr(handler, "_rag_v1_handler", False)
    ]

    assert configured is application_logger
    assert configured.level == logging.INFO
    assert configured.propagate is False
    assert len(marked_handlers) == 1
    assert unrelated_logger.level == original_unrelated_level


def test_logging_configuration_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="log level is not supported"):
        configure_logging("TRACE")
