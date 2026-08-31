import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from anyio import to_thread
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.knowledge.extraction import DocumentExtractor
from app.knowledge.models import ValidatedUpload
from app.knowledge.repository import SqlAlchemyKnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import LocalObjectStorage
from app.tenants.authorization import TenantAuthorizer
from app.tenants.errors import OrganizationNotFoundError, TenantAuthorizationError
from app.tenants.repository import SqlAlchemyTenantRepository
from app.tenants.service import TenantService

ADMIN_DATABASE_URL = os.getenv("INTEGRATION_DATABASE_ADMIN_URL")
OWNER_ID = UUID("61000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("61000000-0000-0000-0000-000000000002")
MEMBER_ID = UUID("61000000-0000-0000-0000-000000000003")
OUTSIDER_ID = UUID("61000000-0000-0000-0000-000000000004")
ORGANIZATION_ID = UUID("62000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("64000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("65000000-0000-0000-0000-000000000001")
SECOND_VERSION_ID = UUID("65000000-0000-0000-0000-000000000002")
DOCUMENT_SOURCE_ID = UUID("64000000-0000-0000-0000-000000000002")
DOCUMENT_VERSION_ID = UUID("65000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        ADMIN_DATABASE_URL is None,
        reason="INTEGRATION_DATABASE_ADMIN_URL is required for persistence integration tests",
    ),
]


async def _assume_actor(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(text("reset role"))
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"}, separators=(",", ":"))
    await session.execute(
        text("select set_config('request.jwt.claims', :claims, true)"), {"claims": claims}
    )
    await session.execute(text("set local role app_api"))


async def _exercise_knowledge_persistence(upload_path: Path, storage_path: Path) -> None:
    assert ADMIN_DATABASE_URL is not None
    engine = create_async_engine(ADMIN_DATABASE_URL)
    session = AsyncSession(engine, expire_on_commit=False)
    transaction = await session.begin()
    tenant_repository = SqlAlchemyTenantRepository()
    generated_ids = iter(
        [SOURCE_ID, VERSION_ID, SECOND_VERSION_ID, DOCUMENT_SOURCE_ID, DOCUMENT_VERSION_ID]
    )
    service = KnowledgeService(
        SqlAlchemyKnowledgeRepository(),
        TenantAuthorizer(tenant_repository),
        id_factory=lambda: next(generated_ids),
        clock=lambda: NOW,
    )
    try:
        await session.execute(
            text(
                """
                insert into auth.users (
                  id, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
                )
                values
                  (:owner_id, 'knowledge-owner@example.test', '{}', '{}', now(), now()),
                  (:admin_id, 'knowledge-admin@example.test', '{}', '{}', now(), now()),
                  (:member_id, 'knowledge-member@example.test', '{}', '{}', now(), now()),
                  (:outsider_id, 'knowledge-outsider@example.test', '{}', '{}', now(), now())
                """
            ),
            {
                "owner_id": OWNER_ID,
                "admin_id": ADMIN_ID,
                "member_id": MEMBER_ID,
                "outsider_id": OUTSIDER_ID,
            },
        )
        await _assume_actor(session, OWNER_ID)
        tenant_service_ids = iter(
            [
                ORGANIZATION_ID,
                UUID("63000000-0000-0000-0000-000000000001"),
                UUID("63000000-0000-0000-0000-000000000002"),
            ]
        )
        tenant_service = TenantService(
            tenant_repository, id_factory=lambda: next(tenant_service_ids)
        )
        await tenant_service.create_organization(session, OWNER_ID, "Knowledge Integration")
        await tenant_service.create_membership(
            session, OWNER_ID, ORGANIZATION_ID, ADMIN_ID, "admin"
        )
        await tenant_service.create_membership(
            session, OWNER_ID, ORGANIZATION_ID, MEMBER_ID, "member"
        )

        article = await service.create_article(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            title="Integration article",
            description=None,
            raw_text="First line  \r\nSecond line",
        )
        assert article.current_version.normalized_text == "First line\nSecond line"

        await _assume_actor(session, MEMBER_ID)
        visible = await service.get_content(
            session,
            actor_user_id=MEMBER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
        assert visible.id == SOURCE_ID
        with pytest.raises(TenantAuthorizationError):
            await service.update_metadata(
                session,
                actor_user_id=MEMBER_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                title="Forbidden",
                description=None,
                description_is_set=False,
            )

        await _assume_actor(session, ADMIN_ID)
        updated = await service.update_metadata(
            session,
            actor_user_id=ADMIN_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            title="Admin updated article",
            description="Updated description",
            description_is_set=True,
        )
        assert updated.title == "Admin updated article"

        await _assume_actor(session, OWNER_ID)
        replaced = await service.replace_article_content(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            raw_text="Replacement content",
        )
        assert replaced.current_version.version_number == 2

        document_bytes = b"Document integration content"
        document, file_object = await service.create_document_processing(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            title="Integration document",
            description=None,
            original_filename="integration.txt",
            media_type="text/plain",
            size_bytes=len(document_bytes),
            sha256=hashlib.sha256(document_bytes).hexdigest(),
        )
        assert document.current_version.status == "processing"
        storage = LocalObjectStorage(storage_path)
        await storage.put(file_object.storage_key, upload_path)
        extracted = await DocumentExtractor(maximum_pdf_pages=100).extract(
            ValidatedUpload(
                temporary_path=str(upload_path),
                original_filename="integration.txt",
                media_type="text/plain",
                size_bytes=len(document_bytes),
                sha256=hashlib.sha256(document_bytes).hexdigest(),
            )
        )
        ready_document = await service.mark_document_ready(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=DOCUMENT_SOURCE_ID,
            extracted=extracted,
        )
        assert ready_document.current_version.normalized_text == document_bytes.decode()

        await _assume_actor(session, MEMBER_ID)
        member_content = await service.get_content(
            session,
            actor_user_id=MEMBER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=DOCUMENT_SOURCE_ID,
        )
        assert member_content.current_version.normalized_text == document_bytes.decode()
        with pytest.raises(TenantAuthorizationError):
            await service.get_file_for_download(
                session,
                actor_user_id=MEMBER_ID,
                organization_id=ORGANIZATION_ID,
                source_id=DOCUMENT_SOURCE_ID,
            )

        await _assume_actor(session, ADMIN_ID)
        downloadable = await service.get_file_for_download(
            session,
            actor_user_id=ADMIN_ID,
            organization_id=ORGANIZATION_ID,
            source_id=DOCUMENT_SOURCE_ID,
        )
        stream = await storage.open(downloadable.storage_key)
        try:
            assert await to_thread.run_sync(stream.read) == document_bytes
        finally:
            await to_thread.run_sync(stream.close)
        await storage.delete(downloadable.storage_key)

        await _assume_actor(session, OUTSIDER_ID)
        with pytest.raises(OrganizationNotFoundError):
            await service.get_source(
                session,
                actor_user_id=OUTSIDER_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
            )
    finally:
        await transaction.rollback()
        await session.close()
        await engine.dispose()


def test_knowledge_lifecycle_enforces_database_storage_and_tenant_boundaries(
    tmp_path: Path,
) -> None:
    upload_path = tmp_path / "integration.txt"
    upload_path.write_bytes(b"Document integration content")
    asyncio.run(_exercise_knowledge_persistence(upload_path, tmp_path / "storage"))
