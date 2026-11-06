"""Unit tests for Open-Meteo weather client and WeatherService.

Conforms to docs/PLAN.md T17:
"Exactly 1 weather call for 3 routes; weather timeout still returns 200 with correct fuel plan".
"""

from datetime import UTC, datetime

import numpy as np

from apps.geo.types import DrivingRoute
from apps.weather.providers.open_meteo import OpenMeteoProvider, WeatherService


def make_dummy_route(index: int, distance: float) -> DrivingRoute:
    coords = np.array([[40.0, -74.0], [41.0, -80.0], [42.0, -87.0]], dtype=np.float64)
    cum = np.array([0.0, distance / 2.0, distance], dtype=np.float64)
    return DrivingRoute(
        route_index=index,
        distance_miles=distance,
        duration_seconds=36000.0,
        geometry_polyline6="dummy",
        coords=coords,
        cum_miles=cum,
    )


def test_weather_service_exactly_one_call_for_multiple_routes(respx_mock):
    """Multiple routes de-duplicate coordinates and query Open-Meteo in exactly 1 call."""
    r1 = make_dummy_route(0, 750.0)
    r2 = make_dummy_route(1, 780.0)
    r3 = make_dummy_route(2, 800.0)

    # Mock Open-Meteo endpoint
    mock_hourly = {
        "time": ["2026-11-06T12:00", "2026-11-06T13:00", "2026-11-06T14:00"],
        "temperature_2m": [60.0, 58.0, 55.0],
        "precipitation": [0.0, 0.0, 0.05],
        "weather_code": [0, 1, 61],
        "wind_speed_10m": [8.0, 10.0, 12.0],
        "wind_gusts_10m": [15.0, 18.0, 22.0],
        "visibility": [16000.0, 16000.0, 10000.0],
    }

    route_call = respx_mock.get(url__regex=r"https://api\.open-meteo\.com/v1/forecast.*").respond(
        200, json=[{"hourly": mock_hourly}] * 50
    )

    dep = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    service = WeatherService(provider=OpenMeteoProvider())
    result_map, call_count = service.get_weather_for_routes([r1, r2, r3], departure_time=dep)

    assert route_call.called
    assert route_call.call_count == 1
    assert call_count == 1
    assert len(result_map) == 3
    assert result_map["r1"].status == "ok"
    assert result_map["r2"].status == "ok"
    assert result_map["r3"].status == "ok"
    assert len(result_map["r1"].samples) > 0


def test_weather_service_graceful_degradation_on_timeout(respx_mock):
    """Open-Meteo timeout degrades gracefully to status='unavailable' without raising."""
    r1 = make_dummy_route(0, 500.0)

    respx_mock.get(url__regex=r"https://api\.open-meteo\.com/v1/forecast.*").mock(
        side_effect=Exception("ReadTimeout")
    )

    service = WeatherService()
    result_map, call_count = service.get_weather_for_routes([r1])

    assert call_count == 0
    assert result_map["r1"].status == "unavailable"
    assert result_map["r1"].risk_level is None
    assert result_map["r1"].samples == []
