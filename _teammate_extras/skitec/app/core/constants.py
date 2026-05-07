"""
Application Constants

Centralized constants for HTTP status codes, error messages, and application-wide values.
"""

# HTTP Status Codes
HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_204_NO_CONTENT = 204
HTTP_400_BAD_REQUEST = 400
HTTP_401_UNAUTHORIZED = 401
HTTP_403_FORBIDDEN = 403
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409
HTTP_422_UNPROCESSABLE_ENTITY = 422
HTTP_500_INTERNAL_SERVER_ERROR = 500

# Error Messages
ERROR_INVALID_CREDENTIALS = "Invalid credentials"
ERROR_INACTIVE_USER = "User account is inactive"
ERROR_NOT_FOUND = "Resource not found"
ERROR_UNAUTHORIZED = "Unauthorized access"
ERROR_FORBIDDEN = "Insufficient permissions"
ERROR_DATABASE = "Database operation failed"
ERROR_INVALID_INPUT = "Invalid input"

# Success Messages
SUCCESS_CREATED = "Resource created successfully"
SUCCESS_UPDATED = "Resource updated successfully"
SUCCESS_DELETED = "Resource deleted successfully"
SUCCESS_LOGIN = "Login successful"

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_PAGE = 1

# Time Limits
TOKEN_EXPIRE_SKEW_SECONDS = 60

# Audit Log Actions
AUDIT_ACTION_CREATE = "CREATE"
AUDIT_ACTION_READ = "READ"
AUDIT_ACTION_UPDATE = "UPDATE"
AUDIT_ACTION_DELETE = "DELETE"
AUDIT_ACTION_LOGIN = "LOGIN"
AUDIT_ACTION_LOGOUT = "LOGOUT"
AUDIT_ACTION_PERMISSION_CHANGE = "PERMISSION_CHANGE"
