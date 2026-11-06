"""Domain and API error classes.

Conforms to docs/API_SPEC.md §3.
"""

from collections.abc import Mapping
from typing import Any


class ApiErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    LOCATION_NOT_FOUND = "LOCATION_NOT_FOUND"
    LOCATION_OUTSIDE_US = "LOCATION_OUTSIDE_US"
    ROUTE_TOO_SHORT = "ROUTE_TOO_SHORT"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    NO_FEASIBLE_FUEL_PLAN = "NO_FEASIBLE_FUEL_PLAN"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_BAD_RESPONSE = "UPSTREAM_BAD_RESPONSE"
    FUEL_DATA_NOT_LOADED = "FUEL_DATA_NOT_LOADED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"


DEFAULT_STATUS_CODES: Mapping[str, int] = {
    ApiErrorCode.VALIDATION_ERROR: 400,
    ApiErrorCode.LOCATION_NOT_FOUND: 422,
    ApiErrorCode.LOCATION_OUTSIDE_US: 422,
    ApiErrorCode.ROUTE_TOO_SHORT: 422,
    ApiErrorCode.ROUTE_NOT_FOUND: 422,
    ApiErrorCode.NO_FEASIBLE_FUEL_PLAN: 422,
    ApiErrorCode.RATE_LIMITED: 429,
    ApiErrorCode.UPSTREAM_UNAVAILABLE: 503,
    ApiErrorCode.UPSTREAM_TIMEOUT: 504,
    ApiErrorCode.UPSTREAM_BAD_RESPONSE: 502,
    ApiErrorCode.FUEL_DATA_NOT_LOADED: 503,
    ApiErrorCode.INTERNAL_ERROR: 500,
    ApiErrorCode.NOT_FOUND: 404,
    ApiErrorCode.METHOD_NOT_ALLOWED: 405,
}


class ApiError(Exception):
    """Application-level exception conforming to API_SPEC error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code or DEFAULT_STATUS_CODES.get(code, 500)
        self.details = details if details is not None else {}
