"""Comprehensive validation matrix and error handling tests.

Conforms to docs/TESTING.md §6 and docs/API_SPEC.md §3, §4.1.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def api_client():
    return APIClient()


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Validation Matrix Tests (TESTING.md §6)
# ---------------------------------------------------------------------------

VALIDATION_CASES = [
    # 1. Missing start
    (
        {"finish": {"lat": 41.8756, "lon": -87.6244}},
        "start",
    ),
    # 2. Start has both query and lat/lon
    (
        {
            "start": {"query": "New York, NY", "lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start",
    ),
    # 3. Query too short (2 chars)
    (
        {
            "start": {"query": "NY"},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.query",
    ),
    # 4. Query too long (201 chars)
    (
        {
            "start": {"query": "A" * 201},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.query",
    ),
    # 5. Query contains null byte
    (
        {
            "start": {"query": "New York\x00, NY"},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.query",
    ),
    # 6. Latitude below contiguous US bounds (< 24.0)
    (
        {
            "start": {"lat": 23.9, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.lat",
    ),
    # 7. Latitude above contiguous US bounds (> 49.5)
    (
        {
            "start": {"lat": 49.6, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.lat",
    ),
    # 8. Longitude below contiguous US bounds (< -125.0)
    (
        {
            "start": {"lat": 40.7127, "lon": -125.1},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.lon",
    ),
    # 9. Longitude above contiguous US bounds (> -66.5)
    (
        {
            "start": {"lat": 40.7127, "lon": -66.4},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        },
        "start.lon",
    ),
    # 10. Start fuel negative (< 0)
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"start_fuel_gal": -1.0},
        },
        "options.start_fuel_gal",
    ),
    # 11. Start fuel exceeds tank capacity (> 50.0)
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"start_fuel_gal": 50.1},
        },
        "options.start_fuel_gal",
    ),
    # 12. Start fuel invalid type
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"start_fuel_gal": "invalid_number"},
        },
        "options.start_fuel_gal",
    ),
    # 13. Departure time naive (no timezone)
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"departure_time": "2026-11-06T12:00:00"},
        },
        "options.departure_time",
    ),
    # 14. Departure time too far in future (> 14 days)
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"departure_time": (datetime.now(UTC) + timedelta(days=15)).isoformat()},
        },
        "options.departure_time",
    ),
    # 15. Departure time too far in past (< now - 1 hour)
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"departure_time": (datetime.now(UTC) - timedelta(hours=2)).isoformat()},
        },
        "options.departure_time",
    ),
    # 16. Unknown root key
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "extra_field": "disallowed",
        },
        "extra_field",
    ),
    # 17. Unknown options key
    (
        {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
            "options": {"disallowed_option": True},
        },
        "options.disallowed_option",
    ),
]


@pytest.mark.parametrize("payload,expected_field_key", VALIDATION_CASES)
def test_validation_matrix_cases(api_client, payload, expected_field_key):
    """Each row of the validation matrix must return 400 VALIDATION_ERROR with expected field."""
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "fields" in data["error"]["details"]
    assert expected_field_key in data["error"]["details"]["fields"]


# ---------------------------------------------------------------------------
# HTTP Protocol and Method Error Tests
# ---------------------------------------------------------------------------


def test_invalid_json_payload_returns_400(api_client):
    """Malformed JSON string returns 400 VALIDATION_ERROR."""
    response = api_client.post(
        "/api/v1/routes/plan",
        data="{'bad': json",
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_wrong_content_type_returns_415(api_client):
    """Unsupported Media Type returns 415."""
    response = api_client.post(
        "/api/v1/routes/plan",
        data="<xml></xml>",
        content_type="application/xml",
    )
    assert response.status_code == 415


def test_get_method_not_allowed_returns_405(api_client):
    """GET /api/v1/routes/plan returns 405 METHOD_NOT_ALLOWED."""
    response = api_client.get("/api/v1/routes/plan")
    assert response.status_code == 405
    data = response.json()
    assert data["error"]["code"] == "METHOD_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# Business Rule 422 Tests
# ---------------------------------------------------------------------------


def test_location_not_found_422(api_client, respx_mock):
    """When geocoding returns empty list -> 422 LOCATION_NOT_FOUND."""
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Zzzzville Nowhere", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(200, json=[])

    payload = {
        "start": {"query": "Zzzzville Nowhere"},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "LOCATION_NOT_FOUND"
    assert data["error"]["details"]["which"] == "start"


def test_location_outside_us_422(api_client, respx_mock):
    """Location resolving outside contiguous US -> 422 LOCATION_OUTSIDE_US."""
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Honolulu, HI", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(
        200,
        json=[{"lat": "21.3069", "lon": "-157.8583", "display_name": "Honolulu, Hawaii"}],
    )

    payload = {
        "start": {"query": "Honolulu, HI"},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "LOCATION_OUTSIDE_US"
    assert data["error"]["details"]["which"] == "start"


def test_route_not_found_422(api_client, respx_mock):
    """OSRM returning NoRoute -> 422 ROUTE_NOT_FOUND."""
    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json={"code": "NoRoute", "routes": []}
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "ROUTE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Internal Error and Security Hardening Tests
# ---------------------------------------------------------------------------


def test_optimizer_validator_failure_returns_internal_error(api_client, respx_mock):
    """If independent validator fails, return 500 INTERNAL_ERROR with no stack trace or plan."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }

    # Monkeypatch validate_plan to fail
    with patch(
        "apps.planner.services.validate_plan",
        return_value=(False, "Mocked fuel reachability deficit of 0.05 gal"),
    ):
        response = api_client.post("/api/v1/routes/plan", data=payload, format="json")

    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
    # Never expose internal details or plan to client
    assert "routes" not in data
    assert "Traceback" not in json.dumps(data)
