"""
Audit Middleware

Middleware for logging user actions to audit trail.
"""

from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..core.database import SessionLocal
from ..services.audit_service import AuditService


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware to log significant actions to audit trail"""

    # Actions that should be audited
    AUDITABLE_METHODS = ["POST", "PUT", "DELETE", "PATCH"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log auditable requests to audit trail

        Args:
            request: FastAPI Request object
            call_next: Callable to process the request

        Returns:
            Response from the request
        """
        response = await call_next(request)

        # Only audit write operations
        if request.method in self.AUDITABLE_METHODS:
            # Extract audit information from request and response
            # This is a placeholder - extend with actual audit logic
            # You'll need to extract user ID from JWT token, resource info, etc.

            db = SessionLocal()
            try:
                audit_service = AuditService(db)
                # Example audit logging
                # audit_service.log_action(
                #     action="OPERATION",
                #     resource_type="resource",
                #     user_id=user_id,
                #     ip_address=request.client.host,
                #     status="success" if response.status_code < 400 else "failure"
                # )
            finally:
                db.close()

        return response
