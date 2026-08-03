import unittest

from app.core.exceptions import (
    AnswerProviderError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    DocumentStorageError,
    EmbeddingProviderError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFilenameError,
    ProviderConfigurationError,
    UnsupportedFileTypeError,
    VectorStoreError,
)


class ExceptionContractTests(unittest.TestCase):
    def test_exception_status_mapping(self) -> None:
        cases = (
            (DocumentNotFoundError(), 404),
            (DocumentNotReadyError(), 409),
            (EmptyFileError(), 400),
            (InvalidFilenameError(), 400),
            (DocumentStorageError(), 500),
            (FileTooLargeError(), 413),
            (UnsupportedFileTypeError(), 415),
            (EmbeddingProviderError(), 502),
            (AnswerProviderError(), 502),
            (ProviderConfigurationError(), 503),
            (VectorStoreError(), 503),
        )

        for error, expected_status in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(error.status_code, expected_status)
                self.assertTrue(error.code)
                self.assertTrue(error.safe_message)


if __name__ == "__main__":
    unittest.main()
