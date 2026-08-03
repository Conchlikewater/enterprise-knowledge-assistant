import unittest

from app.core.exceptions import (
    DocumentNotFoundError,
    DocumentStorageError,
    EmbeddingProviderError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFilenameError,
    UnsupportedFileTypeError,
    VectorStoreError,
)


class ExceptionContractTests(unittest.TestCase):
    def test_exception_status_mapping(self) -> None:
        cases = (
            (DocumentNotFoundError(), 404),
            (EmptyFileError(), 400),
            (InvalidFilenameError(), 400),
            (DocumentStorageError(), 500),
            (FileTooLargeError(), 413),
            (UnsupportedFileTypeError(), 415),
            (EmbeddingProviderError(), 502),
            (VectorStoreError(), 503),
        )

        for error, expected_status in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(error.status_code, expected_status)
                self.assertTrue(error.code)
                self.assertTrue(error.safe_message)


if __name__ == "__main__":
    unittest.main()
