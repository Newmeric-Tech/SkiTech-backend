"""
Storage abstraction layer for chat file uploads.
Supports multiple backends: Local filesystem, AWS S3, etc.
"""

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID
import mimetypes


class StorageService(ABC):
    """Abstract base class for file storage implementations."""

    @abstractmethod
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
        """
        Upload a file and return its storage key/URL.
        
        Args:
            tenant_id: Tenant identifier for multi-tenant isolation
            property_id: Property identifier for property isolation
            conversation_id: Conversation this file belongs to
            message_id: Message this file is attached to
            file_content: Raw file bytes
            file_name: Original file name
            file_type: MIME type (e.g., 'image/jpeg', 'application/pdf')
            
        Returns:
            Storage key/URL string for later retrieval
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> bytes:
        """
        Download a file by storage key.
        Validates tenant/property access.
        
        Args:
            storage_key: The storage identifier from upload_file()
            tenant_id: Tenant making the request
            property_id: Property making the request
            
        Returns:
            File content as bytes
            
        Raises:
            UnauthorizedError: If tenant/property not authorized
            FileNotFoundError: If file not found
        """
        pass

    @abstractmethod
    async def delete_file(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> bool:
        """
        Delete a file by storage key.
        Validates tenant/property access.
        
        Args:
            storage_key: The storage identifier
            tenant_id: Tenant making the request
            property_id: Property making the request
            
        Returns:
            True if deleted successfully
            
        Raises:
            UnauthorizedError: If tenant/property not authorized
        """
        pass

    @abstractmethod
    async def get_url(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
        expiry_seconds: Optional[int] = None,
    ) -> str:
        """
        Get a URL/URI for a file.
        For local storage: file:// URL or download endpoint
        For S3: Pre-signed URL (temporary if expiry_seconds provided)
        
        Args:
            storage_key: The storage identifier
            tenant_id: Tenant making the request
            property_id: Property making the request
            expiry_seconds: For S3 pre-signed URLs
            
        Returns:
            URL string
            
        Raises:
            UnauthorizedError: If tenant/property not authorized
        """
        pass

    @abstractmethod
    async def create_thumbnail(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
        width: int = 200,
        height: int = 200,
    ) -> Optional[str]:
        """
        Create a thumbnail for image files.
        Optional - may return None if not supported.
        
        Args:
            storage_key: The storage identifier
            tenant_id: Tenant making the request
            property_id: Property making the request
            width: Thumbnail width
            height: Thumbnail height
            
        Returns:
            Thumbnail storage key, or None if creation failed
        """
        pass

    @staticmethod
    def get_mime_type(file_name: str) -> str:
        """Get MIME type from file name."""
        mime_type, _ = mimetypes.guess_type(file_name)
        return mime_type or "application/octet-stream"
