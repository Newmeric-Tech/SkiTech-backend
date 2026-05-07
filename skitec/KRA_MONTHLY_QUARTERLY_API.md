# Monthly and Quarterly KRA Submission API Documentation

## Overview

This document describes the Monthly and Quarterly KRA (Key Result Areas) submission APIs for the SciTech platform. These endpoints support revenue report submissions with S3 file upload integration.

## Base URL

```
http://localhost:8000/api/v1/kra
```

## Authentication

All endpoints require a valid JWT token in the `Authorization` header:

```
Authorization: Bearer <your_jwt_token>
```

The token must contain:
- `tenant_id`: The user's tenant identifier
- `user_id`: The user's unique identifier

---

## Monthly KRA Endpoints

### 1. Create Monthly KRA Submission

**Endpoint:** `POST /monthly`

**Description:** Submit a monthly KRA with optional revenue report file URL.

**Request Body:**

```json
{
  "month": 3,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf",
  "notes": "March 2026 revenue report with quarterly analysis"
}
```

**Request Fields:**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `month` | integer | Yes | 1-12 | Month (1=January, 12=December) |
| `year` | integer | Yes | 2024-2099 | Year of the submission |
| `revenue_report_url` | string | No | Valid S3 URL | Pre-signed S3 URL for the revenue report file |
| `notes` | string | No | Max 5000 chars | Additional notes or comments |

**Response (201 Created):**

```json
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "month": 3,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf",
  "notes": "March 2026 revenue report with quarterly analysis",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

**Error Responses:**

- **409 Conflict** - Monthly KRA for this month/year already exists
```json
{
  "detail": "Monthly KRA already exists for 3/2026"
}
```

- **422 Unprocessable Entity** - Invalid input
```json
{
  "detail": [
    {
      "loc": ["body", "month"],
      "msg": "ensure this value is less than or equal to 12",
      "type": "value_error.number.not_le"
    }
  ]
}
```

**cURL Example:**

```bash
curl -X POST http://localhost:8000/api/v1/kra/monthly \
  -H "Authorization: Bearer your_jwt_token" \
  -H "Content-Type: application/json" \
  -d '{
    "month": 3,
    "year": 2026,
    "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf",
    "notes": "March 2026 submission"
  }'
```

---

### 2. List Monthly KRAs

**Endpoint:** `GET /monthly`

**Description:** List all monthly KRAs for the current tenant with pagination.

**Query Parameters:**

| Parameter | Type | Required | Default | Constraints | Description |
|-----------|------|----------|---------|-------------|-------------|
| `skip` | integer | No | 0 | ≥ 0 | Number of records to skip for pagination |
| `limit` | integer | No | 20 | 1-100 | Number of records to return |
| `user_id` | integer | No | None | - | Filter by specific user (optional) |

**Response (200 OK):**

```json
{
  "total": 12,
  "skip": 0,
  "limit": 20,
  "items": [
    {
      "id": 1,
      "tenant_id": 1,
      "user_id": 1,
      "month": 3,
      "year": 2026,
      "is_submitted": true,
      "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf",
      "created_at": "2026-04-21T10:30:00Z"
    }
  ]
}
```

**cURL Example:**

```bash
curl -X GET "http://localhost:8000/api/v1/kra/monthly?skip=0&limit=20" \
  -H "Authorization: Bearer your_jwt_token"
```

---

### 3. Get Monthly KRA by ID

**Endpoint:** `GET /monthly/{kra_id}`

**Description:** Retrieve a specific monthly KRA by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kra_id` | integer | Yes | Monthly KRA ID |

**Response (200 OK):**

```json
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "month": 3,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf",
  "notes": "March 2026 revenue report",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

**Error Responses:**

- **404 Not Found**
```json
{
  "detail": "Monthly KRA not found"
}
```

**cURL Example:**

```bash
curl -X GET http://localhost:8000/api/v1/kra/monthly/1 \
  -H "Authorization: Bearer your_jwt_token"
