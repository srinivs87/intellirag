"""
Request/response logging middleware.
Logs method, path, status code, and duration for every request.
"""
import time
import logging
from fastapi import Request

logger = logging.getLogger("intellirag")


async def logging_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        "%s %s %s %dms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response
