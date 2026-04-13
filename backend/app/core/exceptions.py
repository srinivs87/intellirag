"""
Centralised exception handling for the FastAPI application.
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class IntelliRAGException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def intellirag_exception_handler(request: Request, exc: IntelliRAGException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
