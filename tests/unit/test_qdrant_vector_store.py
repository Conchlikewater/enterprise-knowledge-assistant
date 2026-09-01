from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.storage.qdrant_vector_store import QdrantVectorStore


def test_connection_mode_must_be_unambiguous() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        QdrantVectorStore(
            storage_path=None,
            url=None,
            collection_name="chunks",
            vector_size=3,
        )

    with pytest.raises(ValueError, match="exactly one"):
        QdrantVectorStore(
            storage_path=Path("data/qdrant"),
            url="http://qdrant:6333",
            collection_name="chunks",
            vector_size=3,
        )


def test_server_mode_builds_remote_client_without_creating_local_path() -> None:
    client = Mock()
    client.collection_exists.return_value = False
    with patch(
        "app.storage.qdrant_vector_store.QdrantClient", return_value=client
    ) as client_type:
        store = QdrantVectorStore(
            storage_path=None,
            url="http://qdrant:6333/",
            api_key="test-key",
            timeout_seconds=7.5,
            collection_name="chunks",
            vector_size=3,
        )
        store.initialize()

    client_type.assert_called_once_with(
        url="http://qdrant:6333",
        api_key="test-key",
        timeout=7.5,
    )
    client.create_collection.assert_called_once()


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        QdrantVectorStore(
            storage_path=None,
            url="http://qdrant:6333",
            timeout_seconds=0,
            collection_name="chunks",
            vector_size=3,
        )
