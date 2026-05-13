"""
Local filesystem storage implementation.
Files stored in: {project_root}/storage/{tenant_id}/{property_id}/{conversation_id}/{message_id}/
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta
import aiofiles
import aiofiles.os

from app.services.storage.storage_service import StorageService
from app.utils.exceptions import UnauthorizedError, FileNotFoundError as FileNotFoundErrorApp


class LocalStorageService(StorageService):
    """Local filesystem storage implementation for chat files."""

    def __init__(self, base_path: str = "./storage"):
        """
        Initialize local storage service.
        
        Args:
            base_path: Base directory for storage (default: ./storage)
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_storage_path(
        self,
        tenant_id: UUID,
        property_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
    ) -> Path:
        """Generate the storage path for a file."""
        return (
            self.base_path
            / str(tenant_id)
            / str(property_id)
            / str(conversation_id)
            / str(message_id)
        )

    def _get_file_path(self, storage_key: str) -> Path:
        """Extract file path from storage key."""
        # storage_key format: "{tenant_id}/{property_id}/{conversation_id}/{message_id}/{filename}"
        return self.base_path / storage_key

    def _validate_access(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> None:
        """Validate that tenant/property can access this file."""
        # storage_key should start with tenant_id/property_id
        expected_prefix = f"{tenant_id}/{property_id}"
        if not storage_key.startswith(expected_prefix):
            raise UnauthorizedError(
                "Access denied to this file. Multi-tenant isolation enforced."
            )

    async def upload_file(
        self,
        tenant_id: UUID,
        property_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        file_content: bytes,
        file_name: str,
        file_type: str,
    ) -> str:
        """Upload a file to local storage."""
        # Create directory structure
        dir_path = self._get_storage_path(
            tenant_id, property_id, conversation_id, message_id
        )
        dir_path.mkdir(parents=True, exist_ok=True)

        # Generate unique filename to prevent conflicts
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_")
        file_path = dir_path / f"{timestamp}{file_name}"

        # Write file asynchronously
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        # Return storage key (relative path for later retrieval)
        storage_key = str(file_path.relative_to(self.base_path))
        return storage_key

    async def download_file(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> bytes:
        """Download a file from local storage."""
        # Validate access
        self._validate_access(storage_key, tenant_id, property_id)

        # Get file path
        file_path = self._get_file_path(storage_key)

        # Check existence
        if not await aiofiles.os.path.exists(file_path):
            raise FileNotFoundErrorApp(f"File not found: {storage_key}")

        # Read file
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()

        return content

    async def delete_file(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> bool:
        """Delete a file from local storage."""
        # Validate access
        self._validate_access(storage_key, tenant_id, property_id)

        # Get file path
        file_path = self._get_file_path(storage_key)

        # Delete if exists
        if await aiofiles.os.path.exists(file_path):
            await aiofiles.os.remove(file_path)

            # Try to clean up empty parent directories
            try:
                dir_path = file_path.parent
                if not any(dir_path.iterdir()):  # Empty
                    dir_path.rmdir()
            except (OSError, StopIteration):
                pass  # Directory not empty or doesn't exist

            return True

        return False

    async def get_url(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
        expiry_seconds: Optional[int] = None,
    ) -> str:
        """
        Get URL for a file.
        For local storage, returns a download endpoint path.
        In production, this would be served by FastAPI endpoint.
        """
        # Validate access
        self._validate_access(storage_key, tenant_id, property_id)

        # For local storage, return an API endpoint that serves the file
        # The actual endpoint would be: GET /v1/chats/files/{storage_key}
        return f"/v1/chats/files/{storage_key}"

    async def create_thumbnail(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
        width: int = 200,
        height: int = 200,
    ) -> Optional[str]:
        """
        Create thumbnail for image files.
        Requires PIL/Pillow to be installed.
        """
        try:
            from PIL import Image
        except ImportError:
            # Pillow not installed, skip thumbnail generation
            return None

        # Validate access
        self._validate_access(storage_key, tenant_id, property_id)

        # Get original file path
        file_path = self._get_file_path(storage_key)

        # Check if it's an image
        if not file_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            return None

        if not await aiofiles.os.path.exists(file_path):
            return None

        try:
            # Read image
            async with aiofiles.open(file_path, "rb") as f:
                image_content = await f.read()

            # Create thumbnail
            image = Image.open(io.BytesIO(image_content))
            image.thumbnail((width, height), Image.Resampling.LANCZOS)

            # Save thumbnail with special suffix
            thumbnail_path = file_path.parent / f"{file_path.stem}_thumb{file_path.suffix}"
            image.save(thumbnail_path)

            # Return thumbnail storage key
            return str(thumbnail_path.relative_to(self.base_path))

        except Exception:
            # Thumbnail generation failed
            return None


import io
