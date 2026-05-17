"""
Storage Abstraction Layer - app/storage/base.py

Defines abstract storage interface and implementations for local and S3 storage.

Supports:
- Local file storage (current implementation)
- AWS S3 backend (future, drop-in replacement)
- Easy migration without code changes

API:
- upload_file(file_bytes, path): Upload file
- download_file(path): Download file
- delete_file(path): Delete file
- generate_signed_url(path): Get temporary download URL
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime, timedelta


class StorageBackend(ABC):
    """Abstract storage backend interface"""

    @abstractmethod
    async def upload_file(
        self,
        file_bytes: bytes,
        path: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload file to storage.
        
        Args:
            file_bytes: File content
            path: Destination path (e.g., "conversations/{conv_id}/messages/{msg_id}/file.pdf")
            content_type: MIME type
            
        Returns:
            Storage key/path for retrieval
        """
        pass

    @abstractmethod
    async def download_file(self, path: str) -> bytes:
        """
        Download file from storage.
        
        Args:
            path: Storage path
            
        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """
        Delete file from storage.
        
        Args:
            path: Storage path
            
        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if file exists in storage"""
        pass

    @abstractmethod
    async def get_file_size(self, path: str) -> Optional[int]:
        """Get file size in bytes, or None if not found"""
        pass

    @abstractmethod
    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600
    ) -> str:
        """
        Generate temporary download URL.
        
        Args:
            path: Storage path
            expiration_seconds: URL expiration time
            
        Returns:
            Signed URL for download
        """
        pass


class LocalStorageBackend(StorageBackend):
    """
    Local file system storage implementation.
    
    Stores files in /var/chat_storage or configured directory.
    Used as default until S3 is configured.
    """

    def __init__(self, base_path: str = "/var/chat_storage"):
        """
        Initialize local storage.
        
        Args:
            base_path: Base directory for file storage
        """
        self.base_path = base_path
        self._ensure_directory(base_path)

    def _ensure_directory(self, path: str) -> None:
        """Ensure directory exists, create if needed"""
        import os
        os.makedirs(path, exist_ok=True)

    def _get_full_path(self, path: str) -> str:
        """Get full file path"""
        import os
        # Prevent path traversal attacks
        if ".." in path:
            raise ValueError("Invalid path: cannot contain '..'")
        return os.path.join(self.base_path, path)

    async def upload_file(
        self,
        file_bytes: bytes,
        path: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload file to local storage.
        
        Path structure:
        conversations/{conversation_id}/messages/{message_id}/filename
        """
        import os
        
        full_path = self._get_full_path(path)
        
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Write file
        with open(full_path, "wb") as f:
            f.write(file_bytes)
        
        return path  # Return relative path

    async def download_file(self, path: str) -> bytes:
        """Download file from local storage"""
        full_path = self._get_full_path(path)
        
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {path}")
        
        with open(full_path, "rb") as f:
            return f.read()

    async def delete_file(self, path: str) -> bool:
        """Delete file from local storage"""
        import os
        
        full_path = self._get_full_path(path)
        
        if not os.path.exists(full_path):
            return False
        
        os.remove(full_path)
        return True

    async def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        import os
        full_path = self._get_full_path(path)
        return os.path.exists(full_path)

    async def get_file_size(self, path: str) -> Optional[int]:
        """Get file size"""
        import os
        full_path = self._get_full_path(path)
        
        if not os.path.exists(full_path):
            return None
        
        return os.path.getsize(full_path)

    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600
    ) -> str:
        """
        Generate temporary download URL for local storage.
        
        For local storage, returns a base64-encoded path that backend validates.
        In production with S3, this would be a real signed URL.
        
        TODO: Implement proper temporary token system with database tracking
        """
        import base64
        import json
        from datetime import datetime, timedelta
        
        # Create token payload
        payload = {
            "path": path,
            "expires_at": (datetime.utcnow() + timedelta(seconds=expiration_seconds)).isoformat()
        }
        
        # Encode as JSON and base64
        json_str = json.dumps(payload)
        token = base64.b64encode(json_str.encode()).decode()
        
        # In real implementation, store token in Redis with expiration
        # For now, return base64 encoded path
        return f"/api/v1/chat/media/download/{token}"


class S3StorageBackend(StorageBackend):
    """
    AWS S3 storage implementation (future).
    
    Configuration via environment:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_S3_BUCKET_NAME
    - AWS_S3_REGION
    
    NOTE: Drop-in replacement for LocalStorageBackend
    No code changes needed except configuration
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        region: str = "us-east-1"
    ):
        """Initialize S3 storage"""
        # TODO: Initialize boto3 client when implementing
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.region = region
        # self.s3_client = boto3.client('s3', ...)

    async def upload_file(
        self,
        file_bytes: bytes,
        path: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """Upload file to S3"""
        # TODO: Implement S3 upload
        # self.s3_client.put_object(
        #     Bucket=self.bucket_name,
        #     Key=path,
        #     Body=file_bytes,
        #     ContentType=content_type
        # )
        raise NotImplementedError("S3 backend coming soon")

    async def download_file(self, path: str) -> bytes:
        """Download file from S3"""
        # TODO: Implement S3 download
        raise NotImplementedError("S3 backend coming soon")

    async def delete_file(self, path: str) -> bool:
        """Delete file from S3"""
        # TODO: Implement S3 delete
        raise NotImplementedError("S3 backend coming soon")

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in S3"""
        # TODO: Implement S3 check
        raise NotImplementedError("S3 backend coming soon")

    async def get_file_size(self, path: str) -> Optional[int]:
        """Get file size from S3"""
        # TODO: Implement S3 get size
        raise NotImplementedError("S3 backend coming soon")

    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600
    ) -> str:
        """Generate S3 signed URL"""
        # TODO: Implement S3 signed URL
        # return self.s3_client.generate_presigned_url(
        #     'get_object',
        #     Params={'Bucket': self.bucket_name, 'Key': path},
        #     ExpiresIn=expiration_seconds
        # )
        raise NotImplementedError("S3 backend coming soon")


class StorageFactory:
    """Factory to create storage backend based on configuration"""

    @staticmethod
    def create_backend(
        backend_type: str = "local",
        **config
    ) -> StorageBackend:
        """
        Create storage backend.
        
        Args:
            backend_type: 'local' or 's3'
            **config: Backend-specific configuration
            
        Returns:
            StorageBackend instance
        """
        if backend_type == "local":
            base_path = config.get("base_path", "/var/chat_storage")
            return LocalStorageBackend(base_path)
        
        elif backend_type == "s3":
            return S3StorageBackend(
                access_key=config["access_key"],
                secret_key=config["secret_key"],
                bucket_name=config["bucket_name"],
                region=config.get("region", "us-east-1")
            )
        
        else:
            raise ValueError(f"Unknown storage backend: {backend_type}")


# Default storage instance (configured at app startup)
_storage_instance: Optional[StorageBackend] = None


def init_storage(backend_type: str = "local", **config) -> StorageBackend:
    """Initialize global storage instance"""
    global _storage_instance
    _storage_instance = StorageFactory.create_backend(backend_type, **config)
    return _storage_instance


def get_storage() -> StorageBackend:
    """Get global storage instance"""
    if _storage_instance is None:
        raise RuntimeError("Storage not initialized. Call init_storage() first.")
    return _storage_instance
