# S3 Integration Guide for KRA Revenue Reports

## Overview

The Monthly and Quarterly KRA APIs support S3 file uploads for revenue reports. This guide covers setup, configuration, and integration.

---

## 1. AWS S3 Setup

### Create S3 Bucket

```bash
aws s3api create-bucket \
  --bucket scitech-kra-reports \
  --region us-east-1
```

### Create IAM User for API Access

```bash
# Create user
aws iam create-user --user-name scitech-kra-uploader

# Create access key
aws iam create-access-key --user-name scitech-kra-uploader
```

Save the `AccessKeyId` and `SecretAccessKey` for environment configuration.

### Attach S3 Permissions

Create policy file `s3-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::scitech-kra-reports",
        "arn:aws:s3:::scitech-kra-reports/*"
      ]
    }
  ]
}
```

Attach the policy:

```bash
aws iam put-user-policy \
  --user-name scitech-kra-uploader \
  --policy-name S3KRAReportsAccess \
  --policy-document file://s3-policy.json
```

### Configure CORS

Create `cors.json`:

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
```

Apply CORS:

```bash
aws s3api put-bucket-cors \
  --bucket scitech-kra-reports \
  --cors-configuration file://cors.json
```

---

## 2. Environment Configuration

Add to `.env` file:

```env
# AWS S3 Configuration
AWS_S3_BUCKET_NAME=scitech-kra-reports
AWS_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_S3_ENDPOINT_URL=  # Leave empty for standard AWS S3
S3_FILE_UPLOAD_PREFIX=kra-submissions
```

For local development with MinIO (S3-compatible):

```env
AWS_S3_BUCKET_NAME=scitech-kra-reports
AWS_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_S3_ENDPOINT_URL=http://localhost:9000
S3_FILE_UPLOAD_PREFIX=kra-submissions
```

---

## 3. File Upload Workflow

### Option A: Client-Side Upload with Pre-Signed URLs (Recommended)

**Step 1: Generate Pre-Signed URL (Backend)**

Create endpoint `/kra/upload-url`:

```python
from datetime import timedelta
import boto3
from app.core.config import settings

def generate_presigned_url(filename: str, file_type: str) -> str:
    """Generate pre-signed URL for S3 file upload"""
    s3_client = boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    
    key = f"{settings.S3_FILE_UPLOAD_PREFIX}/{filename}"
    
    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET_NAME,
            "Key": key,
            "ContentType": file_type,
        },
        ExpiresIn=3600,  # 1 hour expiration
    )
    
    return presigned_url
```

**Step 2: Upload File from Client**

```javascript
// Client-side JavaScript
async function uploadRevenueReport(file) {
  // 1. Get pre-signed URL from backend
  const response = await fetch('/api/v1/kra/upload-url', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      filename: file.name,
      file_type: file.type
    })
  });
  
  const { presigned_url, s3_url } = await response.json();
  
  // 2. Upload directly to S3
  await fetch(presigned_url, {
    method: 'PUT',
    body: file,
    headers: {
      'Content-Type': file.type
    }
  });
  
  // 3. Submit KRA with S3 URL
  return await fetch('/api/v1/kra/monthly', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      month: 3,
      year: 2026,
      revenue_report_url: s3_url
    })
  });
}
```

### Option B: Direct Backend Upload

**Step 1: Upload File**

```bash
curl -X POST http://localhost:8000/api/v1/kra/upload \
  -H "Authorization: Bearer your_jwt_token" \
  -F "file=@revenue-report.pdf"
```

**Step 2: Submit KRA**

```bash
curl -X POST http://localhost:8000/api/v1/kra/monthly \
  -H "Authorization: Bearer your_jwt_token" \
  -H "Content-Type: application/json" \
  -d '{
    "month": 3,
    "year": 2026,
    "revenue_report_url": "https://s3.amazonaws.com/scitech-kra-reports/kra-submissions/revenue-report.pdf"
  }'
```

---

## 4. S3 Helper Utility

Create `app/utils/s3_handler.py`:

```python
"""S3 file handling utilities"""

import boto3
from datetime import timedelta
from typing import Optional
from app.core.config import settings


