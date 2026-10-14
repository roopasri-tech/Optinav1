"""User-facing errors. The `detail` text of these exceptions is shown to the
traveller as-is, so it must always be a clear, non-technical sentence."""
from fastapi import HTTPException


class SmartRouteError(HTTPException):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)


class NotFound(SmartRouteError):
    def __init__(self, detail: str = "Not found"):
        super().__init__(detail=detail, status_code=404)


class ExternalServiceError(SmartRouteError):
    """A third-party provider (routing, geocoding) failed and there is no honest fallback."""

    def __init__(self, detail: str = "An external map service is temporarily unavailable. Please try again."):
        super().__init__(detail=detail, status_code=503)
