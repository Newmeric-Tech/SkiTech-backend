# Security Fixes - Authentication & Authorization Issues

## Issues Identified

### Issue 1: User Can Self-Assign Admin Roles During Registration ✅ FIXED
**Problem:** During registration (`POST /auth/register`), users could specify ANY role including "Tenant Admin" and "Super Admin", bypassing role-based access controls.

**Impact:** 
- A Manager could register as Tenant Admin and access the Tenant Admin dashboard
- Any user could self-promote to higher privilege levels

**Root Cause:** 
- No validation on the `role` parameter in `RegisterRequest` schema
- Registration endpoint accepted any role value passed by the frontend

**Solution Applied:**
1. Added `@field_validator` on `RegisterRequest.role` to only allow "Staff" or "Manager" roles
2. Admin roles (Tenant Admin, Super Admin) can ONLY be assigned via admin invite endpoint
3. Error message guides users to contact administrators for higher-level role assignment

**Files Modified:**
- `app/schemas/schemas.py` - Added role validation in RegisterRequest
- `app/api/v1/endpoints/auth.py` - Removed redundant role check (now handled at schema level)

**New Behavior:**
```
Self-registration allowed roles: ["Staff", "Manager"]
Self-registration blocked roles: ["Tenant Admin", "Super Admin"]
Result for invalid role: Pydantic validation error with message
```

---

### Issue 2: SuperAdmin Login Redirects to Common Login ❌ NOT A BACKEND ISSUE
**Problem:** When logging in via `/auth/superadmin-login`, non-Super Admin users are being redirected to common login page instead of seeing error.

**Root Cause:** 
- **FRONTEND ISSUE** - The backend endpoint is correctly implemented
- Backend returns 403 error with message "Access denied. This portal is restricted to Super Admins only."
- Frontend is catching the 403 error and redirecting instead of displaying error message

**Backend Implementation:** ✅ Correct
The `/superadmin-login` endpoint properly:
- Validates credentials
- Checks user is verified
- **Verifies role is exactly "Super Admin"** and returns 403 if not
- Returns JWT token only for Super Admin users

**Frontend Fix Required:**
Frontend should:
1. NOT redirect on 403 error from `/superadmin-login` endpoint
2. Display error message: "Access denied. This portal is restricted to Super Admins only."
3. Allow user retry with different credentials or redirect to regular login

---

## Associated Security Features (Already Implemented ✅)

### Dashboard Role-Based Access Control
All dashboard endpoints have proper role restrictions:

| Endpoint | Allowed Roles | Status |
|----------|---------------|--------|
| `GET /stats/owner` | Super Admin, Tenant Admin | ✅ Protected |
| `GET /stats/manager/{id}` | Super Admin, Tenant Admin, Manager | ✅ Protected |
| `GET /stats/staff/me` | All authenticated users | ✅ Protected |

Even if a Manager obtains a Tenant Admin token (which they can't now), they would still be blocked at the endpoint level.

### Admin-Only Operations
- `PUT /users/{user_id}/role` - Only Tenant Admin, Super Admin
- `POST /users/invite` - Only Tenant Admin, Super Admin
- User deactivation and activation - Only Tenant Admin, Super Admin

---

## Testing the Fixes

### Test 1: Register as Manager (Should Succeed)
```bash
POST /auth/register
{
  "email": "manager@test.com",
  "password": "SecurePass123",
  "role": "Manager",
  "tenant_id": "xxxx-xxxx-xxxx-xxxx"
}
Result: ✅ Success
```

### Test 2: Register as Tenant Admin (Should Fail)
```bash
POST /auth/register
{
  "email": "admin@test.com",
  "password": "SecurePass123",
  "role": "Tenant Admin",
  "tenant_id": "xxxx-xxxx-xxxx-xxxx"
}
Result: ❌ 422 Validation Error
Message: "Role 'Tenant Admin' cannot be self-assigned. Contact your administrator."
```

### Test 3: SuperAdmin Login with Non-Admin (Should Fail)
```bash
POST /auth/superadmin-login
{
  "email": "manager@test.com",
  "password": "SecurePass123"
}
Result: ❌ 403 Forbidden
Message: "Access denied. This portal is restricted to Super Admins only."
```

### Test 4: SuperAdmin Login with Valid SuperAdmin (Should Succeed)
```bash
POST /auth/superadmin-login
{
  "email": "superadmin@test.com",
  "password": "SecurePass123"
}
Result: ✅ Success
Response: {access_token, refresh_token}
```

---

## How Admin Users Should Be Created

**Correct Flow for Creating Tenant Admins:**

1. Super Admin uses invite endpoint:
   ```bash
   POST /users/invite
   {
     "email": "newadmin@test.com",
     "first_name": "John",
     "last_name": "Doe",
     "role": "Tenant Admin",
     "property_id": null
   }
   ```

2. System generates temp password and sends OTP

3. New user sets password and verifies email

4. User now has Tenant Admin role and can access Tenant Admin dashboard

---

## Summary

✅ **Issue 1 FIXED**: Role assignment vulnerability during registration plugged
- Users can no longer self-assign admin roles
- Schema validation enforces allowed roles

⚠️ **Issue 2 ACTION REQUIRED**: Frontend needs to handle 403 errors from `/superadmin-login`
- Backend is working correctly
- Frontend should display error message instead of redirecting
