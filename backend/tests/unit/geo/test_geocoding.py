"""Unit tests for GeocodingService and NominatimProvider.

Conforms to docs/TESTING.md §4.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from apps.common.errors import ApiError, ApiErrorCode
from apps.geo.geocoding import (
    GeocodingService,
    NominatimProvider,
    normalize_display_name,
    normalize_query,
)


def test_normalization():
    assert normalize_query("  New York,  NY!  ") == "new york ny"
    assert normalize_query("St. Louis, MO-USA.") == "st louis mo usa"
    assert normalize_query("  San Francisco   ") == "san francisco"


def test_display_name_restores_missing_county_space():
    assert (
        normalize_display_name(
            "Chicago, South Chicago Township, CookCounty, Illinois, United States"
        )
        == "Chicago, South Chicago Township, Cook County, Illinois, United States"
    )
    assert normalize_display_name("Chicago, Cook County, Illinois") == (
        "Chicago, Cook County, Illinois"
    )


@pytest.mark.django_db
def test_positive_and_negative_cache_ttl(respx_mock):
    base_time = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)
    current_time = base_time

    def mock_clock():
        return current_time

    provider = NominatimProvider(base_url="https://nominatim.test", clock=mock_clock)
    service = GeocodingService(provider=provider, clock=mock_clock)

    # 1. Positive lookup
    respx_mock.get("https://nominatim.test/search").respond(
        200,
        json=[{"lat": "40.7128", "lon": "-74.0060", "display_name": "New York, NY, USA"}],
    )

    loc = service.geocode("New York, NY")
    assert loc.lat == 40.7128
    assert loc.lon == -74.0060
    assert respx_mock.calls.call_count == 1

    # Immediate second call -> cache hit (no HTTP call)
    loc2 = service.geocode("  new york, ny! ")
    assert loc2.lat == 40.7128
    assert respx_mock.calls.call_count == 1

    # Advance clock by 29 days -> still valid (TTL 30 days)
    current_time = base_time + timedelta(days=29)
    loc3 = service.geocode("New York, NY")
    assert loc3.lat == 40.7128
    assert respx_mock.calls.call_count == 1

    # Advance clock past 30 days -> cache expired, refetched
    current_time = base_time + timedelta(days=31)
    loc4 = service.geocode("New York, NY")
    assert loc4.lat == 40.7128
    assert respx_mock.calls.call_count == 2

    # 2. Negative lookup (not found)
    respx_mock.get("https://nominatim.test/search").respond(200, json=[])
    with pytest.raises(ApiError) as exc_info:
        service.geocode("Nonexistent Place")
    assert exc_info.value.code == ApiErrorCode.LOCATION_NOT_FOUND
    assert respx_mock.calls.call_count == 3

    # Re-querying nonexistent place hits negative cache
    with pytest.raises(ApiError) as exc_info2:
        service.geocode("Nonexistent Place")
    assert exc_info2.value.code == ApiErrorCode.LOCATION_NOT_FOUND
    assert respx_mock.calls.call_count == 3  # No HTTP call


@pytest.mark.django_db
def test_location_outside_us_bounding_box(respx_mock):
    respx_mock.get("https://nominatim.openstreetmap.org/search").respond(
        200,
        json=[{"lat": "19.4326", "lon": "-99.1332", "display_name": "Mexico City, Mexico"}],
    )
    service = GeocodingService()
    with pytest.raises(ApiError) as exc_info:
        service.geocode("Mexico City, Mexico")

    assert exc_info.value.code == ApiErrorCode.LOCATION_OUTSIDE_US
    assert exc_info.value.status_code == 422


@pytest.mark.django_db
def test_user_agent_header_and_error_mappings(respx_mock):
    provider = NominatimProvider(
        base_url="https://nominatim.test",
        app_contact="https://github.com/example/fuelroute",
    )
    service = GeocodingService(provider=provider)

    # 1. 429/503 -> UPSTREAM_UNAVAILABLE
    respx_mock.get("https://nominatim.test/search").respond(429)
    with pytest.raises(ApiError) as exc_info:
        service.geocode("Chicago, IL")
    assert exc_info.value.code == ApiErrorCode.UPSTREAM_UNAVAILABLE
    assert exc_info.value.status_code == 503

    # Check User-Agent header was present
    last_req = respx_mock.calls.last.request
    assert "FuelRoute/1.0 (+https://github.com/example/fuelroute)" in last_req.headers["User-Agent"]

    # 2. Timeout -> UPSTREAM_TIMEOUT
    respx_mock.get("https://nominatim.test/search").mock(side_effect=httpx.ReadTimeout("Timeout"))
    with pytest.raises(ApiError) as exc_info:
        service.geocode("Dallas, TX")
    assert exc_info.value.code == ApiErrorCode.UPSTREAM_TIMEOUT
    assert exc_info.value.status_code == 504

    # 3. Bad JSON -> UPSTREAM_BAD_RESPONSE
    respx_mock.get("https://nominatim.test/search").respond(200, text="NOT_JSON")
    with pytest.raises(ApiError) as exc_info:
        service.geocode("Denver, CO")
    assert exc_info.value.code == ApiErrorCode.UPSTREAM_BAD_RESPONSE
    assert exc_info.value.status_code == 502
