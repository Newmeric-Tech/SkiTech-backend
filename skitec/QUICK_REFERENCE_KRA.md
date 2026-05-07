# Quick Reference: Monthly & Quarterly KRA APIs

## Endpoints at a Glance

### Monthly KRA Endpoints
```
GET    /api/v1/kra/monthly              - List monthly KRAs
POST   /api/v1/kra/monthly              - Create monthly KRA
GET    /api/v1/kra/monthly/{id}         - Get monthly KRA
PUT    /api/v1/kra/monthly/{id}         - Update monthly KRA
DELETE /api/v1/kra/monthly/{id}         - Delete monthly KRA
```

### Quarterly KRA Endpoints
```
GET    /api/v1/kra/quarterly            - List quarterly KRAs
POST   /api/v1/kra/quarterly            - Create quarterly KRA
GET    /api/v1/kra/quarterly/{id}       - Get quarterly KRA
PUT    /api/v1/kra/quarterly/{id}       - Update quarterly KRA
DELETE /api/v1/kra/quarterly/{id}       - Delete quarterly KRA
```

---

## Request/Response Examples

### Create Monthly KRA

```json
POST /api/v1/kra/monthly

{
  "month": 3,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-03-revenue.pdf",
  "notes": "March 2026 submission"
}

HTTP 201 Created
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "month": 3,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-03-revenue.pdf",
  "notes": "March 2026 submission",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

### Create Quarterly KRA

```json
POST /api/v1/kra/quarterly

{
  "quarter": 1,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-q1-revenue.pdf",
  "notes": "Q1 2026 submission"
}

HTTP 201 Created
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "quarter": 1,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-q1-revenue.pdf",
  "notes": "Q1 2026 submission",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:30:00Z"
}
```

### List with Pagination

```
GET /api/v1/kra/monthly?skip=0&limit=20

HTTP 200 OK
{
  "total": 12,
  "skip": 0,
  "limit": 20,
  "items": [...]
}
```

### Update Revenue Report

```json
PUT /api/v1/kra/monthly/1

{
  "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-03-revenue-v2.pdf"
}

HTTP 200 OK
{
  "id": 1,
  "tenant_id": 1,
  "user_id": 1,
  "month": 3,
  "year": 2026,
  "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-03-revenue-v2.pdf",
  "notes": "March 2026 submission",
  "is_submitted": true,
  "created_at": "2026-04-21T10:30:00Z",
  "updated_at": "2026-04-21T10:31:00Z"
}
```

### Delete KRA

```
DELETE /api/v1/kra/monthly/1

HTTP 204 No Content
(no response body)
```

---

## Field Reference

### Monthly KRA

| Field | Type | Required | Valid Range | Notes |
|-------|------|----------|-------------|-------|
| month | int | Yes | 1-12 | Month number |
| year | int | Yes | 2024-2099 | Cannot be future |
| revenue_report_url | string | No | Valid URL | S3 file URL |
| notes | string | No | Any | Additional info |
| is_submitted | bool | No | - | Auto set to true |

### Quarterly KRA

| Field | Type | Required | Valid Range | Notes |
|-------|------|----------|-------------|-------|
| quarter | int | Yes | 1-4 | Q1, Q2, Q3, Q4 |
| year | int | Yes | 2024-2099 | Cannot be future |
| revenue_report_url | string | No | Valid URL | S3 file URL |
| notes | string | No | Any | Additional info |
| is_submitted | bool | No | - | Auto set to true |

---

## Common Errors

### 409 Conflict - Duplicate Submission
```json
{
  "detail": "Monthly KRA already exists for 3/2026"
}
```
**Solution**: Update existing KRA or check if already submitted

### 404 Not Found
```json
{
  "detail": "Monthly KRA not found"
}
```
**Solution**: Verify KRA ID exists and belongs to your tenant

### 422 Unprocessable Entity - Validation Error
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
**Solution**: Check field values against valid ranges

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```
**Solution**: Provide valid JWT token in Authorization header

---

## cURL Cheat Sheet

### Create Monthly KRA
```bash
curl -X POST http://localhost:8000/api/v1/kra/monthly \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"month":3,"year":2026,"revenue_report_url":"https://...pdf"}'
```

### List Monthly KRAs
```bash
curl -X GET "http://localhost:8000/api/v1/kra/monthly?skip=0&limit=20" \
  -H "Authorization: Bearer TOKEN"
```

### Get Specific Monthly KRA
```bash
curl -X GET http://localhost:8000/api/v1/kra/monthly/1 \
  -H "Authorization: Bearer TOKEN"
```

### Update Monthly KRA
```bash
curl -X PUT http://localhost:8000/api/v1/kra/monthly/1 \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"revenue_report_url":"https://...pdf-v2"}'
```

### Delete Monthly KRA
```bash
curl -X DELETE http://localhost:8000/api/v1/kra/monthly/1 \
  -H "Authorization: Bearer TOKEN"
```