```

---

### 4. Update Monthly KRA

**Endpoint:** `PUT /monthly/{kra_id}`

**Description:** Update a monthly KRA (e.g., update revenue report URL).

**Request Body:**

```json
{
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue-v2.pdf",
  "notes": "Updated March report"
}
```

**Response (200 OK):**

Same as Get Monthly KRA response with updated values.

**cURL Example:**

```bash
curl -X PUT http://localhost:8000/api/v1/kra/monthly/1 \
  -H "Authorization: Bearer your_jwt_token" \
  -H "Content-Type: application/json" \
  -d '{
    "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue-v2.pdf"
  }'
```

---

### 5. Delete Monthly KRA

**Endpoint:** `DELETE /monthly/{kra_id}`

**Description:** Delete (soft delete) a monthly KRA.

**Response (204 No Content)**

No response body.

**cURL Example:**

```bash
curl -X DELETE http://localhost:8000/api/v1/kra/monthly/1 \
  -H "Authorization: Bearer your_jwt_token"
```

---

## Quarterly KRA Endpoints

### 1. Create Quarterly KRA Submission

**Endpoint:** `POST /quarterly`

**Description:** Submit a quarterly KRA with optional revenue report file URL.

**Request Body:**

```json
{
  "quarter": 1,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf",
  "notes": "Q1 2026 revenue report"
}
```

**Request Fields:**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `quarter` | integer | Yes | 1-4 | Quarter (1=Q1, 4=Q4) |
| `year` | integer | Yes | 2024-2099 | Year of the submission |
| `revenue_report_url` | string | No | Valid S3 URL | Pre-signed S3 URL for the revenue report file |
| `notes` | string | No | Max 5000 chars | Additional notes or comments |

**Response (201 Created):**

```json
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "quarter": 1,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf",
  "notes": "Q1 2026 revenue report",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

**Error Responses:**

- **409 Conflict** - Quarterly KRA for this quarter/year already exists
```json
{
  "detail": "Quarterly KRA already exists for Q1/2026"
}
```

- **422 Unprocessable Entity** - Invalid input
```json
{
  "detail": [
    {
      "loc": ["body", "quarter"],
      "msg": "ensure this value is less than or equal to 4",
      "type": "value_error.number.not_le"
    }
  ]
}
```

**cURL Example:**

```bash
curl -X POST http://localhost:8000/api/v1/kra/quarterly \
  -H "Authorization: Bearer your_jwt_token" \
  -H "Content-Type: application/json" \
  -d '{
    "quarter": 1,
    "year": 2026,
    "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf",
    "notes": "Q1 2026 submission"
  }'
```

---

### 2. List Quarterly KRAs

**Endpoint:** `GET /quarterly`

**Description:** List all quarterly KRAs for the current tenant with pagination.

**Query Parameters:**

| Parameter | Type | Required | Default | Constraints | Description |
|-----------|------|----------|---------|-------------|-------------|
| `skip` | integer | No | 0 | ≥ 0 | Number of records to skip for pagination |
| `limit` | integer | No | 20 | 1-100 | Number of records to return |
| `user_id` | integer | No | None | - | Filter by specific user (optional) |

**Response (200 OK):**

```json
{
  "total": 4,
  "skip": 0,
  "limit": 20,
  "items": [
    {
      "id": 1,
      "tenant_id": 1,
      "user_id": 1,
      "quarter": 1,
      "year": 2026,
      "is_submitted": true,
      "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf",
      "created_at": "2026-04-21T10:30:00Z"
    }
  ]
}
```

---

### 3. Get Quarterly KRA by ID

**Endpoint:** `GET /quarterly/{kra_id}`

**Description:** Retrieve a specific quarterly KRA by ID.

**Response (200 OK):**

```json
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "quarter": 1,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf",
  "notes": "Q1 2026 revenue report",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

---

### 4. Update Quarterly KRA

**Endpoint:** `PUT /quarterly/{kra_id}`

**Description:** Update a quarterly KRA.

**Request Body:**

```json
{
  "revenue_report_url": "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue-v2.pdf"
}
```

---

### 5. Delete Quarterly KRA

**Endpoint:** `DELETE /quarterly/{kra_id}`

**Description:** Delete (soft delete) a quarterly KRA.

**Response (204 No Content)**

---

## S3 File Upload Integration

### Prerequisites

1. **AWS S3 Configuration** - Set environment variables:
   ```
   AWS_S3_BUCKET_NAME=your-bucket-name
   AWS_S3_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   ```

2. **S3 Bucket Permissions** - Ensure the bucket has proper CORS configuration for file uploads.

### File Upload Workflow

1. **Client-side Upload** (Recommended approach):
   - Generate pre-signed S3 URL from your S3 service
   - Upload file directly to S3 using the pre-signed URL
   - Get the S3 file URL after upload

2. **Submit KRA with File URL**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/kra/monthly \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "month": 3,
       "year": 2026,
       "revenue_report_url": "https://your-bucket.s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf"
     }'
   ```

