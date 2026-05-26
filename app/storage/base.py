"""
Storage Abstraction Layer - app/storage/base.py

Defines abstract storage interface and implementations for local and S3 storage.

Supports:
- Local file storage (development / fallback)
- AWS S3 backend (production)

API:
- upload_file(file_bytes, path, content_type) -> storage_key
- download_file(path) -> bytes
- delete_file(path) -> bool
- file_exists(path) -> bool
- get_file_size(path) -> int | None
- generate_signed_url(path, expiration_seconds) -> str
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    async def upload_file(
        self,
        file_bytes: bytes,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file and return storage key."""
        ...

    @abstractmethod
    async def download_file(self, path: str) -> bytes:
        """Download file and return bytes."""
        ...

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """Delete file. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Return True if the file exists."""
        ...

    @abstractmethod
    async def get_file_size(self, path: str) -> Optional[int]:
        """Return file size in bytes, or None if not found."""
        ...

    @abstractmethod
    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600,
    ) -> str:
        """Return a temporary URL for downloading the file."""
        ...


# ── Local Storage ─────────────────────────────────────────────────────────────

class LocalStorageBackend(StorageBackend):
    """
    Local file-system storage.
    Used for development and as a fallback when S3 is not configured.
    NOTE: ephemeral on Render free tier — do not use in production.
    """

    def __init__(self, base_path: str = "uploads/chat"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _full(self, path: str) -> str:
        if ".." in path:
            raise ValueError("Path traversal not allowed")
        return os.path.join(self.base_path, path)

    async def upload_file(
        self,
        file_bytes: bytes,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        full = self._full(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(file_bytes)
        return path

    async def download_file(self, path: str) -> bytes:
        full = self._full(path)
        if not os.path.exists(full):
            raise FileNotFoundError(f"File not found: {path}")
        with open(full, "rb") as fh:
            return fh.read()

    async def delete_file(self, path: str) -> bool:
        full = self._full(path)
        if not os.path.exists(full):
            return False
        os.remove(full)
        return True

    async def file_exists(self, path: str) -> bool:
        return os.path.exists(self._full(path))

    async def get_file_size(self, path: str) -> Optional[int]:
        full = self._full(path)
        return os.path.getsize(full) if os.path.exists(full) else None

    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600,
    ) -> str:
        import base64
        import json
        from datetime import datetime, timedelta

        payload = {
            "path": path,
            "expires_at": (
                datetime.utcnow() + timedelta(seconds=expiration_seconds)
            ).isoformat(),
        }
        token = base64.b64encode(json.dumps(payload).encode()).decode()
        return f"/api/v1/chat/media/download/{token}"


# ── S3 Storage ────────────────────────────────────────────────────────────────

class S3StorageBackend(StorageBackend):
    """
    AWS S3 storage backend for production use.

    Required env vars (set in Render dashboard):
        AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY
        AWS_REGION              (default: us-east-1)

    For chat/documents the bucket is private — access is via pre-signed URLs.
    For property images a separate public bucket is used (see properties.py).
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        region: str = "us-east-1",
    ):
        import boto3

        self.bucket_name = bucket_name
        self.region = region
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        logger.info(
            "S3StorageBackend initialised — bucket=%s region=%s",
            bucket_name,
            region,
        )

    # ── helpers ───────────────────────────────────────────

    def _run(self, fn):
        """Run a blocking boto3 call in the default thread pool."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, fn)

    # ── interface ─────────────────────────────────────────

    async def upload_file(
        self,
        file_bytes: bytes,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        await self._run(
            lambda: self._client.put_object(
                Bucket=self.bucket_name,
                Key=path,
                Body=file_bytes,
                ContentType=content_type,
            )
        )
        logger.debug("S3 upload OK — bucket=%s key=%s", self.bucket_name, path)
        return path

    async def download_file(self, path: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            response = await self._run(
                lambda: self._client.get_object(
                    Bucket=self.bucket_name, Key=path
                )
            )
            return response["Body"].read()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"S3 object not found: {path}") from exc
            raise

    async def delete_file(self, path: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            await self._run(
                lambda: self._client.delete_object(
                    Bucket=self.bucket_name, Key=path
                )
            )
            return True
        except ClientError as exc:
            logger.warning("S3 delete failed for %s: %s", path, exc)
            return False

    async def file_exists(self, path: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            await self._run(
                lambda: self._client.head_object(
                    Bucket=self.bucket_name, Key=path
                )
            )
            return True
        except ClientError:
            return False

    async def get_file_size(self, path: str) -> Optional[int]:
        from botocore.exceptions import ClientError

        try:
            response = await self._run(
                lambda: self._client.head_object(
                    Bucket=self.bucket_name, Key=path
                )
            )
            return response.get("ContentLength")
        except ClientError:
            return None

    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600,
    ) -> str:
        url = await self._run(
            lambda: self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": path},
                ExpiresIn=expiration_seconds,
            )
        )
        return url


# ── Factory & global instance ─────────────────────────────────────────────────

class StorageFactory:
    @staticmethod
    def create_backend(backend_type: str = "local", **config) -> StorageBackend:
        if backend_type == "local":
            return LocalStorageBackend(config.get("base_path", "uploads/chat"))
        elif backend_type == "s3":
            return S3StorageBackend(
                access_key=config["access_key"],
                secret_key=config["secret_key"],
                bucket_name=config["bucket_name"],
                region=config.get("region", "us-east-1"),
            )
        raise ValueError(f"Unknown storage backend: {backend_type!r}")


_storage_instance: Optional[StorageBackend] = None


def init_storage(backend_type: str = "local", **config) -> StorageBackend:
    global _storage_instance
    _storage_instance = StorageFactory.create_backend(backend_type, **config)
    return _storage_instance


def get_storage() -> StorageBackend:
    if _storage_instance is None:
        raise RuntimeError("Storage not initialised — call init_storage() first.")
    return _storage_instance
