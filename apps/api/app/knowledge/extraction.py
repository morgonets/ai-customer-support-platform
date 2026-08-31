import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol

import pypdf
from anyio import CapacityLimiter, open_file, to_thread
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.knowledge.errors import (
    DocumentExtractionError,
    KnowledgeContentEmptyError,
    KnowledgeContentTooLargeError,
    KnowledgeFileTooLargeError,
    KnowledgeInvalidDocumentError,
    KnowledgeUnsupportedMediaTypeError,
)
from app.knowledge.models import ExtractedContent, ValidatedUpload
from app.knowledge.normalization import MAX_NORMALIZED_CHARACTERS, normalize_text

UPLOAD_CHUNK_SIZE = 64 * 1024
ALLOWED_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".txt": frozenset({"text/plain"}),
    ".md": frozenset({"text/markdown", "text/plain"}),
    ".pdf": frozenset({"application/pdf"}),
}


class AsyncUpload(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


def safe_upload_filename(value: str | None) -> str:
    if value is None:
        raise KnowledgeInvalidDocumentError
    filename = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename or len(filename) > 255 or any(ord(character) < 32 for character in filename):
        raise KnowledgeInvalidDocumentError
    return filename


def default_document_title(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    title = " ".join(stem.split())
    if not title:
        raise KnowledgeInvalidDocumentError
    return title[:200]


async def stage_upload(upload: AsyncUpload, *, maximum_bytes: int) -> ValidatedUpload:
    filename = safe_upload_filename(upload.filename)
    extension = Path(filename).suffix.lower()
    declared_media_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    accepted_types = ALLOWED_MEDIA_TYPES.get(extension)
    if accepted_types is None or declared_media_type not in accepted_types:
        raise KnowledgeUnsupportedMediaTypeError

    descriptor, temporary_name = tempfile.mkstemp(prefix="knowledge-upload-")
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    size = 0
    digest = hashlib.sha256()
    header = b""
    try:
        async with await open_file(temporary_path, "wb") as target:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > maximum_bytes:
                    raise KnowledgeFileTooLargeError
                if len(header) < 5:
                    header = (header + chunk)[:5]
                digest.update(chunk)
                await target.write(chunk)
        if size == 0:
            raise KnowledgeInvalidDocumentError
        if extension == ".pdf" and header != b"%PDF-":
            raise KnowledgeInvalidDocumentError
        await to_thread.run_sync(os.chmod, temporary_path, 0o600)
        return ValidatedUpload(
            temporary_path=str(temporary_path),
            original_filename=filename,
            media_type="text/markdown" if extension == ".md" else declared_media_type,
            size_bytes=size,
            sha256=digest.hexdigest(),
        )
    except Exception:
        await to_thread.run_sync(_unlink, temporary_path)
        raise


def _unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


class DocumentExtractor:
    def __init__(self, *, maximum_pdf_pages: int, maximum_concurrency: int = 2) -> None:
        self._maximum_pdf_pages = maximum_pdf_pages
        self._limiter = CapacityLimiter(maximum_concurrency)

    async def extract(self, upload: ValidatedUpload) -> ExtractedContent:
        return await to_thread.run_sync(
            self._extract,
            upload,
            limiter=self._limiter,
        )

    def _extract(self, upload: ValidatedUpload) -> ExtractedContent:
        path = Path(upload.temporary_path)
        if upload.media_type in ("text/plain", "text/markdown"):
            return self._extract_text(path, upload.media_type)
        return self._extract_pdf(path)

    @staticmethod
    def _extract_text(path: Path, media_type: str) -> ExtractedContent:
        try:
            raw_text = path.read_bytes().decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(
                "text_decode_failed", "The document is not valid UTF-8 text."
            ) from exc
        try:
            normalized = normalize_text(raw_text)
        except KnowledgeContentEmptyError as exc:
            raise DocumentExtractionError(
                "no_extractable_text", "The document contains no readable text."
            ) from exc
        except KnowledgeContentTooLargeError as exc:
            raise DocumentExtractionError(
                "normalized_content_too_large", "The extracted text is too large."
            ) from exc
        return ExtractedContent(
            normalized_text=normalized,
            locator_map={
                "schema_version": 1,
                "segments": [{"kind": "text", "start": 0, "end": len(normalized)}],
            },
            extractor_name="plain_text" if media_type == "text/plain" else "markdown",
            extractor_version="1",
        )

    def _extract_pdf(self, path: Path) -> ExtractedContent:
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise DocumentExtractionError(
                    "encrypted_pdf", "Encrypted PDF documents are not supported."
                )
            if len(reader.pages) > self._maximum_pdf_pages:
                raise DocumentExtractionError(
                    "pdf_page_limit_exceeded",
                    f"PDF documents may contain at most {self._maximum_pdf_pages} pages.",
                )
            combined = ""
            segments: list[dict[str, object]] = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                try:
                    normalized_page = normalize_text(page_text)
                except KnowledgeContentEmptyError:
                    continue
                if combined:
                    combined += "\n\n"
                start = len(combined)
                combined += normalized_page
                if len(combined) > MAX_NORMALIZED_CHARACTERS:
                    raise DocumentExtractionError(
                        "normalized_content_too_large", "The extracted text is too large."
                    )
                segments.append(
                    {
                        "kind": "page",
                        "page": page_number,
                        "start": start,
                        "end": len(combined),
                    }
                )
            if not combined:
                raise DocumentExtractionError(
                    "no_extractable_text", "The PDF contains no extractable text."
                )
            return ExtractedContent(
                normalized_text=combined,
                locator_map={"schema_version": 1, "segments": segments},
                extractor_name="pypdf",
                extractor_version=pypdf.__version__,
            )
        except DocumentExtractionError:
            raise
        except PdfReadError as exc:
            raise DocumentExtractionError(
                "invalid_document", "The PDF document could not be read."
            ) from exc