### File URL Format

S3 URLs follow this pattern:
```
https://{bucket-name}.s3.{region}.amazonaws.com/{prefix}/{filename}
```

Example:
```
https://scitech-kra-reports.s3.us-east-1.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf
```

---

## Validation Rules

### Monthly KRA

- **Month**: Must be between 1-12
- **Year**: Must be between 2024-2099
- **Past/Future Check**: Cannot submit for future months
- **Uniqueness**: Only one monthly KRA per user per month/year combination

### Quarterly KRA

- **Quarter**: Must be between 1-4 (Q1, Q2, Q3, Q4)
- **Year**: Must be between 2024-2099
- **Past/Future Check**: Cannot submit for future quarters
- **Uniqueness**: Only one quarterly KRA per user per quarter/year combination

### Revenue Report URL

- **Format**: Must be a valid S3 URL
- **Optional**: Can be null/empty during creation
- **Updateable**: Can be updated after initial submission

---

## Multi-Tenancy

All KRA endpoints enforce strict tenant-level isolation:

- Users can only view their own tenant's KRAs
- KRAs created by one tenant are invisible to other tenants
- The `tenant_id` is extracted from the JWT token automatically

---

## Error Handling

All endpoints return standardized error responses:

**400 Bad Request** - Invalid input format
```json
{
  "detail": "Invalid request body"
}
```

**401 Unauthorized** - Missing or invalid JWT token
```json
{
  "detail": "Not authenticated"
}
```

**404 Not Found** - Resource not found
```json
{
  "detail": "Monthly KRA not found"
}
```

**409 Conflict** - Resource already exists
```json
{
  "detail": "Monthly KRA already exists for 3/2026"
}
```

**422 Unprocessable Entity** - Validation failed
```json
{
  "detail": [
    {
      "loc": ["body", "month"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Rate Limiting

No rate limiting is currently applied. Future versions may implement:
- Per-user rate limits
- Per-tenant rate limits
- Sliding window throttling

---

## Pagination

All list endpoints support cursor-based pagination:

- **skip**: Number of records to skip (default: 0)
- **limit**: Number of records to return (default: 20, max: 100)

Example:
```bash
GET /monthly?skip=20&limit=20  # Returns records 21-40
```

---

## Examples

### Complete Workflow: Monthly KRA Submission

1. **Upload file to S3** (client-side or separate API)
   ```bash
   # Use pre-signed URL to upload
   curl -X PUT "https://your-bucket.s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf" \
     --data-binary @revenue-report.pdf
   ```

2. **Submit KRA with file URL**
   ```bash
   curl -X POST http://localhost:8000/api/v1/kra/monthly \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "month": 3,
       "year": 2026,
       "revenue_report_url": "https://your-bucket.s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf"
     }'
   ```

3. **Verify submission**
   ```bash
   curl -X GET http://localhost:8000/api/v1/kra/monthly/1 \
     -H "Authorization: Bearer your_jwt_token"
   ```

### Complete Workflow: Quarterly KRA Submission

1. **Submit quarterly KRA**
   ```bash
   curl -X POST http://localhost:8000/api/v1/kra/quarterly \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "quarter": 1,
       "year": 2026,
       "revenue_report_url": "https://your-bucket.s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf"
     }'
   ```

2. **List all quarters for 2026**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/kra/quarterly?user_id=1" \
     -H "Authorization: Bearer your_jwt_token"
   ```

---

## Related Documentation

- [Database Schema](../STRUCTURE.md)
- [API Overview](./README.md)
- [Authentication Guide](../core/security.md)
- [S3 Setup Guide](../services/s3-setup.md)
