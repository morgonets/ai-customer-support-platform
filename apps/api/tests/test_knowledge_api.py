import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_authenticated_session,
    get_database,
    require_authenticated_actor,
)
from app.api.knowledge_errors import knowledge_error_handler
from app.api.rag_dependencies import get_rag_service
from app.api.routes.knowledge import (
    get_document_extractor,
    get_ingestion_coordinator,
    get_knowledge_service,
    get_knowledge_storage,
    knowledge_service,
)
from app.core.auth import AuthenticatedActor
from app.core.database import Database
from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentEmptyError,
    KnowledgeContentTooLargeError,
    KnowledgeContentUnavailableError,
    KnowledgeError,
    KnowledgeFileTooLargeError,
    KnowledgeInvalidDocumentError,
    KnowledgeProcessingInProgressError,
    KnowledgeProcessingNotRetryableError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
    KnowledgeStorageUnavailableError,
    KnowledgeUnsupportedMediaTypeError,
)
from app.knowledge.extraction import DocumentExtractor
from app.knowledge.ingestion import KnowledgeIngestionCoordinator
from app.knowledge.models import (
    KnowledgeFileObject,
    KnowledgeSource,
    KnowledgeSourcePage,
    KnowledgeSourceVersion,
)
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import LocalObjectStorage, ObjectStorage
from app.main import app
from app.rag.service import RagService

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("50000000-0000-0000-0000-000000000001")


def _source(*, normalized_text: str | None = "Normalized") -> KnowledgeSource:
    return KnowledgeSource(
        id=SOURCE_ID,
        organization_id=ORGANIZATION_ID,
        kind="article",
        title="Article",
        description="Description",
        created_by_user_id=ACTOR_ID,
        updated_by_user_id=ACTOR_ID,
        created_at=NOW,
        updated_at=NOW,
        current_version=KnowledgeSourceVersion(
            id=VERSION_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            kind="article",
            version_number=1,
            is_current=True,
            status="ready",
            raw_text="Raw article",
            normalized_text=normalized_text,
            normalization_version=1,
            locator_map={"schema_version": 1} if normalized_text is not None else None,
            original_filename=None,
            media_type=None,
            size_bytes=None,
            sha256=None,
            extractor_name="manual",
            extractor_version="1",
            processing_attempts=0,
            processing_started_at=None,
            processed_at=NOW,
            failure_code=None,
            failure_message=None,
            created_by_user_id=ACTOR_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _document_source() -> KnowledgeSource:
    source = _source()
    version = replace(
        source.current_version,
        kind="document",
        raw_text=None,
        original_filename="support-guide.txt",
        media_type="text/plain",
        size_bytes=13,
        sha256="a" * 64,
        extractor_name="plain_text",
    )
    return replace(
        source,
        kind="document",
        title="Support guide",
        current_version=version,
    )


def _actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        user_id=ACTOR_ID,
        email="person@example.test",
        expires_at=NOW + timedelta(minutes=5),
    )


def test_knowledge_article_http_contracts() -> None:
    service_mock = MagicMock(spec=KnowledgeService)
    service_mock.list_sources.return_value = KnowledgeSourcePage(
        items=[_source()], next_cursor="next"
    )
    service_mock.create_article.return_value = _source()
    service_mock.get_source.return_value = _source()
    service_mock.get_content.return_value = _source()
    service_mock.update_metadata.return_value = _source()
    service_mock.replace_article_content.return_value = _source()
    session = MagicMock(spec=AsyncSession)
    rag_service_mock = MagicMock(spec=RagService)

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    def service_override() -> KnowledgeService:
        return cast(KnowledgeService, service_mock)

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    app.dependency_overrides[get_knowledge_service] = service_override
    app.dependency_overrides[get_rag_service] = lambda: cast(RagService, rag_service_mock)
    client = TestClient(app)
    base = f"/api/v1/organizations/{ORGANIZATION_ID}/knowledge-sources"
    try:
        listed = client.get(f"{base}?limit=10&kind=article&processing_status=ready")
        created = client.post(
            f"{base}/articles",
            json={"title": " Article ", "description": " Description ", "text": "Raw"},
        )
        fetched = client.get(f"{base}/{SOURCE_ID}")
        content = client.get(f"{base}/{SOURCE_ID}/content")
        updated = client.patch(f"{base}/{SOURCE_ID}", json={"description": None})
        replaced = client.put(f"{base}/{SOURCE_ID}/content", json={"text": "Replacement"})
    finally:
        app.dependency_overrides.clear()

    assert listed.status_code == 200
    assert listed.json()["next_cursor"] == "next"
    assert created.status_code == 201
    assert created.json()["current_version"]["status"] == "ready"
    assert fetched.json()["id"] == str(SOURCE_ID)
    assert content.json()["normalized_text"] == "Normalized"
    assert updated.status_code == 200
    assert replaced.status_code == 200
    service_mock.create_article.assert_awaited_once_with(
        session,
        actor_user_id=ACTOR_ID,
        organization_id=ORGANIZATION_ID,
        title="Article",
        description="Description",
        raw_text="Raw",
    )
    service_mock.update_metadata.assert_awaited_once_with(
        session,
        actor_user_id=ACTOR_ID,
        organization_id=ORGANIZATION_ID,
        source_id=SOURCE_ID,
        title=None,
        description=None,
        description_is_set=True,
    )
    assert rag_service_mock.enqueue_ready_source.await_count == 2


def test_knowledge_metadata_requires_a_real_change() -> None:
    async def actor_override() -> AuthenticatedActor:
        return _actor()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, MagicMock(spec=AsyncSession))

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    client = TestClient(app)
    base = f"/api/v1/organizations/{ORGANIZATION_ID}/knowledge-sources/{SOURCE_ID}"
    try:
        assert client.patch(base, json={}).status_code == 422
        assert client.patch(base, json={"title": None}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_content_route_detects_inconsistent_ready_version() -> None:
    service_mock = MagicMock(spec=KnowledgeService)
    service_mock.get_content.return_value = _source(normalized_text=None)

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, MagicMock(spec=AsyncSession))

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    app.dependency_overrides[get_knowledge_service] = lambda: cast(KnowledgeService, service_mock)
    try:
        with pytest.raises(RuntimeError, match="incomplete"):
            TestClient(app, raise_server_exceptions=True).get(
                f"/api/v1/organizations/{ORGANIZATION_ID}/knowledge-sources/{SOURCE_ID}/content"
            )
    finally:
        app.dependency_overrides.clear()


