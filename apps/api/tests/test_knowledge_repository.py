import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.repository import SqlAlchemyKnowledgeRepository

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("50000000-0000-0000-0000-000000000001")
ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")


def _row() -> dict[str, object]:
    return {
        "id": SOURCE_ID,
        "organization_id": ORGANIZATION_ID,
        "kind": "article",
        "title": "Article",
        "description": None,
        "created_by_user_id": ACTOR_ID,
        "updated_by_user_id": ACTOR_ID,
        "created_at": NOW,
        "updated_at": NOW,
        "version_id": VERSION_ID,
        "version_number": 1,
        "is_current": True,
        "status": "ready",
        "raw_text": "Raw",
        "normalized_text": "Normalized",
        "normalization_version": 1,
        "locator_map": {"schema_version": 1},
        "original_filename": None,
        "media_type": None,
        "size_bytes": None,
        "sha256": None,
        "extractor_name": "manual",
        "extractor_version": "1",
        "processing_attempts": 0,
        "processing_started_at": None,
        "processed_at": NOW,
        "failure_code": None,
        "failure_message": None,
        "version_created_by_user_id": ACTOR_ID,
        "version_created_at": NOW,
        "version_updated_at": NOW,
    }


def _document_row(status: str = "processing") -> dict[str, object]:
    row = _row()
    row.update(
        {
            "kind": "document",
            "status": status,
            "raw_text": None,
            "normalized_text": "Extracted" if status == "ready" else None,
            "locator_map": {"schema_version": 1} if status == "ready" else None,
            "original_filename": "guide.pdf",
            "media_type": "application/pdf",
            "size_bytes": 100,
            "sha256": "a" * 64,
            "extractor_name": "pypdf" if status == "ready" else None,
            "extractor_version": "1" if status == "ready" else None,
            "processing_attempts": 1,
            "processing_started_at": NOW,
            "failure_code": "failed" if status == "failed" else None,
            "failure_message": "Failed" if status == "failed" else None,
        }
    )
    return row


