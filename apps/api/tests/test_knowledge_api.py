import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_authenticated_session, require_authenticated_actor
from app.api.knowledge_errors import knowledge_error_handler
from app.api.routes.knowledge import get_knowledge_service, knowledge_service
from app.core.auth import AuthenticatedActor
from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentEmptyError,
    KnowledgeContentTooLargeError,
    KnowledgeContentUnavailableError,
    KnowledgeError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
)
from app.knowledge.models import KnowledgeSource, KnowledgeSourcePage, KnowledgeSourceVersion
from app.knowledge.service import KnowledgeService
from app.main import app

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

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    def service_override() -> KnowledgeService:
        return cast(KnowledgeService, service_mock)

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    app.dependency_overrides[get_knowledge_service] = service_override
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


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (KnowledgeSourceNotFoundError(), 404, "knowledge_source_not_found"),
        (InvalidKnowledgeCursorError(), 422, "invalid_cursor"),
        (KnowledgeContentEmptyError(), 422, "invalid_knowledge_content"),
        (KnowledgeContentTooLargeError(), 422, "normalized_content_too_large"),
        (KnowledgeSourceKindError(), 409, "knowledge_source_kind_mismatch"),
        (KnowledgeContentUnavailableError(), 409, "knowledge_content_unavailable"),
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