### Create Quarterly KRA
```bash
curl -X POST http://localhost:8000/api/v1/kra/quarterly \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"quarter":1,"year":2026,"revenue_report_url":"https://...pdf"}'
```

---

## Python SDK Example

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/kra"
TOKEN = "your_jwt_token"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Create monthly KRA
monthly_data = {
    "month": 3,
    "year": 2026,
    "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-03-revenue.pdf",
    "notes": "March 2026"
}

response = requests.post(f"{BASE_URL}/monthly", json=monthly_data, headers=headers)
kra_id = response.json()["id"]

# List monthly KRAs
response = requests.get(f"{BASE_URL}/monthly", headers=headers)
kras = response.json()["items"]

# Get specific KRA
response = requests.get(f"{BASE_URL}/monthly/{kra_id}", headers=headers)
kra = response.json()

# Update KRA
update_data = {
    "revenue_report_url": "https://s3.amazonaws.com/bucket/2026-03-revenue-v2.pdf"
}
response = requests.put(f"{BASE_URL}/monthly/{kra_id}", json=update_data, headers=headers)

# Delete KRA
response = requests.delete(f"{BASE_URL}/monthly/{kra_id}", headers=headers)

# Same pattern for quarterly endpoints
quarterly_data = {"quarter": 1, "year": 2026}
response = requests.post(f"{BASE_URL}/quarterly", json=quarterly_data, headers=headers)
```

---

## JavaScript/TypeScript Example

```typescript
const BASE_URL = "http://localhost:8000/api/v1/kra";
const TOKEN = "your_jwt_token";

const headers = {
  "Authorization": `Bearer ${TOKEN}`,
  "Content-Type": "application/json"
};

// Create monthly KRA
async function createMonthlyKRA(month: number, year: number, url?: string) {
  const response = await fetch(`${BASE_URL}/monthly`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      month,
      year,
      revenue_report_url: url,
      notes: `${month}/${year} submission`
    })
  });
  return await response.json();
}

// List monthly KRAs
async function listMonthlyKRAs(skip = 0, limit = 20) {
  const response = await fetch(`${BASE_URL}/monthly?skip=${skip}&limit=${limit}`, {
    method: "GET",
    headers
  });
  return await response.json();
}

// Get specific KRA
async function getMonthlyKRA(id: number) {
  const response = await fetch(`${BASE_URL}/monthly/${id}`, {
    method: "GET",
    headers
  });
  return await response.json();
}

// Update KRA
async function updateMonthlyKRA(id: number, url: string) {
  const response = await fetch(`${BASE_URL}/monthly/${id}`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ revenue_report_url: url })
  });
  return await response.json();
}

// Delete KRA
async function deleteMonthlyKRA(id: number) {
  await fetch(`${BASE_URL}/monthly/${id}`, {
    method: "DELETE",
    headers
  });
}

// Usage
const kra = await createMonthlyKRA(3, 2026, "https://s3.amazonaws.com/bucket/file.pdf");
```

---

## Validation Constraints

### Month (Monthly KRA)
- **Range**: 1-12
- **Type**: Integer
- **Required**: Yes
- **Future Check**: Cannot submit for future months

### Quarter (Quarterly KRA)
- **Range**: 1-4 (Q1, Q2, Q3, Q4)
- **Type**: Integer
- **Required**: Yes
- **Future Check**: Cannot submit for future quarters

### Year (Both)
- **Range**: 2024-2099
- **Type**: Integer
- **Required**: Yes

### Revenue Report URL
- **Type**: String (URL)
- **Required**: No
- **Format**: Must be valid URL
- **Recommended**: S3 pre-signed URL

### Notes
- **Type**: String
- **Required**: No
- **Max Length**: ~5000 characters

---

## Environment Setup

### Required Variables
```env
# Database
DATABASE_URL=postgresql+asyncpg://...

# JWT
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256

# AWS S3
AWS_S3_BUCKET_NAME=scitech-kra-reports
AWS_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
S3_FILE_UPLOAD_PREFIX=kra-submissions
```

---

## Documentation Links

- [Full API Documentation](./KRA_MONTHLY_QUARTERLY_API.md)
- [S3 Integration Guide](./S3_INTEGRATION_GUIDE.md)
- [Implementation Summary](../IMPLEMENTATION_SUMMARY_KRA_MONTHLY_QUARTERLY.md)
- [Test Cases](../tests/test_monthly_quarterly_kra.py)

---

## Support

For issues or questions:
1. Check [Full API Documentation](./KRA_MONTHLY_QUARTERLY_API.md)
2. Review [S3 Integration Guide](./S3_INTEGRATION_GUIDE.md)
3. Check test cases in `tests/test_monthly_quarterly_kra.py`
4. Review error messages and HTTP status codes
