"""Test health endpoints and 404 error envelope."""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_liveness_endpoint(django_assert_num_queries):
    client = APIClient()
    with django_assert_num_queries(0):
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


@pytest.mark.django_db
def test_unknown_path_returns_api_error_envelope():
    client = APIClient()
    response = client.get("/api/v1/unknown-endpoint-404")

    assert response.status_code == 404
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "request_id" in data["error"]
    assert data["error"]["request_id"] == response.headers["X-Request-ID"]
