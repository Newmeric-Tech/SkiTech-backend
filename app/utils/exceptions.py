"""Custom exceptions - app/utils/exceptions.py"""


class SkiTechException(Exception):
    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class InvalidCredentialsError(SkiTechException):
    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, 401, "INVALID_CREDENTIALS")


class UnauthorizedError(SkiTechException):
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message, 401, "UNAUTHORIZED")


class ForbiddenError(SkiTechException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, 403, "FORBIDDEN")


class NotFoundError(SkiTechException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", 404, "NOT_FOUND")


class ConflictError(SkiTechException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, 409, "CONFLICT")


class ValidationError(SkiTechException):
    def __init__(self, message: str = "Invalid input"):
        super().__init__(message, 422, "VALIDATION_ERROR")


class DatabaseError(SkiTechException):
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, 500, "DATABASE_ERROR")


# Aliases used by attendance module
NotFoundException = NotFoundError
ValidationException = ValidationError
