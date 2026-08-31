import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from anyio import to_thread
from pypdf import PdfWriter

from app.knowledge.errors import (
    DocumentExtractionError,
    KnowledgeFileTooLargeError,
    KnowledgeInvalidDocumentError,
    KnowledgeUnsupportedMediaTypeError,
)
from app.knowledge.extraction import (
    DocumentExtractor,
    default_document_title,
    safe_upload_filename,
    stage_upload,
)
from app.knowledge.models import ValidatedUpload


class FakeUpload:
    def __init__(self, filename: str | None, content_type: str | None, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self, size: int = -1) -> bytes:
        if not self._content:
            return b""
        chunk = self._content[:size]
        self._content = self._content[size:]
        return chunk


def _minimal_text_pdf(text: str = "Hello knowledge") -> bytes:
    stream = f"BT /F1 12 Tf 72 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode())
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(document)


def _validated(path: Path, media_type: str) -> ValidatedUpload:
    return ValidatedUpload(
        temporary_path=str(path),
        original_filename=path.name,
        media_type=media_type,
        size_bytes=path.stat().st_size,
        sha256="a" * 64,
    )


def test_upload_filename_and_default_title_are_safe() -> None:
    assert safe_upload_filename(r"C:\fakepath\support-guide.md") == "support-guide.md"
    assert default_document_title("support_guide-final.md") == "support guide final"
    assert len(default_document_title(f"{'a' * 250}.txt")) == 200
    for value in (None, "", "bad\x00name.txt", f"{'a' * 256}.txt"):
        with pytest.raises(KnowledgeInvalidDocumentError):
            safe_upload_filename(value)
    with pytest.raises(KnowledgeInvalidDocumentError):
        default_document_title("-.txt")


def test_stage_upload_validates_and_hashes_supported_files() -> None:
    async def exercise() -> None:
        for filename, media_type, content, expected_type in [
            ("notes.txt", "text/plain", b"Text", "text/plain"),
            ("notes.md", "text/plain; charset=utf-8", b"# Notes", "text/markdown"),
            ("guide.pdf", "application/pdf", _minimal_text_pdf(), "application/pdf"),
        ]:
            staged = await stage_upload(
                FakeUpload(filename, media_type, content), maximum_bytes=10_000
            )
            try:
                assert staged.media_type == expected_type
                assert staged.size_bytes == len(content)
                assert len(staged.sha256) == 64
                assert await to_thread.run_sync(Path(staged.temporary_path).read_bytes) == content
            finally:
                await to_thread.run_sync(Path(staged.temporary_path).unlink)

    asyncio.run(exercise())


def test_stage_upload_streams_multiple_chunks() -> None:
    class ChunkedUpload:
        filename: str | None = "notes.txt"
        content_type: str | None = "text/plain"

        def __init__(self) -> None:
            self.chunks = [b"hello", b" world"]

        async def read(self, size: int = -1) -> bytes:
            del size
            return self.chunks.pop(0) if self.chunks else b""

    async def exercise() -> None:
        staged = await stage_upload(ChunkedUpload(), maximum_bytes=100)
        try:
            assert staged.size_bytes == 11
        finally:
            await to_thread.run_sync(Path(staged.temporary_path).unlink)

    asyncio.run(exercise())


def test_stage_upload_rejects_unsupported_empty_large_and_invalid_pdf() -> None:
    async def exercise() -> None:
        with pytest.raises(KnowledgeUnsupportedMediaTypeError):
            await stage_upload(
                FakeUpload("guide.docx", "application/octet-stream", b"content"),
                maximum_bytes=100,
            )
        with pytest.raises(KnowledgeUnsupportedMediaTypeError):
            await stage_upload(
                FakeUpload("guide.pdf", "text/plain", _minimal_text_pdf()),
                maximum_bytes=10_000,
            )
        with pytest.raises(KnowledgeInvalidDocumentError):
            await stage_upload(FakeUpload("empty.txt", "text/plain", b""), maximum_bytes=100)
        with pytest.raises(KnowledgeFileTooLargeError):
            await stage_upload(FakeUpload("large.txt", "text/plain", b"large"), maximum_bytes=4)
        with pytest.raises(KnowledgeInvalidDocumentError):
            await stage_upload(
                FakeUpload("fake.pdf", "application/pdf", b"not pdf"), maximum_bytes=100
            )

    asyncio.run(exercise())


def test_text_and_markdown_extraction(tmp_path: Path) -> None:
    extractor = DocumentExtractor(maximum_pdf_pages=100)
    text_path = tmp_path / "notes.txt"
    text_path.write_bytes(b"First  \r\nSecond")
    markdown_path = tmp_path / "notes.md"
    markdown_path.write_text("# Heading")

    async def exercise() -> None:
        text_result = await extractor.extract(_validated(text_path, "text/plain"))
        markdown_result = await extractor.extract(_validated(markdown_path, "text/markdown"))
        assert text_result.normalized_text == "First\nSecond"
        assert text_result.extractor_name == "plain_text"
        assert markdown_result.extractor_name == "markdown"
        assert markdown_result.locator_map["schema_version"] == 1

    asyncio.run(exercise())


