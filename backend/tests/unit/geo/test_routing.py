"""Unit tests for OSRMRoutingProvider and RoutingService.

Conforms to docs/TESTING.md §4.
"""

import json
from pathlib import Path

import httpx
import pytest

from apps.common.errors import ApiError, ApiErrorCode
from apps.geo.routing import OSRMRoutingProvider, RoutingService


@pytest.fixture
def nyc_chicago_fixture() -> dict:
    fixture_path = (
        Path(__file__).resolve().parent.parent.parent / "fixtures" / "osrm_nyc_chicago.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.django_db
def test_routing_service_cache_and_fewer_alternatives(respx_mock, nyc_chicago_fixture):
    # NYC to Chicago coordinates
    lat1, lon1 = 40.71278, -74.00600
    lat2, lon2 = 41.87560, -87.62440

    route_route = respx_mock.get(
        "https://router.project-osrm.org/route/v1/driving/-74.00600,40.71278;-87.62440,41.87560"
    ).respond(200, json=nyc_chicago_fixture)

    service = RoutingService()

    # 1. First call fetches from OSRM
    routes = service.get_routes(lat1, lon1, lat2, lon2, alternatives=True)
    assert route_route.called
    assert respx_mock.calls.call_count == 1

    # Handled fewer routes than 3 requested (fixture has 2)
    assert len(routes) == 2
    r0 = routes[0]
    assert r0.route_index == 0
    assert r0.distance_miles > 750.0
    assert len(r0.coords) > 100
    assert r0.cum_miles[-1] == pytest.approx(r0.distance_miles, abs=0.1)

    # 2. Second call hits RouteCache (0 HTTP calls)
    cached_routes = service.get_routes(lat1, lon1, lat2, lon2, alternatives=True)
    assert respx_mock.calls.call_count == 1  # No new call
    assert len(cached_routes) == 2
    assert cached_routes[0].distance_miles == r0.distance_miles


def test_route_too_short_raises_without_http_call(respx_mock):
    # Coordinates 0.1 miles apart
    lat1, lon1 = 40.7128, -74.0060
    lat2, lon2 = 40.7130, -74.0060

    service = RoutingService()
    with pytest.raises(ApiError) as exc_info:
        service.get_routes(lat1, lon1, lat2, lon2)

    assert exc_info.value.code == ApiErrorCode.ROUTE_TOO_SHORT
    assert exc_info.value.status_code == 422
    assert respx_mock.calls.call_count == 0


@pytest.mark.django_db
def test_osrm_error_mappings(respx_mock):
    lat1, lon1 = 40.7128, -74.0060
    lat2, lon2 = 41.8781, -87.6298

    provider = OSRMRoutingProvider(base_url="https://osrm.test")
    service = RoutingService(provider=provider)

    # 1. NoRoute
    respx_mock.get(
        "https://osrm.test/route/v1/driving/-74.00600,40.71280;-87.62980,41.87810"
    ).respond(200, json={"code": "NoRoute", "routes": []})
    with pytest.raises(ApiError) as exc_info:
        service.get_routes(lat1, lon1, lat2, lon2)
    assert exc_info.value.code == ApiErrorCode.ROUTE_NOT_FOUND
    assert exc_info.value.status_code == 422

    # 2. Timeout
    respx_mock.get("https://osrm.test/route/v1/driving/-74.00600,40.71280;-87.62980,41.87810").mock(
        side_effect=httpx.ReadTimeout("Timeout")
    )
    with pytest.raises(ApiError) as exc_info2:
        service.get_routes(lat1, lon1, lat2, lon2)
    assert exc_info2.value.code == ApiErrorCode.UPSTREAM_TIMEOUT
    assert exc_info2.value.status_code == 504

    # 3. 503 / 429
    respx_mock.get(
        "https://osrm.test/route/v1/driving/-74.00600,40.71280;-87.62980,41.87810"
    ).respond(503)
    with pytest.raises(ApiError) as exc_info3:
        service.get_routes(lat1, lon1, lat2, lon2)
    assert exc_info3.value.code == ApiErrorCode.UPSTREAM_UNAVAILABLE
    assert exc_info3.value.status_code == 503