class S3Handler:
    """Handle S3 operations for KRA file uploads"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_S3_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        )
        self.bucket = settings.AWS_S3_BUCKET_NAME
        self.prefix = settings.S3_FILE_UPLOAD_PREFIX
    
    def generate_presigned_put_url(
        self,
        filename: str,
        content_type: str,
        expiration_hours: int = 1
    ) -> str:
        """Generate pre-signed URL for file upload"""
        key = f"{self.prefix}/{filename}"
        
        presigned_url = self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expiration_hours * 3600,
        )
        
        return presigned_url
    
    def generate_presigned_get_url(
        self,
        filename: str,
        expiration_hours: int = 24
    ) -> str:
        """Generate pre-signed URL for file download"""
        key = f"{self.prefix}/{filename}"
        
        presigned_url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
            },
            ExpiresIn=expiration_hours * 3600,
        )
        
        return presigned_url
    
    def get_public_url(self, filename: str) -> str:
        """Get public URL for S3 object"""
        key = f"{self.prefix}/{filename}"
        url = f"https://{self.bucket}.s3.{settings.AWS_S3_REGION}.amazonaws.com/{key}"
        return url
    
    def delete_file(self, filename: str) -> bool:
        """Delete file from S3"""
        try:
            key = f"{self.prefix}/{filename}"
            self.s3_client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            print(f"Error deleting S3 file: {e}")
            return False
    
    def upload_file(self, file_data: bytes, filename: str, content_type: str) -> str:
        """Upload file directly to S3"""
        try:
            key = f"{self.prefix}/{filename}"
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            return self.get_public_url(filename)
        except Exception as e:
            print(f"Error uploading to S3: {e}")
            raise
```

---

## 5. File Naming Convention

Recommended S3 folder structure:

```
s3://scitech-kra-reports/
├── kra-submissions/
│   ├── monthly/
│   │   ├── 2026/
│   │   │   ├── 01-revenue.pdf
│   │   │   ├── 02-revenue.pdf
│   │   │   └── 03-revenue.pdf
│   ├── quarterly/
│   │   ├── 2026/
│   │   │   ├── q1-revenue.pdf
│   │   │   ├── q2-revenue.pdf
│   │   │   └── q3-revenue.pdf
```

Filename pattern:

```python
# Monthly KRA
def generate_monthly_filename(month: int, year: int, user_id: int) -> str:
    return f"monthly/{year}/{month:02d}-revenue-user{user_id}.pdf"

# Quarterly KRA
def generate_quarterly_filename(quarter: int, year: int, user_id: int) -> str:
    return f"quarterly/{year}/q{quarter}-revenue-user{user_id}.pdf"
```

---

## 6. Error Handling

Common S3 errors:

```python
from botocore.exceptions import ClientError

try:
    response = s3_client.put_object(...)
except ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchBucket':
        print("S3 bucket does not exist")
    elif e.response['Error']['Code'] == 'AccessDenied':
        print("Access denied to S3 bucket")
    else:
        print(f"S3 error: {e}")
```

---

## 7. Testing S3 Integration

### Local Testing with MinIO

```bash
# Start MinIO
docker run -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data

# Create bucket
aws s3api create-bucket \
  --bucket scitech-kra-reports \
  --endpoint-url http://localhost:9000 \
  --region us-east-1
```

Update `.env`:

```env
AWS_S3_ENDPOINT_URL=http://localhost:9000
```

### Test Upload

```python
import pytest
from app.utils.s3_handler import S3Handler

@pytest.mark.asyncio
async def test_s3_upload():
    handler = S3Handler()
    
    # Test upload
    url = handler.upload_file(
        file_data=b"Test revenue data",
        filename="test-revenue.pdf",
        content_type="application/pdf"
    )
    
    assert "scitech-kra-reports" in url
    assert "test-revenue.pdf" in url
```

---

## 8. Best Practices

1. **Use Pre-Signed URLs**: Let clients upload directly to S3
2. **Set Expiration**: Pre-signed URLs expire after 1 hour by default
3. **Validate Content-Type**: Only allow PDF and specific file types
4. **Implement Virus Scanning**: Use S3 Object Lambda or Lambda trigger
5. **Monitor Costs**: S3 charges for storage and API calls
6. **Organize Files**: Use folder structure for easy retrieval
7. **Enable Versioning**: Keep file history in S3
8. **Set Lifecycle Policies**: Archive old files automatically

---

## 9. Security Considerations

1. **IAM Permissions**: Limit API user to specific S3 operations
2. **Encryption**: Enable S3-SSE for data at rest
3. **HTTPS Only**: Use secure URLs for transfers
4. **Access Logs**: Enable S3 access logging
5. **Block Public Access**: Disable public bucket access
6. **MFA Delete**: Require MFA for object deletion
7. **File Size Limits**: Validate file size before upload

---

## 10. Troubleshooting

### Bucket Access Denied

```
Error: Access Denied
```

Solution: Check IAM permissions and credentials

### File Not Found After Upload

```
Error: NoSuchKey
```

Solution: Verify S3 key path matches your naming convention

### CORS Issues

```
Error: CORS policy blocked request
```

Solution: Update CORS configuration as shown in section 1

### Pre-Signed URL Expired

```
Error: Request has expired
```

Solution: Generate new pre-signed URL (max 1-hour validity)

---

## 11. Monitoring

Monitor S3 usage with CloudWatch:

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

# Track uploads
cloudwatch.put_metric_data(
    Namespace='SciTech',
    MetricData=[
        {
            'MetricName': 'KRAFileUploads',
            'Value': 1,
            'Unit': 'Count'
        }
    ]
)
```

---

## 12. Cost Estimation

Monthly cost for 100 files (average 2MB each):

```
Storage: 100 files × 2MB × $0.023/GB = $0.46
Requests: 100 PUT × $0.005/1K + 100 GET × $0.0004/1K = $0.54
Total: ~$1.00/month
```

---

## References

- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [Boto3 S3 Reference](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- [MinIO Documentation](https://min.io/docs/minio/kubernetes/upstream/)
- [S3 Security Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/dev/BestPractices.html)
