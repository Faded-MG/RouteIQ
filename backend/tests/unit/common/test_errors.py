"""Test custom exception handler and ApiError envelope."""

import uuid

from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from apps.common.errors import ApiError, ApiErrorCode
from apps.common.exception_handler import custom_exception_handler


def test_api_error_envelope():
    factory = APIRequestFactory()
    req_id = str(uuid.uuid4())
    request = factory.get("/api/v1/routes/plan", HTTP_X_REQUEST_ID=req_id)
    request.request_id = req_id

    # 1. Custom ApiError
    exc = ApiError(
        code=ApiErrorCode.NO_FEASIBLE_FUEL_PLAN,
        message="No refueling plan keeps the vehicle within range.",
        details={"largest_gap": {"gap_miles": 550.0}},
    )
    context = {"request": request}
    response = custom_exception_handler(exc, context)

    assert response.status_code == 422
    assert response["X-Request-ID"] == req_id
    assert response.data == {
        "error": {
            "code": "NO_FEASIBLE_FUEL_PLAN",
            "message": "No refueling plan keeps the vehicle within range.",
            "details": {"largest_gap": {"gap_miles": 550.0}},
            "request_id": req_id,
        }
    }


def test_drf_validation_error_envelope():
    factory = APIRequestFactory()
    req_id = str(uuid.uuid4())
    request = factory.get("/api/v1/routes/plan", HTTP_X_REQUEST_ID=req_id)
    request.request_id = req_id

    exc = exceptions.ValidationError({"start": {"lat": ["Must be between 24.0 and 49.5."]}})
    context = {"request": request}
    response = custom_exception_handler(exc, context)

    assert response.status_code == 400
    assert response["X-Request-ID"] == req_id
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert response.data["error"]["message"] == "Validation failed."
    assert response.data["error"]["request_id"] == req_id
    field_errors = response.data["error"]["details"]["fields"]
    assert "start.lat" in field_errors
    assert field_errors["start.lat"] == ["Must be between 24.0 and 49.5."]


def test_exception_handler_throttled_and_not_found():
    factory = APIRequestFactory()
    request = factory.get("/api/v1/routes/plan")
    context = {"request": request}

    # Throttled
    throttled_exc = exceptions.Throttled(wait=15)
    resp = custom_exception_handler(throttled_exc, context)
    assert resp.status_code == 429
    assert resp.data["error"]["code"] == "RATE_LIMITED"
    assert "15 seconds" in resp.data["error"]["message"]

    # Not Found
    nf_exc = exceptions.NotFound()
    resp_nf = custom_exception_handler(nf_exc, context)
    assert resp_nf.status_code == 404
    assert resp_nf.data["error"]["code"] == "NOT_FOUND"


def test_exception_handler_unhandled_internal_error():
    factory = APIRequestFactory()
    request = factory.get("/api/v1/routes/plan")
    context = {"request": request}

    unhandled = RuntimeError("Unexpected boom")
    resp = custom_exception_handler(unhandled, context)
    assert resp.status_code == 500
    assert resp.data["error"]["code"] == "INTERNAL_ERROR"
    assert resp.data["error"]["message"] == "An internal server error occurred."


def test_handle_500_view():
    from apps.common.exception_handler import handle_500

    factory = APIRequestFactory()
    request = factory.get("/any")
    resp = handle_500(request)
    assert resp.status_code == 500
    assert "error" in resp.content.decode()