def test_text_extraction_reports_safe_failures(tmp_path: Path) -> None:
    extractor = DocumentExtractor(maximum_pdf_pages=100)
    invalid_utf8 = tmp_path / "invalid.txt"
    invalid_utf8.write_bytes(b"\xff")
    empty = tmp_path / "empty.txt"
    empty.write_text(" \n")
    oversized = tmp_path / "large.txt"
    oversized.write_text("a" * 2_000_001)

    for path, code in [
        (invalid_utf8, "text_decode_failed"),
        (empty, "no_extractable_text"),
        (oversized, "normalized_content_too_large"),
    ]:
        with pytest.raises(DocumentExtractionError) as raised:
            asyncio.run(extractor.extract(_validated(path, "text/plain")))
        assert raised.value.code == code


def test_pdf_extraction_preserves_page_locator(tmp_path: Path) -> None:
    pdf_path = tmp_path / "guide.pdf"
    pdf_path.write_bytes(_minimal_text_pdf())
    extractor = DocumentExtractor(maximum_pdf_pages=100)

    extracted = asyncio.run(extractor.extract(_validated(pdf_path, "application/pdf")))

    assert "Hello knowledge" in extracted.normalized_text
    assert extracted.extractor_name == "pypdf"
    assert extracted.locator_map["segments"] == [
        {
            "kind": "page",
            "page": 1,
            "start": 0,
            "end": len(extracted.normalized_text),
        }
    ]


def test_pdf_extraction_separates_multiple_text_pages(tmp_path: Path) -> None:
    class Page:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    pdf_path = tmp_path / "guide.pdf"
    pdf_path.write_bytes(b"%PDF-placeholder")
    reader = SimpleNamespace(is_encrypted=False, pages=[Page("First"), Page("Second")])

    with patch("app.knowledge.extraction.PdfReader", return_value=reader):
        extracted = asyncio.run(
            DocumentExtractor(maximum_pdf_pages=100).extract(
                _validated(pdf_path, "application/pdf")
            )
        )

    assert extracted.normalized_text == "First\n\nSecond"
    segments = cast(list[dict[str, object]], extracted.locator_map["segments"])
    assert segments[1]["start"] == 7


def test_pdf_extraction_reports_encryption_page_empty_size_and_parse_failures(
    tmp_path: Path,
) -> None:
    encrypted_path = tmp_path / "encrypted.pdf"
    encrypted_writer = PdfWriter()
    encrypted_writer.add_blank_page(width=100, height=100)
    encrypted_writer.encrypt("password")
    with encrypted_path.open("wb") as stream:
        encrypted_writer.write(stream)

    pages_path = tmp_path / "pages.pdf"
    pages_writer = PdfWriter()
    pages_writer.add_blank_page(width=100, height=100)
    pages_writer.add_blank_page(width=100, height=100)
    with pages_path.open("wb") as stream:
        pages_writer.write(stream)

    empty_path = tmp_path / "empty.pdf"
    empty_writer = PdfWriter()
    empty_writer.add_blank_page(width=100, height=100)
    with empty_path.open("wb") as stream:
        empty_writer.write(stream)

    corrupt_path = tmp_path / "corrupt.pdf"
    corrupt_path.write_bytes(b"%PDF-corrupt")
    text_path = tmp_path / "large.pdf"
    text_path.write_bytes(_minimal_text_pdf())

    cases = [
        (DocumentExtractor(maximum_pdf_pages=100), encrypted_path, "encrypted_pdf"),
        (DocumentExtractor(maximum_pdf_pages=1), pages_path, "pdf_page_limit_exceeded"),
        (DocumentExtractor(maximum_pdf_pages=100), empty_path, "no_extractable_text"),
        (DocumentExtractor(maximum_pdf_pages=100), corrupt_path, "invalid_document"),
    ]
    for extractor, path, code in cases:
        with pytest.raises(DocumentExtractionError) as raised:
            asyncio.run(extractor.extract(_validated(path, "application/pdf")))
        assert raised.value.code == code

    with (
        patch("app.knowledge.extraction.MAX_NORMALIZED_CHARACTERS", 5),
        pytest.raises(DocumentExtractionError) as raised,
    ):
        asyncio.run(
            DocumentExtractor(maximum_pdf_pages=100).extract(
                _validated(text_path, "application/pdf")
            )
        )
    assert raised.value.code == "normalized_content_too_large"
