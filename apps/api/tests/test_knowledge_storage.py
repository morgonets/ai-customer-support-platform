import asyncio
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from app.knowledge.errors import KnowledgeStorageUnavailableError
from app.knowledge.storage import LocalObjectStorage, knowledge_storage_key

ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("50000000-0000-0000-0000-000000000001")
KEY = knowledge_storage_key(ORGANIZATION_ID, SOURCE_ID, VERSION_ID)


def test_local_storage_round_trip_and_idempotent_deletion(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "storage")
    source = tmp_path / "source.txt"
    destination = tmp_path / "copy.txt"
    source.write_bytes(b"private content")

    async def exercise() -> None:
        await storage.put(KEY, source)
        await storage.copy_to(KEY, destination)
        stream = await storage.open(KEY)
        with stream:
            assert stream.read() == b"private content"
        await storage.delete(KEY)
        await storage.delete(KEY)

    asyncio.run(exercise())
    assert destination.read_bytes() == b"private content"
    assert (tmp_path / "storage").is_dir()
    assert not (tmp_path / "storage" / KEY).exists()


@pytest.mark.parametrize(
    "key",
    [
        "invalid",
        f"not-a-uuid/{SOURCE_ID}/{VERSION_ID}/content",
        f"{ORGANIZATION_ID}/not-a-uuid/{VERSION_ID}/content",
        f"{ORGANIZATION_ID}/{SOURCE_ID}/not-a-uuid/content",
    ],
)
def test_local_storage_rejects_invalid_keys(tmp_path: Path, key: str) -> None:
    storage = LocalObjectStorage(tmp_path)

    with pytest.raises(KnowledgeStorageUnavailableError):
        asyncio.run(storage.open(key))


def test_local_storage_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / str(ORGANIZATION_ID)).symlink_to(outside, target_is_directory=True)
    storage = LocalObjectStorage(root)

    with pytest.raises(KnowledgeStorageUnavailableError):
        asyncio.run(storage.open(KEY))


def test_local_storage_maps_filesystem_failures(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "storage")
    source = tmp_path / "source"
    source.write_bytes(b"content")

    async def exercise() -> None:
        for method_name, arguments in [
            ("_put", (KEY, source)),
            ("_copy_to", (KEY, tmp_path / "copy")),
            ("_open", (KEY,)),
            ("_delete", (KEY,)),
        ]:
            with (
                patch.object(storage, method_name, side_effect=OSError("failure")),
                pytest.raises(KnowledgeStorageUnavailableError),
            ):
                await getattr(storage, method_name.removeprefix("_"))(*arguments)

    asyncio.run(exercise())


def test_local_storage_keeps_nonempty_parent_directories(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "storage")
    source = tmp_path / "source"
    source.write_bytes(b"content")
    object_path = tmp_path / "storage" / KEY

    async def exercise() -> None:
        await storage.put(KEY, source)
        (object_path.parent / "keep").write_text("keep")
        await storage.delete(KEY)

    asyncio.run(exercise())
    assert object_path.parent.exists()