def test_default_knowledge_service_is_configured() -> None:
    assert get_knowledge_service() is knowledge_service


def test_knowledge_runtime_dependencies_are_configured(tmp_path: Path) -> None:
    request = Request({"type": "http", "app": app})
    assert isinstance(get_knowledge_storage(request), LocalObjectStorage)
    assert isinstance(get_document_extractor(request), DocumentExtractor)
    rag_service_mock = MagicMock(spec=RagService)
    coordinator = get_ingestion_coordinator(
        knowledge_service,
        LocalObjectStorage(tmp_path),
        DocumentExtractor(maximum_pdf_pages=1),
        cast(RagService, rag_service_mock),
    )
    assert isinstance(coordinator, KnowledgeIngestionCoordinator)
    assert coordinator._ready_callback is not None

    async def invoke_ready_callback() -> None:
        assert coordinator._ready_callback is not None
        await coordinator._ready_callback(cast(AsyncSession, MagicMock()), ACTOR_ID, _source())

    asyncio.run(invoke_ready_callback())
    rag_service_mock.enqueue_ready_source.assert_awaited_once()

    invalid_app = SimpleNamespace(state=SimpleNamespace(knowledge_storage=object()))
    invalid_request = Request({"type": "http", "app": invalid_app})
    with pytest.raises(RuntimeError, match="storage"):
        get_knowledge_storage(invalid_request)
    invalid_app.state.document_extractor = object()
    with pytest.raises(RuntimeError, match="extractor"):
        get_document_extractor(invalid_request)


def test_document_upload_retry_and_delete_http_contracts() -> None:
    coordinator_mock = MagicMock(spec=KnowledgeIngestionCoordinator)
    coordinator_mock.create_document.return_value = _document_source()
    coordinator_mock.retry_document.return_value = _document_source()
    database_mock = MagicMock(spec=Database)

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_database] = lambda: cast(Database, database_mock)
    app.dependency_overrides[get_ingestion_coordinator] = lambda: cast(
        KnowledgeIngestionCoordinator, coordinator_mock
    )
    client = TestClient(app)
    base = f"/api/v1/organizations/{ORGANIZATION_ID}/knowledge-sources"
    try:
        created = client.post(
            f"{base}/documents",
            data={"description": " Upload guide "},
            files={"file": ("support-guide.txt", b"Support guide", "text/plain")},
        )
        retried = client.post(f"{base}/{SOURCE_ID}/retry")
        deleted = client.delete(f"{base}/{SOURCE_ID}")
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["kind"] == "document"
    assert retried.status_code == 200
    assert deleted.status_code == 204
    create_arguments = coordinator_mock.create_document.await_args.kwargs
    assert create_arguments["title"] == "support guide"
    assert create_arguments["description"] == "Upload guide"
    assert create_arguments["upload"].filename == "support-guide.txt"
    assert coordinator_mock.create_document.await_args.args[0]() is (
        database_mock.session_for.return_value
    )
    assert (
        coordinator_mock.retry_document.await_args.args[0]()
        is database_mock.session_for.return_value
    )
    assert (
        coordinator_mock.delete_source.await_args.args[0]()
        is database_mock.session_for.return_value
    )
    coordinator_mock.retry_document.assert_awaited_once()
    coordinator_mock.delete_source.assert_awaited_once()


