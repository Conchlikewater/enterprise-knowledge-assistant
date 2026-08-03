import tempfile
import unittest
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.exceptions import (
    DocumentParseError,
    DocumentStorageError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFilenameError,
    UnsupportedFileTypeError,
)
from app.document_processing.chunker import chunk_sections
from app.document_processing.file_hash import calculate_sha256
from app.document_processing.file_storage import save_upload_stream
from app.document_processing.file_validation import (
    build_storage_path,
    validate_file,
    validate_file_identity,
)
from app.document_processing.loaders import DocumentSection, load_pdf, load_txt


class FileValidationTests(unittest.TestCase):
    def test_identity_can_be_validated_before_stream_size_is_known(self) -> None:
        result = validate_file_identity("notes.TXT", "text/plain; charset=utf-8")

        self.assertEqual(result.filename, "notes.TXT")
        self.assertEqual(result.suffix, ".txt")
        self.assertEqual(result.media_type, "text/plain")

    def test_valid_txt_metadata_is_normalized(self) -> None:
        result = validate_file("notes.TXT", "text/plain; charset=utf-8", 12, 100)

        self.assertEqual(result.filename, "notes.TXT")
        self.assertEqual(result.suffix, ".txt")
        self.assertEqual(result.media_type, "text/plain")

    def test_unsafe_paths_are_rejected(self) -> None:
        filenames = (
            "../secret.txt",
            "folder/file.txt",
            "folder\\file.txt",
            "C:\\secret.txt",
            "/absolute/file.txt",
            "\\\\server\\share\\file.txt",
        )

        for filename in filenames:
            with self.subTest(filename=filename):
                with self.assertRaises(InvalidFilenameError):
                    validate_file(filename, "text/plain", 10, 100)

    def test_type_size_and_empty_file_failures(self) -> None:
        with self.assertRaises(UnsupportedFileTypeError):
            validate_file("notes.md", "text/markdown", 10, 100)
        with self.assertRaises(UnsupportedFileTypeError):
            validate_file("notes.txt", "application/pdf", 10, 100)
        with self.assertRaises(EmptyFileError):
            validate_file("notes.txt", "text/plain", 0, 100)
        with self.assertRaises(FileTooLargeError):
            validate_file("notes.txt", "text/plain", 101, 100)

    def test_storage_path_uses_document_id_under_upload_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            upload_dir = Path(temporary_directory) / "uploads"
            document_id = uuid4()

            storage_path = build_storage_path(upload_dir, document_id, ".pdf")

            self.assertEqual(storage_path.parent, upload_dir.resolve())
            self.assertEqual(storage_path.name, f"{document_id}.pdf")


class FileHashTests(unittest.TestCase):
    def test_sha256_is_calculated_in_binary_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "content.bin"
            file_path.write_bytes(b"abc")

            result = calculate_sha256(file_path, buffer_size=2)

        self.assertEqual(result, sha256(b"abc").hexdigest())


class FileStorageTests(unittest.TestCase):
    def test_stream_is_bounded_hashed_and_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "uploads" / "document.txt"

            result = save_upload_stream(
                BytesIO(b"streamed content"),
                destination,
                max_upload_bytes=100,
                buffer_size=3,
            )

            self.assertEqual(destination.read_bytes(), b"streamed content")
            self.assertEqual(result.size_bytes, 16)
            self.assertEqual(result.sha256, sha256(b"streamed content").hexdigest())
            self.assertEqual(list(destination.parent.glob("*.part")), [])

    def test_empty_and_oversized_streams_leave_no_file(self) -> None:
        cases = (
            (b"", EmptyFileError),
            (b"too large", FileTooLargeError),
        )
        for content, expected_error in cases:
            with self.subTest(expected_error=expected_error.__name__):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    destination = Path(temporary_directory) / "document.txt"
                    with self.assertRaises(expected_error):
                        save_upload_stream(
                            BytesIO(content),
                            destination,
                            max_upload_bytes=4,
                            buffer_size=2,
                        )
                    self.assertEqual(list(Path(temporary_directory).iterdir()), [])

    def test_existing_destination_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "document.txt"
            destination.write_bytes(b"keep me")

            with self.assertRaises(DocumentStorageError):
                save_upload_stream(
                    BytesIO(b"replacement"),
                    destination,
                    max_upload_bytes=100,
                )

            self.assertEqual(destination.read_bytes(), b"keep me")
            self.assertEqual(list(Path(temporary_directory).iterdir()), [destination])


class LoaderTests(unittest.TestCase):
    def test_txt_loader_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "notes.txt"
            file_path.write_bytes(b"\xef\xbb\xbfHello, knowledge base!\r\n")

            sections = load_txt(file_path)

        self.assertEqual(sections, [DocumentSection("Hello, knowledge base!")])

    def test_invalid_or_empty_txt_is_a_safe_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "notes.txt"
            for content in (b"\xff\xfe", b"   \n"):
                with self.subTest(content=content):
                    file_path.write_bytes(content)
                    with self.assertRaises(DocumentParseError):
                        load_txt(file_path)

    def test_text_pdf_preserves_page_number(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "document.pdf"
            _write_text_pdf(file_path, "PDF evidence")

            sections = load_pdf(file_path)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].page_number, 1)
        self.assertIn("PDF evidence", sections[0].text)

    def test_blank_pdf_is_a_safe_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "blank.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with file_path.open("wb") as target:
                writer.write(target)

            with self.assertRaises(DocumentParseError):
                load_pdf(file_path)

    def test_corrupt_pdf_is_a_safe_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "corrupt.pdf"
            file_path.write_bytes(b"this is not a PDF")

            with self.assertRaises(DocumentParseError) as raised:
                load_pdf(file_path)

        self.assertEqual(str(raised.exception), "The document could not be parsed.")


class ChunkerTests(unittest.TestCase):
    def test_chunks_preserve_scope_order_page_and_hash(self) -> None:
        document_id = uuid4()
        sections = [
            DocumentSection("012345678901234567890123456789", page_number=2),
            DocumentSection("   ", page_number=3),
        ]

        chunks = chunk_sections(
            sections,
            document_id=document_id,
            filename="policy.pdf",
            chunk_size=10,
            chunk_overlap=3,
        )

        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            [chunk.chunk_index for chunk in chunks], list(range(len(chunks)))
        )
        self.assertTrue(all(chunk.document_id == document_id for chunk in chunks))
        self.assertTrue(all(chunk.filename == "policy.pdf" for chunk in chunks))
        self.assertTrue(all(chunk.page_number == 2 for chunk in chunks))
        self.assertTrue(all(len(chunk.text) <= 10 for chunk in chunks))
        self.assertTrue(all(len(chunk.content_hash) == 64 for chunk in chunks))
        self.assertEqual(chunks[0].text[-3:], chunks[1].text[:3])

    def test_invalid_chunk_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            chunk_sections([], uuid4(), "notes.txt", chunk_size=100, chunk_overlap=100)


def _write_text_pdf(file_path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )

    content = DecodedStreamObject()
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped_text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)

    with file_path.open("wb") as target:
        writer.write(target)


if __name__ == "__main__":
    unittest.main()
