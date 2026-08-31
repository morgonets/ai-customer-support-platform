import asyncio
import base64
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentUnavailableError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
)
from app.knowledge.models import (
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceVersion,
)
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.tenants.authorization import TenantAuthorizer
from app.tenants.errors import TenantAuthorizationError
from app.tenants.models import Membership, OrganizationRole
from app.tenants.repository import TenantRepository

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")
SECOND_SOURCE_ID = UUID("40000000-0000-0000-0000-000000000002")
VERSION_ID = UUID("50000000-0000-0000-0000-000000000001")
NEW_SOURCE_ID = UUID("60000000-0000-0000-0000-000000000001")
NEW_VERSION_ID = UUID("60000000-0000-0000-0000-000000000002")


def _membership(role: OrganizationRole = "owner") -> Membership:
    return Membership(
        id=UUID("30000000-0000-0000-0000-000000000001"),
        organization_id=ORGANIZATION_ID,
        user_id=ACTOR_ID,
        display_name=None,
        role=role,
        created_at=NOW,
        updated_at=NOW,
    )


def _source(
    *,
    source_id: UUID = SOURCE_ID,
    kind: str = "article",
    status: str = "ready",
    title: str = "Example article",
) -> KnowledgeSource:
    return KnowledgeSource(
        id=source_id,
        organization_id=ORGANIZATION_ID,
        kind=cast(KnowledgeSourceKind, kind),
        title=title,
        description="Description",
        created_by_user_id=ACTOR_ID,
        updated_by_user_id=ACTOR_ID,
        created_at=NOW,
        updated_at=NOW,
        current_version=KnowledgeSourceVersion(
            id=VERSION_ID,
            organization_id=ORGANIZATION_ID,
            source_id=source_id,
            kind=cast(KnowledgeSourceKind, kind),
            version_number=1,
            is_current=True,
            status=cast(KnowledgeProcessingStatus, status),
            raw_text="Raw article" if kind == "article" else None,
            normalized_text="Normalized content" if status == "ready" else None,
            normalization_version=1,
            locator_map={"schema_version": 1} if status == "ready" else None,
            original_filename="guide.pdf" if kind == "document" else None,
            media_type="application/pdf" if kind == "document" else None,
            size_bytes=100 if kind == "document" else None,
            sha256="a" * 64 if kind == "document" else None,
            extractor_name="manual",
            extractor_version="1",
            processing_attempts=0 if kind == "article" else 1,
            processing_started_at=None,
            processed_at=NOW if status != "processing" else None,
            failure_code="failed" if status == "failed" else None,
            failure_message="Failed" if status == "failed" else None,
            created_by_user_id=ACTOR_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _service(
    role: OrganizationRole = "owner",
) -> tuple[KnowledgeService, MagicMock, AsyncMock]:
    tenant_repository_mock = MagicMock(spec=TenantRepository)
    tenant_repository_mock.get_membership.return_value = _membership(role)
    knowledge_repository_mock = MagicMock(spec=KnowledgeRepository)
    generated = iter([NEW_SOURCE_ID, NEW_VERSION_ID])
    service = KnowledgeService(
        cast(KnowledgeRepository, knowledge_repository_mock),
        TenantAuthorizer(cast(TenantRepository, tenant_repository_mock)),
        id_factory=lambda: next(generated),
        clock=lambda: NOW,
    )
    return service, knowledge_repository_mock, AsyncMock(spec=AsyncSession)


def test_list_sources_paginates_and_round_trips_cursor() -> None:
    service, repository_mock, session = _service("member")
    first = _source()
    second = _source(source_id=SECOND_SOURCE_ID)
    repository_mock.list_sources.return_value = [first, second]

    page = asyncio.run(
        service.list_sources(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            limit=1,
            cursor=None,
            kind="article",
            status="ready",
        )
    )

    assert page.items == [first]
    assert page.next_cursor is not None
    repository_mock.list_sources.reset_mock()
    repository_mock.list_sources.return_value = [second]
    next_page = asyncio.run(
        service.list_sources(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            limit=1,
            cursor=page.next_cursor,
            kind=None,
            status=None,
        )
    )
    assert next_page.next_cursor is None
    assert repository_mock.list_sources.await_args.kwargs["cursor"] == (NOW, SOURCE_ID)


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64",
        "W10",
        "e30",
        "eyJjcmVhdGVkX2F0IjoxfQ",
        base64.urlsafe_b64encode(
            b'{"created_at":"2026-08-31T12:00:00","id":"40000000-0000-0000-0000-000000000001"}'
        )
        .decode()
        .rstrip("="),
    ],
)
def test_list_sources_rejects_invalid_cursor(cursor: str) -> None:
    service, _, session = _service()

    with pytest.raises(InvalidKnowledgeCursorError):
        asyncio.run(
            service.list_sources(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                limit=25,
                cursor=cursor,
                kind=None,
                status=None,
            )
        )


