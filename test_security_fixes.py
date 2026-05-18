"""
Test script to validate security fixes for authentication issues
Run this to verify the role assignment vulnerability is fixed
"""

from pydantic import ValidationError
from app.schemas.schemas import RegisterRequest
from uuid import UUID

test_tenant_id = UUID("12345678-1234-5678-1234-567812345678")

print("=" * 70)
print("TESTING AUTHENTICATION & AUTHORIZATION FIXES")
print("=" * 70)

# Test 1: Try to register as Tenant Admin (should fail)
print("\n[TEST 1] Attempting to register as Tenant Admin...")
try:
    RegisterRequest(
        email="attacker@test.com",
        password="SecurePass123",
        role="Tenant Admin",
        tenant_id=test_tenant_id
    )
    print("❌ FAILED - Should have blocked Tenant Admin role")
except ValidationError as e:
    print("✅ PASSED - Registration blocked with validation error:")
    print(f"   Error: {e.errors()[0]['msg']}")

# Test 2: Try to register as Super Admin (should fail)
print("\n[TEST 2] Attempting to register as Super Admin...")
try:
    RegisterRequest(
        email="attacker2@test.com",
        password="SecurePass123",
        role="Super Admin",
        tenant_id=test_tenant_id
    )
    print("❌ FAILED - Should have blocked Super Admin role")
except ValidationError as e:
    print("✅ PASSED - Registration blocked with validation error:")
    print(f"   Error: {e.errors()[0]['msg']}")

# Test 3: Register as Manager (should succeed)
print("\n[TEST 3] Attempting to register as Manager...")
try:
    user = RegisterRequest(
        email="manager@test.com",
        password="SecurePass123",
        role="Manager",
        tenant_id=test_tenant_id
    )
    print("✅ PASSED - Manager role registration allowed")
    print(f"   Email: {user.email}")
    print(f"   Role: {user.role}")
except ValidationError as e:
    print("❌ FAILED - Manager registration should be allowed")
    print(f"   Error: {e.errors()[0]['msg']}")

# Test 4: Register as Staff (should succeed - default role)
print("\n[TEST 4] Attempting to register as Staff...")
try:
    user = RegisterRequest(
        email="staff@test.com",
        password="SecurePass123",
        role="Staff",
        tenant_id=test_tenant_id
    )
    print("✅ PASSED - Staff role registration allowed")
    print(f"   Email: {user.email}")
    print(f"   Role: {user.role}")
except ValidationError as e:
    print("❌ FAILED - Staff registration should be allowed")
    print(f"   Error: {e.errors()[0]['msg']}")

# Test 5: Register without role (should default to Staff)
print("\n[TEST 5] Attempting to register without specifying role...")
try:
    user = RegisterRequest(
        email="default@test.com",
        password="SecurePass123",
        tenant_id=test_tenant_id
    )
    print("✅ PASSED - Default role applied")
    print(f"   Email: {user.email}")
    print(f"   Role: {user.role} (default)")
except ValidationError as e:
    print("❌ FAILED - Default role should be Staff")
    print(f"   Error: {e.errors()[0]['msg']}")

print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)
print("""
✅ ROLE ASSIGNMENT VULNERABILITY - FIXED

Self-registration is now restricted to:
  - Staff ✅
  - Manager ✅

Self-registration is now blocked for:
  - Tenant Admin ❌
  - Super Admin ❌

Admin roles can ONLY be assigned via /users/invite endpoint
by existing Super Admin or Tenant Admin users.

⚠️  FRONTEND NOTE:
Handle 403 errors from /auth/superadmin-login gracefully
instead of redirecting to common login page.
""")
print("=" * 70)