def _mapping_result(*rows: dict[str, object]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = list(rows)
    result.mappings.return_value.one_or_none.return_value = rows[0] if rows else None
    return result


def test_repository_lists_with_and_without_filters_and_maps_source() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [_mapping_result(_row()), _mapping_result()]

    async def exercise() -> None:
        sources = await repository.list_sources(
            session,
            ORGANIZATION_ID,
            limit=26,
            cursor=(NOW, SOURCE_ID),
            kind="article",
            status="ready",
        )
        assert sources[0].current_version.normalized_text == "Normalized"
        assert sources[0].description is None
        empty = await repository.list_sources(
            session,
            ORGANIZATION_ID,
            limit=26,
            cursor=None,
            kind=None,
            status=None,
        )
        assert empty == []

    asyncio.run(exercise())
    first_parameters = session.execute.await_args_list[0].args[1]
    assert first_parameters["cursor_id"] == SOURCE_ID
    assert first_parameters["kind"] == "article"
    assert first_parameters["status"] == "ready"


def test_repository_gets_present_and_missing_source() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [_mapping_result(_row()), _mapping_result()]

    async def exercise() -> None:
        assert await repository.get_source(session, ORGANIZATION_ID, SOURCE_ID) is not None
        assert await repository.get_source(session, ORGANIZATION_ID, SOURCE_ID) is None

    asyncio.run(exercise())


def test_repository_creates_article_and_requires_visible_result() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [MagicMock(), MagicMock(), _mapping_result(_row())]

    created = asyncio.run(
        repository.create_article(
            session,
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            organization_id=ORGANIZATION_ID,
            actor_user_id=ACTOR_ID,
            title="Article",
            description=None,
            raw_text="Raw",
            normalized_text="Normalized",
            locator_map={"schema_version": 1},
            processed_at=NOW,
        )
    )
    assert created.id == SOURCE_ID
    version_parameters = session.execute.await_args_list[1].args[1]
    assert version_parameters["locator_map"] == '{"schema_version":1}'

    missing_session = AsyncMock(spec=AsyncSession)
    missing_session.execute.side_effect = [MagicMock(), MagicMock(), _mapping_result()]
    with pytest.raises(RuntimeError, match="not visible"):
        asyncio.run(
            repository.create_article(
                missing_session,
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                organization_id=ORGANIZATION_ID,
                actor_user_id=ACTOR_ID,
                title="Article",
                description=None,
                raw_text="Raw",
                normalized_text="Normalized",
                locator_map={"schema_version": 1},
                processed_at=NOW,
            )
        )


def test_repository_updates_metadata_when_row_remains_visible() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    session = AsyncMock(spec=AsyncSession)
    updated_result = MagicMock()
    updated_result.scalar_one_or_none.return_value = SOURCE_ID
    missing_result = MagicMock()
    missing_result.scalar_one_or_none.return_value = None
    session.execute.side_effect = [updated_result, _mapping_result(_row()), missing_result]

    async def exercise() -> None:
        updated = await repository.update_metadata(
            session,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            actor_user_id=ACTOR_ID,
            title="Updated",
            description="Description",
        )
        assert updated is not None
        assert (
            await repository.update_metadata(
                session,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                actor_user_id=ACTOR_ID,
                title="Updated",
                description=None,
            )
            is None
        )

    asyncio.run(exercise())


def test_repository_replaces_article_under_lock_and_handles_missing_source() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    session = AsyncMock(spec=AsyncSession)
    locked = MagicMock()
    locked.scalar_one_or_none.return_value = SOURCE_ID
    number = MagicMock()
    number.scalar_one.return_value = 1
    session.execute.side_effect = [
        locked,
        number,
        MagicMock(),
        MagicMock(),
        _mapping_result(_row()),
    ]

    replaced = asyncio.run(
        repository.replace_article_content(
            session,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            actor_user_id=ACTOR_ID,
            raw_text="Replacement",
            normalized_text="Replacement",
            locator_map={"schema_version": 1},
            processed_at=NOW,
        )
    )
    assert replaced is not None
    inserted_parameters = session.execute.await_args_list[3].args[1]
    assert inserted_parameters["version_number"] == 2

    missing_session = AsyncMock(spec=AsyncSession)
    missing = MagicMock()
    missing.scalar_one_or_none.return_value = None
    missing_session.execute.return_value = missing
    assert (
        asyncio.run(
            repository.replace_article_content(
                missing_session,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                actor_user_id=ACTOR_ID,
                raw_text="Replacement",
                normalized_text="Replacement",
                locator_map={"schema_version": 1},
                processed_at=NOW,
            )
        )
        is None
    )


def test_repository_creates_processing_document_and_requires_visibility() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [MagicMock(), MagicMock(), _mapping_result(_document_row())]

    created = asyncio.run(
        repository.create_document_processing(
            session,
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            organization_id=ORGANIZATION_ID,
            actor_user_id=ACTOR_ID,
            title="Document",
            description=None,
            original_filename="guide.pdf",
            media_type="application/pdf",
            size_bytes=100,
            sha256="a" * 64,
            storage_key=f"{ORGANIZATION_ID}/{SOURCE_ID}/{VERSION_ID}/content",
            processing_started_at=NOW,
        )
    )
    assert created.kind == "document"

    missing_session = AsyncMock(spec=AsyncSession)
    missing_session.execute.side_effect = [MagicMock(), MagicMock(), _mapping_result()]
    with pytest.raises(RuntimeError, match="document is not visible"):
        asyncio.run(
            repository.create_document_processing(
                missing_session,
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                organization_id=ORGANIZATION_ID,
                actor_user_id=ACTOR_ID,
                title="Document",
                description=None,
                original_filename="guide.pdf",
                media_type="application/pdf",
                size_bytes=100,
                sha256="a" * 64,
                storage_key=f"{ORGANIZATION_ID}/{SOURCE_ID}/{VERSION_ID}/content",
                processing_started_at=NOW,
            )
        )


def test_repository_completes_fails_and_retries_document_processing() -> None:
    repository = SqlAlchemyKnowledgeRepository()

    async def exercise_update(method_name: str, expected_status: str, **kwargs: object) -> None:
        session = AsyncMock(spec=AsyncSession)
        updated = MagicMock()
        updated.scalar_one_or_none.return_value = VERSION_ID
        session.execute.side_effect = [updated, _mapping_result(_document_row(expected_status))]
        result = await getattr(repository, method_name)(
            session,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            **kwargs,
        )
        assert result is not None
        assert result.current_version.status == expected_status

        missing_session = AsyncMock(spec=AsyncSession)
        missing = MagicMock()
        missing.scalar_one_or_none.return_value = None
        missing_session.execute.return_value = missing
        assert (
            await getattr(repository, method_name)(
                missing_session,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                **kwargs,
            )
            is None
        )

    async def exercise() -> None:
        await exercise_update(
            "mark_document_ready",
            "ready",
            normalized_text="Extracted",
            locator_map={"schema_version": 1},
            extractor_name="pypdf",
            extractor_version="1",
            processed_at=NOW,
        )
        await exercise_update(
            "mark_document_failed",
            "failed",
            failure_code="invalid_document",
            failure_message="Invalid",
            processed_at=NOW,
        )
        await exercise_update(
            "begin_document_retry",
            "processing",
            processing_started_at=NOW,
        )

    asyncio.run(exercise())


def test_repository_resolves_guarded_files_and_deletes_source() -> None:
    repository = SqlAlchemyKnowledgeRepository()
    file_result = _mapping_result(
        {
            "version_id": VERSION_ID,
            "storage_key": f"{ORGANIZATION_ID}/{SOURCE_ID}/{VERSION_ID}/content",
            "original_filename": "guide.pdf",
            "media_type": "application/pdf",
            "size_bytes": 100,
        }
    )
    deleted = MagicMock()
    deleted.scalar_one_or_none.return_value = SOURCE_ID
    missing = MagicMock()
    missing.scalar_one_or_none.return_value = None
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [file_result, deleted, missing]

    async def exercise() -> None:
        files = await repository.get_file_objects(session, ORGANIZATION_ID, SOURCE_ID)
        assert files[0].original_filename == "guide.pdf"
        assert await repository.delete_source(session, ORGANIZATION_ID, SOURCE_ID)
        assert not await repository.delete_source(session, ORGANIZATION_ID, SOURCE_ID)

    asyncio.run(exercise())
