import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_match_v1_local_layout(self) -> None:
        settings = Settings.from_env({})

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.upload_dir, Path("data/uploads"))
        self.assertEqual(settings.qdrant_path, Path("data/qdrant"))
        self.assertIsNone(settings.qdrant_url)
        self.assertEqual(settings.qdrant_collection, "knowledge_chunks")
        self.assertEqual(settings.sqlite_busy_timeout_ms, 5000)
        self.assertEqual(settings.worker_poll_interval_seconds, 0.5)
        self.assertEqual(settings.llm_provider, "openai")
        self.assertEqual(settings.llm_model, "gpt-5.6-sol")
        self.assertEqual(settings.llm_reasoning_effort, "low")

    def test_environment_values_are_typed(self) -> None:
        settings = Settings.from_env(
            {
                "RAG_PORT": "9000",
                "RAG_CHUNK_SIZE": "600",
                "RAG_CHUNK_OVERLAP": "60",
                "RAG_LLM_REASONING_EFFORT": "MEDIUM",
                "RAG_LLM_MAX_OUTPUT_TOKENS": "500",
                "RAG_SQLITE_BUSY_TIMEOUT_MS": "750",
                "RAG_WORKER_POLL_INTERVAL_SECONDS": "0.25",
            }
        )

        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.chunk_size, 600)
        self.assertEqual(settings.chunk_overlap, 60)
        self.assertEqual(settings.llm_reasoning_effort, "medium")
        self.assertEqual(settings.llm_max_output_tokens, 500)
        self.assertEqual(settings.sqlite_busy_timeout_ms, 750)
        self.assertEqual(settings.worker_poll_interval_seconds, 0.25)

    def test_qdrant_server_configuration_is_typed_and_hides_key(self) -> None:
        secret = "qdrant-test-secret"
        settings = Settings.from_env(
            {
                "RAG_QDRANT_URL": "http://qdrant:6333/",
                "RAG_QDRANT_API_KEY": secret,
                "RAG_QDRANT_TIMEOUT_SECONDS": "7.5",
            }
        )

        self.assertEqual(settings.qdrant_url, "http://qdrant:6333")
        self.assertEqual(settings.qdrant_api_key, secret)
        self.assertEqual(settings.qdrant_timeout_seconds, 7.5)
        self.assertNotIn(secret, repr(settings))

    def test_deepseek_provider_uses_safe_defaults_and_hides_key(self) -> None:
        secret = "deepseek-test-secret"
        settings = Settings.from_env(
            {
                "RAG_LLM_PROVIDER": "DEEPSEEK",
                "DEEPSEEK_API_KEY": secret,
            }
        )

        self.assertEqual(settings.llm_provider, "deepseek")
        self.assertEqual(settings.llm_model, "deepseek-v4-flash")
        self.assertEqual(settings.llm_reasoning_effort, "none")
        self.assertEqual(settings.deepseek_api_key, secret)
        self.assertNotIn(secret, repr(settings))

    def test_invalid_overlap_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(chunk_size=100, chunk_overlap=100)
        with self.assertRaises(ValueError):
            Settings(sqlite_busy_timeout_ms=0)
        with self.assertRaises(ValueError):
            Settings(worker_poll_interval_seconds=0)

    def test_invalid_llm_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(llm_reasoning_effort="extreme")
        with self.assertRaises(ValueError):
            Settings(llm_max_output_tokens=0)
        with self.assertRaises(ValueError):
            Settings(llm_provider="unsupported")

    def test_invalid_log_level_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(log_level="TRACE")

    def test_invalid_qdrant_server_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Settings(qdrant_url="qdrant:6333")
        with self.assertRaises(ValueError):
            Settings(qdrant_timeout_seconds=0)

    def test_env_file_loads_key_without_exposing_it_in_repr(self) -> None:
        secret = "test-secret-value"
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(env_file=env_file)

        self.assertEqual(settings.openai_api_key, secret)
        self.assertNotIn(secret, repr(settings))

    def test_system_environment_overrides_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text("OPENAI_API_KEY=file-value\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "environment-value"},
                clear=True,
            ):
                settings = Settings.from_env(env_file=env_file)

        self.assertEqual(settings.openai_api_key, "environment-value")


if __name__ == "__main__":
    unittest.main()
