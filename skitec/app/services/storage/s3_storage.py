"""
AWS S3 storage implementation.
For future migration from local storage.
Requires: boto3 and botocore packages
"""

from typing import Optional
from uuid import UUID
from datetime import timedelta

from app.services.storage.storage_service import StorageService


class S3StorageService(StorageService):
    """
    AWS S3 storage implementation for chat files.
    
    To be implemented when migrating to AWS.
    This template shows the interface that must be implemented.
    """

    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str,
        bucket_name: str,
    ):
        """
        Initialize S3 storage service.
        
        Args:
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            aws_region: AWS region (e.g., 'us-east-1')
            bucket_name: S3 bucket name
        """
        # TODO: Initialize boto3 S3 client
        # import boto3
        # self.s3_client = boto3.client(
        #     's3',
        #     aws_access_key_id=aws_access_key_id,
        #     aws_secret_access_key=aws_secret_access_key,
        #     region_name=aws_region
        # )
        # self.bucket_name = bucket_name
        pass

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
        """Upload file to S3."""
        # TODO: Implement S3 upload
        # Key format: {tenant_id}/{property_id}/{conversation_id}/{message_id}/{filename}
        # - Use server-side encryption
        # - Set metadata: tenant_id, property_id, conversation_id, message_id
        # - Return S3 key
        raise NotImplementedError("S3 upload not yet implemented")

    async def download_file(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> bytes:
        """Download file from S3."""
        # TODO: Implement S3 download with tenant/property validation
        raise NotImplementedError("S3 download not yet implemented")

    async def delete_file(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
    ) -> bool:
        """Delete file from S3."""
        # TODO: Implement S3 delete
        raise NotImplementedError("S3 delete not yet implemented")

    async def get_url(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
        expiry_seconds: Optional[int] = None,
    ) -> str:
        """
        Get pre-signed URL from S3.
        
        If expiry_seconds provided, creates temporary pre-signed URL.
        Otherwise, generates permanent URL.
        """
        # TODO: Implement pre-signed URL generation
        # - Validate tenant/property access
        # - Generate pre-signed URL valid for expiry_seconds (default: 1 hour)
        # - Return URL
        raise NotImplementedError("S3 pre-signed URL generation not yet implemented")

    async def create_thumbnail(
        self,
        storage_key: str,
        tenant_id: UUID,
        property_id: UUID,
        width: int = 200,
        height: int = 200,
    ) -> Optional[str]:
        """
        Create thumbnail using AWS Lambda or EC2.
        
        Could use AWS Lambda with PIL layer for serverless thumbnail generation.
        Or use EC2 instance with PIL pre-installed.
        """
        # TODO: Implement thumbnail generation
        # Option 1: Invoke Lambda function
        # Option 2: Use local PIL if needed
        raise NotImplementedError("S3 thumbnail generation not yet implemented")


# Migration guide when ready to implement S3:
"""
1. Install boto3: pip install boto3
2. Set up AWS credentials (IAM user with S3 access)
3. Create S3 bucket with:
   - Versioning enabled
   - Server-side encryption (SSE-S3)
   - Block public access
   - Lifecycle policy for old files
4. Implement all methods following the StorageService interface
5. Add S3StorageService to dependency injection
6. Update config to use S3 instead of LocalStorageService
7. Test file upload/download/delete operations
8. Verify multi-tenant isolation (check S3 metadata and key paths)
"""
