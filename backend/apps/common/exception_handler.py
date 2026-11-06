"""Custom DRF exception handler conforming to API_SPEC.md §3."""

import logging
import uuid
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response

from .errors import ApiError, ApiErrorCode

logger = logging.getLogger(__name__)


def _format_validation_details(detail: Any, prefix: str = "") -> dict[str, list[str]]:
    """Flatten DRF ValidationError detail dictionary/list into {field_path: [msgs]}."""
    fields: dict[str, list[str]] = {}

    if isinstance(detail, dict):
        for key, val in detail.items():
            if key == "non_field_errors" and prefix:
                field_name = prefix
            else:
                field_name = f"{prefix}.{key}" if prefix else str(key)
            nested = _format_validation_details(val, prefix=field_name)
            fields.update(nested)
    elif isinstance(detail, (list, tuple)):
        # Check if list contains nested dicts/objects or simple string errors
        simple_msgs: list[str] = []
        for idx, item in enumerate(detail):
            if isinstance(item, (dict, list)):
                item_prefix = f"{prefix}[{idx}]" if prefix else str(idx)
                nested = _format_validation_details(item, prefix=item_prefix)
                fields.update(nested)
            else:
                simple_msgs.append(str(item))
        if simple_msgs:
            target_key = prefix or "non_field_errors"
            fields.setdefault(target_key, []).extend(simple_msgs)
    else:
        target_key = prefix or "non_field_errors"
        fields.setdefault(target_key, []).append(str(detail))

    return fields


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """Handle all exceptions, returning standard API_SPEC §3 error JSON response."""
    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    if not request_id and request:
        request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())

    code = ApiErrorCode.INTERNAL_ERROR
    status_code = 500
    message = "An internal server error occurred."
    details: dict[str, Any] = {}

    if isinstance(exc, ApiError):
        code = exc.code
        status_code = exc.status_code
        message = exc.message
        details = exc.details
    elif isinstance(exc, exceptions.ValidationError):
        code = ApiErrorCode.VALIDATION_ERROR
        status_code = 400
        message = "Validation failed."
        details = {"fields": _format_validation_details(exc.detail)}
    elif isinstance(exc, (exceptions.NotFound, Http404)):
        code = ApiErrorCode.NOT_FOUND
        status_code = 404
        message = "Resource not found."
    elif isinstance(exc, exceptions.MethodNotAllowed):
        code = ApiErrorCode.METHOD_NOT_ALLOWED
        status_code = 405
        message = str(exc)
    elif isinstance(exc, exceptions.Throttled):
        code = ApiErrorCode.RATE_LIMITED
        status_code = 429
        if exc.wait:
            message = f"Request was throttled. Expected available in {exc.wait} seconds."
        else:
            message = "Request was throttled."
    elif isinstance(exc, exceptions.ParseError):
        code = ApiErrorCode.VALIDATION_ERROR
        status_code = 400
        message = "Malformed request payload."
    elif isinstance(exc, (exceptions.PermissionDenied, PermissionDenied)):
        code = "PERMISSION_DENIED"
        status_code = 403
        message = "Permission denied."
    elif isinstance(exc, exceptions.NotAuthenticated):
        code = "NOT_AUTHENTICATED"
        status_code = 401
        message = "Authentication required."
    elif isinstance(exc, exceptions.APIException):
        status_code = exc.status_code
        message = str(exc.detail) if hasattr(exc, "detail") else str(exc)
    else:
        # Unhandled exception: log structured error with request_id
        logger.exception("Unhandled server error", extra={"request_id": request_id})

    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }
    response = Response(payload, status=status_code)
    response["X-Request-ID"] = request_id
    return response


def handle_404(request: Any, exception: Any = None) -> JsonResponse:
    """Standard Django handler for 404 errors on unknown endpoints."""
    req_id = getattr(request, "request_id", None) or request.headers.get("X-Request-ID")
    request_id = req_id or str(uuid.uuid4())
    payload = {
        "error": {
            "code": ApiErrorCode.NOT_FOUND,
            "message": "Resource not found.",
            "details": {},
            "request_id": request_id,
        }
    }
    response = JsonResponse(payload, status=404)
    response["X-Request-ID"] = request_id
    return response


def handle_500(request: Any) -> JsonResponse:
    """Standard Django handler for 500 errors."""
    req_id = getattr(request, "request_id", None) or request.headers.get("X-Request-ID")
    request_id = req_id or str(uuid.uuid4())
    payload = {
        "error": {
            "code": ApiErrorCode.INTERNAL_ERROR,
            "message": "An internal server error occurred.",
            "details": {},
            "request_id": request_id,
        }
    }
    response = JsonResponse(payload, status=500)
    response["X-Request-ID"] = request_id
    return response
