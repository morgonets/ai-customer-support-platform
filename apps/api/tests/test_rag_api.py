import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_authenticated_session, require_authenticated_actor
from app.api.rag_dependencies import get_rag_service
from app.api.rag_errors import rag_error_handler
from app.core.auth import AuthenticatedActor
from app.main import app
from app.rag.errors import RagGenerationNotFoundError
from app.rag.models import Answer, Citation, IndexGeneration
from app.rag.service import RagService

ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("30000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("40000000-0000-0000-0000-000000000001")
GENERATION_ID = UUID("50000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 9, tzinfo=UTC)


def _generation() -> IndexGeneration:
    return IndexGeneration(
        id=GENERATION_ID,
        version_id=VERSION_ID,
        profile_key="deterministic-local-v1",
        generation_number=1,
        status="ready",
        is_active=True,
        attempt_count=1,
        failure_code=None,
        failure_message=None,
        created_at=NOW,
        completed_at=NOW,
    )


def test_rag_http_contracts() -> None:
    service = MagicMock(spec=RagService)
    service.answer.return_value = Answer(
        text="Grounded",
        insufficient_context=False,
        citations=(
            Citation(
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                version_number=1,
                source_title="Guide",
                source_kind="article",
                locator={"schema_version": 1},
                excerpt="Evidence",
                answer_start=0,
                answer_end=8,
            ),
        ),
    )
    service.list_generations.return_value = (_generation(),)
    service.reindex.return_value = _generation()
    service.retry.return_value = _generation()
    service.migrate_profile.return_value = (_generation(),)
    session = MagicMock(spec=AsyncSession)

    async def actor_override() -> AuthenticatedActor:
        return AuthenticatedActor(user_id=ACTOR_ID, email=None, expires_at=NOW)

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    app.dependency_overrides[get_rag_service] = lambda: cast(RagService, service)
    client = TestClient(app)
    base = f"/api/v1/organizations/{ORGANIZATION_ID}"
    try:
        answered = client.post(f"{base}/answers", json={"question": " What is supported? "})
        listed = client.get(f"{base}/knowledge-sources/{SOURCE_ID}/index-generations")
        reindexed = client.post(f"{base}/knowledge-sources/{SOURCE_ID}/index-generations")
        retried = client.post(
            f"{base}/knowledge-sources/{SOURCE_ID}/index-generations/{GENERATION_ID}/retry"
        )
        migrated = client.post(
            f"{base}/rag-profile-migrations", json={"profile_key": "deterministic-local-v1"}
        )
    finally:
        app.dependency_overrides.clear()

    assert answered.status_code == 200
    assert answered.json()["citations"][0]["source_id"] == str(SOURCE_ID)
    assert listed.json()["items"][0]["is_active"] is True
    assert reindexed.status_code == 202
    assert retried.status_code == 202
    assert migrated.status_code == 202
    service.answer.assert_awaited_once_with(
        session,
        actor_user_id=ACTOR_ID,
        organization_id=ORGANIZATION_ID,
        question="What is supported?",
    )
    assert service.reindex.await_args.kwargs["request_id"] is not None
    assert service.migrate_profile.await_args.kwargs["request_id"] is not None


def test_rag_api_validates_question_and_profile_key() -> None:
    async def actor_override() -> AuthenticatedActor:
        return AuthenticatedActor(user_id=ACTOR_ID, email=None, expires_at=NOW)

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, MagicMock(spec=AsyncSession))

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    client = TestClient(app)
    base = f"/api/v1/organizations/{ORGANIZATION_ID}"
    try:
        assert client.post(f"{base}/answers", json={"question": " "}).status_code == 422
        assert (
            client.post(
                f"{base}/rag-profile-migrations", json={"profile_key": "Invalid key"}
            ).status_code
            == 422
        )
    finally:
        app.dependency_overrides.clear()


def test_rag_dependency_and_error_handler_fail_closed() -> None:
    request = Request({"type": "http", "app": app})
    assert get_rag_service(request) is app.state.rag_service
    invalid_request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(rag_service=object()))}
    )
    with pytest.raises(RuntimeError, match="not configured"):
        get_rag_service(invalid_request)

    request.state.request_id = "request-id"
    response = asyncio.run(rag_error_handler(request, RagGenerationNotFoundError()))
    assert response.status_code == 404
    with pytest.raises(ValueError):
        asyncio.run(rag_error_handler(request, ValueError("wrong handler")))
