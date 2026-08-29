from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Protocol, cast
from uuid import uuid4

from alos.config import Settings


class ObjectStorageError(RuntimeError):
    """Raised when an object cannot be persisted or retrieved safely."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    provider: str
    bucket: str
    object_key: str
    etag: str | None


class ReadableStream(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


class ObjectStorage(Protocol):
    provider_name: str
    bucket_name: str

    def put(
        self,
        object_key: str,
        stream: BinaryIO,
        *,
        size_bytes: int,
        media_type: str,
        metadata: dict[str, str],
    ) -> StoredObject: ...

    def open(self, object_key: str) -> ReadableStream: ...

    def delete(self, object_key: str) -> None: ...


def _validated_key(object_key: str) -> PurePosixPath:
    key = PurePosixPath(object_key)
    if not object_key or key.is_absolute() or ".." in key.parts or "\\" in object_key:
        raise ObjectStorageError("Object key tidak valid")
    if any(part in {"", "."} for part in key.parts):
        raise ObjectStorageError("Object key tidak valid")
    return key


class FilesystemObjectStorage:
    provider_name = "FILESYSTEM"

    def __init__(self, root: Path, bucket_name: str) -> None:
        self._root = root.resolve()
        self.bucket_name = bucket_name

    def _path_for(self, object_key: str) -> Path:
        key = _validated_key(object_key)
        bucket_root = (self._root / self.bucket_name).resolve()
        destination = bucket_root.joinpath(*key.parts).resolve()
        if destination != bucket_root and bucket_root not in destination.parents:
            raise ObjectStorageError("Object key keluar dari direktori penyimpanan")
        return destination

    def put(
        self,
        object_key: str,
        stream: BinaryIO,
        *,
        size_bytes: int,
        media_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        del size_bytes, media_type, metadata
        destination = self._path_for(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.upload")
        try:
            stream.seek(0)
            with temporary.open("xb") as target:
                shutil.copyfileobj(stream, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            os.link(temporary, destination)
            temporary.unlink()
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise ObjectStorageError("Gagal menyimpan object ke filesystem") from exc
        return StoredObject(
            provider=self.provider_name,
            bucket=self.bucket_name,
            object_key=object_key,
            etag=None,
        )

    def open(self, object_key: str) -> ReadableStream:
        try:
            return self._path_for(object_key).open("rb")
        except (OSError, ObjectStorageError) as exc:
            raise ObjectStorageError("Object dokumen tidak tersedia") from exc

    def delete(self, object_key: str) -> None:
        try:
            self._path_for(object_key).unlink(missing_ok=True)
        except OSError as exc:
            raise ObjectStorageError("Gagal menghapus object kompensasi") from exc


class S3ObjectStorage:
    provider_name = "S3"

    def __init__(
        self,
        *,
        bucket_name: str,
        endpoint_url: str | None,
        region: str,
        access_key: str | None,
        secret_key: str | None,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket_name = bucket_name
        addressing_style = "path" if endpoint_url else "auto"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3=cast(Any, {"addressing_style": addressing_style}),
            ),
        )

    def put(
        self,
        object_key: str,
        stream: BinaryIO,
        *,
        size_bytes: int,
        media_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        _validated_key(object_key)
        try:
            stream.seek(0)
            response = self._client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=stream,
                ContentLength=size_bytes,
                ContentType=media_type,
                Metadata=metadata,
                IfNoneMatch="*",
            )
        except Exception as exc:
            raise ObjectStorageError("Gagal menyimpan object ke S3") from exc
        etag = response.get("ETag")
        return StoredObject(
            provider=self.provider_name,
            bucket=self.bucket_name,
            object_key=object_key,
            etag=etag.strip('"') if isinstance(etag, str) else None,
        )

    def open(self, object_key: str) -> ReadableStream:
        _validated_key(object_key)
        try:
            return self._client.get_object(Bucket=self.bucket_name, Key=object_key)["Body"]
        except Exception as exc:
            raise ObjectStorageError("Object dokumen tidak tersedia di S3") from exc

    def delete(self, object_key: str) -> None:
        _validated_key(object_key)
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=object_key)
        except Exception as exc:
            raise ObjectStorageError("Gagal menghapus object kompensasi dari S3") from exc


@lru_cache(maxsize=8)
def _storage_for_configuration(
    provider: str,
    bucket: str,
    path: str,
    endpoint: str | None,
    region: str,
    access_key: str | None,
    secret_key: str | None,
) -> ObjectStorage:
    if provider == "filesystem":
        return FilesystemObjectStorage(Path(path), bucket)
    return S3ObjectStorage(
        bucket_name=bucket,
        endpoint_url=endpoint,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
    )


def object_storage_for(settings: Settings) -> ObjectStorage:
    return _storage_for_configuration(
        settings.object_storage_provider,
        settings.object_storage_bucket,
        str(settings.resolved_object_storage_path),
        settings.object_storage_endpoint,
        settings.object_storage_region,
        settings.object_storage_access_key_value,
        settings.object_storage_secret_key_value,
    )
