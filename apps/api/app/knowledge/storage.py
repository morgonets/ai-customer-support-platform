import os
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable
from uuid import UUID

from anyio import to_thread

from app.knowledge.errors import KnowledgeStorageUnavailableError


@runtime_checkable
class ObjectStorage(Protocol):
    async def put(self, key: str, source_path: Path) -> None: ...

    async def copy_to(self, key: str, destination_path: Path) -> None: ...

    async def open(self, key: str) -> BinaryIO: ...

    async def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def put(self, key: str, source_path: Path) -> None:
        try:
            await to_thread.run_sync(self._put, key, source_path)
        except OSError as exc:
            raise KnowledgeStorageUnavailableError from exc

    async def copy_to(self, key: str, destination_path: Path) -> None:
        try:
            await to_thread.run_sync(self._copy_to, key, destination_path)
        except OSError as exc:
            raise KnowledgeStorageUnavailableError from exc

    async def open(self, key: str) -> BinaryIO:
        try:
            return await to_thread.run_sync(self._open, key)
        except OSError as exc:
            raise KnowledgeStorageUnavailableError from exc

    async def delete(self, key: str) -> None:
        try:
            await to_thread.run_sync(self._delete, key)
        except OSError as exc:
            raise KnowledgeStorageUnavailableError from exc

    def _path(self, key: str) -> Path:
        parts = key.split("/")
        if len(parts) != 4 or parts[3] != "content":
            raise KnowledgeStorageUnavailableError
        try:
            UUID(parts[0])
            UUID(parts[1])
            UUID(parts[2])
        except ValueError as exc:
            raise KnowledgeStorageUnavailableError from exc
        path = self._root.joinpath(*parts)
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(self._root):
            raise KnowledgeStorageUnavailableError
        return resolved

    def _put(self, key: str, source_path: Path) -> None:
        destination = self._path(key)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = destination.with_name(".uploading")
        try:
            with source_path.open("rb") as source, temporary.open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            temporary.chmod(0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _copy_to(self, key: str, destination_path: Path) -> None:
        with self._path(key).open("rb") as source, destination_path.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        destination_path.chmod(0o600)

    def _open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def _delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)
        parent = path.parent
        while parent != self._root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def knowledge_storage_key(organization_id: UUID, source_id: UUID, version_id: UUID) -> str:
    return f"{organization_id}/{source_id}/{version_id}/content"
