"""Test RequestIdMiddleware behavior."""

import uuid

from django.http import HttpResponse
from django.test import RequestFactory

from apps.common.middleware import RequestIdMiddleware


def test_request_id_middleware_reflects_incoming_header():
    factory = RequestFactory()
    custom_id = str(uuid.uuid4())
    request = factory.get("/api/v1/health/live", HTTP_X_REQUEST_ID=custom_id)

    middleware = RequestIdMiddleware(lambda req: HttpResponse("OK"))
    response = middleware(request)

    assert request.request_id == custom_id
    assert response["X-Request-ID"] == custom_id


def test_request_id_middleware_generates_uuid_when_missing():
    factory = RequestFactory()
    request = factory.get("/api/v1/health/live")

    middleware = RequestIdMiddleware(lambda req: HttpResponse("OK"))
    response = middleware(request)

    assert hasattr(request, "request_id")
    generated_id = request.request_id
    # Assert valid UUID4
    parsed = uuid.UUID(generated_id, version=4)
    assert str(parsed) == generated_id
    assert response["X-Request-ID"] == generated_id
