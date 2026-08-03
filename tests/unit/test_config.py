import unittest
from pathlib import Path

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_match_v1_local_layout(self) -> None:
        settings = Settings.from_env({})

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.upload_dir, Path("data/uploads"))
        self.assertEqual(settings.qdrant_path, Path("data/qdrant"))
        self.assertEqual(settings.qdrant_collection, "knowledge_chunks")

    def test_environment_values_are_typed(self) -> None:
        settings = Settings.from_env(
            {"RAG_PORT": "9000", "RAG_CHUNK_SIZE": "600", "RAG_CHUNK_OVERLAP": "60"}
        )

        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.chunk_size, 600)
        self.assertEqual(settings.chunk_overlap, 60)

    def test_invalid_overlap_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(chunk_size=100, chunk_overlap=100)


if __name__ == "__main__":
    unittest.main()
