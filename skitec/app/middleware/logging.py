"""
Logging Middleware

Middleware for request/response logging and performance metrics.
"""

import time
import logging
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log request details and process request

        Args:
            request: FastAPI Request object
            call_next: Callable to process the request

        Returns:
            Response from the request
        """
        # Log request details
        logger.info(
            f"Incoming Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
            },
        )

        # Measure request processing time
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(f"Request failed: {str(exc)}")
            raise

        process_time = time.time() - start_time

        # Log response details
        logger.info(
            f"Response: {response.status_code} for {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
            },
        )

        # Add process time to response headers
        response.headers["X-Process-Time"] = str(process_time)

        return response
