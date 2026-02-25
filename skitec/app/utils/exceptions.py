"""
Utilities - Custom Exceptions

Application-specific exception classes for error handling and HTTP responses.
"""


class SkitecException(Exception):
    """Base exception for Skitec application"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
    ):
        """
        Initialize exception

        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Machine-readable error code
        """
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class InvalidCredentialsError(SkitecException):
    """Raised when authentication credentials are invalid"""

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, status_code=401, error_code="INVALID_CREDENTIALS")


class UnauthorizedError(SkitecException):
    """Raised when user is not authorized for action"""

    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message, status_code=401, error_code="UNAUTHORIZED")


class ForbiddenError(SkitecException):
    """Raised when user lacks required permissions"""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status_code=403, error_code="FORBIDDEN")


class NotFoundError(SkitecException):
    """Raised when resource is not found"""

    def __init__(self, resource: str = "Resource"):
        super().__init__(
            f"{resource} not found",
            status_code=404,
            error_code="NOT_FOUND",
        )


class ConflictError(SkitecException):
    """Raised when resource already exists"""

    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409, error_code="CONFLICT")


class ValidationError(SkitecException):
    """Raised when input validation fails"""

    def __init__(self, message: str = "Invalid input"):
        super().__init__(message, status_code=422, error_code="VALIDATION_ERROR")


class DatabaseError(SkitecException):
    """Raised for database operation failures"""

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, status_code=500, error_code="DATABASE_ERROR")
