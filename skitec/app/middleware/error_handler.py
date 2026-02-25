"""
Error Handler Middleware

Centralized error handling and formatting.
"""

import logging
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.utils.exceptions import SkitecException

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for centralized error handling"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Handle errors and format error responses

        Args:
            request: FastAPI Request object
            call_next: Callable to process the request

        Returns:
            Response or error response
        """
        try:
            response = await call_next(request)
            return response
        except SkitecException as exc:
            logger.warning(f"Application error: {exc.message}")
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": exc.error_code,
                    "detail": exc.message,
                    "status_code": exc.status_code,
                },
            )
        except Exception as exc:
            logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_SERVER_ERROR",
                    "detail": "An unexpected error occurred",
                    "status_code": 500,
                },
            )