def test_get_source_and_content_require_visible_ready_source() -> None:
    service, repository_mock, session = _service("member")
    repository_mock.get_source.side_effect = [_source(), None, _source(), _source(status="failed")]

    found = asyncio.run(
        service.get_source(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
    )
    assert found.id == SOURCE_ID
    with pytest.raises(KnowledgeSourceNotFoundError):
        asyncio.run(
            service.get_source(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
            )
        )
    assert (
        asyncio.run(
            service.get_content(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
            )
        ).current_version.normalized_text
        == "Normalized content"
    )
    with pytest.raises(KnowledgeContentUnavailableError):
        asyncio.run(
            service.get_content(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
            )
        )


def test_create_article_normalizes_content_and_requires_manager() -> None:
    service, repository_mock, session = _service("admin")
    repository_mock.create_article.return_value = _source()

    created = asyncio.run(
        service.create_article(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            title="Example",
            description=None,
            raw_text="Line one  \r\nLine two",
        )
    )

    assert created.id == SOURCE_ID
    assert repository_mock.create_article.await_args.kwargs == {
        "source_id": NEW_SOURCE_ID,
        "version_id": NEW_VERSION_ID,
        "organization_id": ORGANIZATION_ID,
        "actor_user_id": ACTOR_ID,
        "title": "Example",
        "description": None,
        "raw_text": "Line one  \r\nLine two",
        "normalized_text": "Line one\nLine two",
        "locator_map": {
            "schema_version": 1,
            "segments": [{"kind": "text", "start": 0, "end": 17}],
        },
        "processed_at": NOW,
    }

    denied, _, denied_session = _service("member")
    with pytest.raises(TenantAuthorizationError):
        asyncio.run(
            denied.create_article(
                denied_session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                title="Denied",
                description=None,
                raw_text="Content",
            )
        )


def test_update_metadata_preserves_omitted_values_and_handles_race() -> None:
    service, repository_mock, session = _service()
    repository_mock.get_source.side_effect = [_source(), _source()]
    repository_mock.update_metadata.side_effect = [_source(title="Updated"), None]

    updated = asyncio.run(
        service.update_metadata(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            title="Updated",
            description=None,
            description_is_set=False,
        )
    )
    assert updated.title == "Updated"
    assert repository_mock.update_metadata.await_args_list[0].kwargs["description"] == "Description"

    with pytest.raises(KnowledgeSourceNotFoundError):
        asyncio.run(
            service.update_metadata(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                title=None,
                description=None,
                description_is_set=True,
            )
        )


def test_replace_article_content_creates_version_and_rejects_document() -> None:
    service, repository_mock, session = _service()
    repository_mock.get_source.side_effect = [_source(), _source(kind="document"), _source()]
    repository_mock.replace_article_content.side_effect = [_source(), None]

    replaced = asyncio.run(
        service.replace_article_content(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            raw_text="Replacement",
        )
    )
    assert replaced.id == SOURCE_ID

    with pytest.raises(KnowledgeSourceKindError):
        asyncio.run(
            service.replace_article_content(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                raw_text="Replacement",
            )
        )
    with pytest.raises(KnowledgeSourceNotFoundError):
        asyncio.run(
            service.replace_article_content(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                raw_text="Replacement",
            )
        )
