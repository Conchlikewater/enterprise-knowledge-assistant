import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.core.exceptions import ProviderConfigurationError
from app.worker import main, run_worker


class WorkerEntryPointTests(unittest.TestCase):
    def test_missing_embedding_key_is_rejected_before_resources_are_created(
        self,
    ) -> None:
        with self.assertRaises(ProviderConfigurationError):
            run_worker(Settings(openai_api_key=None))

    @patch("app.worker.IngestionWorker")
    @patch("app.worker.IngestionProcessor")
    @patch("app.worker.OpenAIEmbeddingProvider")
    @patch("app.worker.QdrantVectorStore")
    @patch("app.worker.SQLiteDocumentRepository")
    def test_run_worker_initializes_and_closes_owned_resources(
        self,
        repository_type: MagicMock,
        vector_store_type: MagicMock,
        provider_type: MagicMock,
        processor_type: MagicMock,
        worker_type: MagicMock,
    ) -> None:
        settings = Settings(
            openai_api_key="fake-test-key",
            sqlite_path=Path("test.db"),
            qdrant_path=Path("qdrant"),
            embedding_dimensions=3,
        )
        worker_type.return_value.run_forever.side_effect = KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_worker(settings)

        repository_type.return_value.initialize.assert_called_once_with()
        vector_store_type.return_value.initialize.assert_called_once_with()
        processor_type.assert_called_once()
        worker_type.return_value.run_forever.assert_called_once_with()
        provider_type.return_value.close.assert_called_once_with()
        vector_store_type.return_value.close.assert_called_once_with()

    @patch("app.worker.run_worker", side_effect=KeyboardInterrupt)
    @patch("app.worker.Settings.from_env", return_value=Settings())
    def test_main_treats_keyboard_interrupt_as_clean_stop(
        self,
        _settings: MagicMock,
        _run_worker: MagicMock,
    ) -> None:
        self.assertEqual(main(), 0)

    @patch("app.worker.Settings.from_env", return_value=Settings())
    def test_main_reports_missing_provider_without_exposing_a_secret(
        self,
        _settings: MagicMock,
    ) -> None:
        with self.assertLogs("app.worker", level="ERROR") as logs:
            result = main()

        self.assertEqual(result, 1)
        self.assertIn("PROVIDER_NOT_CONFIGURED", logs.output[0])


if __name__ == "__main__":
    unittest.main()