def test_document_upload_rejects_blank_metadata() -> None:
    coordinator_mock = MagicMock(spec=KnowledgeIngestionCoordinator)

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_database] = lambda: cast(Database, MagicMock(spec=Database))
    app.dependency_overrides[get_ingestion_coordinator] = lambda: cast(
        KnowledgeIngestionCoordinator, coordinator_mock
    )
    client = TestClient(app)
    url = f"/api/v1/organizations/{ORGANIZATION_ID}/knowledge-sources/documents"
    try:
        blank_title = client.post(
            url,
            data={"title": " "},
            files={"file": ("guide.txt", b"Guide", "text/plain")},
        )
        blank_description = client.post(
            url,
            data={"description": " "},
            files={"file": ("guide.txt", b"Guide", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert blank_title.status_code == 422
    assert blank_title.json()["error"]["code"] == "invalid_document"
    assert blank_description.status_code == 422
    coordinator_mock.create_document.assert_not_awaited()


def test_original_document_download_streams_private_file() -> None:
    service_mock = MagicMock(spec=KnowledgeService)
    service_mock.get_file_for_download.return_value = KnowledgeFileObject(
        version_id=VERSION_ID,
        storage_key=f"{ORGANIZATION_ID}/{SOURCE_ID}/{VERSION_ID}/content",
        original_filename="support guide.txt",
        media_type="text/plain",
        size_bytes=13,
    )
    storage_mock = MagicMock(spec=ObjectStorage)
    storage_mock.open.return_value = BytesIO(b"Support guide")

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, MagicMock(spec=AsyncSession))

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    app.dependency_overrides[get_knowledge_service] = lambda: cast(KnowledgeService, service_mock)
    app.dependency_overrides[get_knowledge_storage] = lambda: cast(ObjectStorage, storage_mock)
    client = TestClient(app)
    try:
        response = client.get(
            f"/api/v1/organizations/{ORGANIZATION_ID}/knowledge-sources/{SOURCE_ID}/file"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"Support guide"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "support%20guide.txt" in response.headers["content-disposition"]
    service_mock.get_file_for_download.assert_awaited_once()
    storage_mock.open.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (KnowledgeSourceNotFoundError(), 404, "knowledge_source_not_found"),
        (InvalidKnowledgeCursorError(), 422, "invalid_cursor"),
        (KnowledgeContentEmptyError(), 422, "invalid_knowledge_content"),
        (KnowledgeContentTooLargeError(), 422, "normalized_content_too_large"),
        (KnowledgeSourceKindError(), 409, "knowledge_source_kind_mismatch"),
        (KnowledgeContentUnavailableError(), 409, "knowledge_content_unavailable"),
        (KnowledgeFileTooLargeError(), 413, "file_too_large"),
        (KnowledgeUnsupportedMediaTypeError(), 415, "unsupported_media_type"),
        (KnowledgeInvalidDocumentError(), 422, "invalid_document"),
        (KnowledgeStorageUnavailableError(), 503, "storage_unavailable"),
        (KnowledgeProcessingInProgressError(), 409, "processing_in_progress"),
        (KnowledgeProcessingNotRetryableError(), 409, "processing_not_retryable"),
    ],
)
def test_knowledge_errors_use_stable_contract(
    error: KnowledgeError, status_code: int, code: str
) -> None:
    request = Request({"type": "http", "headers": []})
    request.state.request_id = "request-id"

    response = asyncio.run(knowledge_error_handler(request, error))

    assert response.status_code == status_code
    assert f'"code":"{code}"'.encode() in response.body


def test_knowledge_error_handler_reraises_unknown_errors() -> None:
    request = Request({"type": "http", "headers": []})

    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(knowledge_error_handler(request, RuntimeError("unexpected")))
    with pytest.raises(KnowledgeError, match="new error"):
        asyncio.run(knowledge_error_handler(request, KnowledgeError("new error")))
