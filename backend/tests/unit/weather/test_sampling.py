"""Unit tests for weather route sampling.

Conforms to docs/ARCHITECTURE.md §6.5 and docs/PLAN.md T17.
"""

from datetime import UTC, datetime

import numpy as np

from apps.common.constants import WEATHER_MAX_SAMPLES_PER_ROUTE
from apps.geo.types import DrivingRoute
from apps.weather.sampling import interpolate_coord_at_mile, sample_route_for_weather


def test_interpolate_coord_at_mile():
    """Coordinates are linearly interpolated along route polyline segments."""
    coords = np.array([[40.0, -80.0], [41.0, -80.0], [42.0, -80.0]], dtype=np.float64)
    cum_miles = np.array([0.0, 50.0, 100.0], dtype=np.float64)

    # At start
    lat, lon = interpolate_coord_at_mile(coords, cum_miles, 0.0)
    assert np.isclose(lat, 40.0)
    assert np.isclose(lon, -80.0)

    # Halfway between 0 and 50 miles (mile 25)
    lat, lon = interpolate_coord_at_mile(coords, cum_miles, 25.0)
    assert np.isclose(lat, 40.5)
    assert np.isclose(lon, -80.0)

    # At destination
    lat, lon = interpolate_coord_at_mile(coords, cum_miles, 100.0)
    assert np.isclose(lat, 42.0)
    assert np.isclose(lon, -80.0)


def test_sample_route_for_weather_spacing_and_cap():
    """Samples every ~100 miles, includes mile 0 and destination, capped at 12."""
    coords = np.array([[40.0, -80.0], [42.0, -82.0]], dtype=np.float64)
    cum_miles = np.array([0.0, 750.0], dtype=np.float64)

    route = DrivingRoute(
        route_index=0,
        distance_miles=750.0,
        duration_seconds=36000.0,
        geometry_polyline6="dummy",
        coords=coords,
        cum_miles=cum_miles,
    )

    dep = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    samples = sample_route_for_weather(route, departure_time=dep)

    assert len(samples) <= WEATHER_MAX_SAMPLES_PER_ROUTE
    assert samples[0]["route_mile"] == 0.0
    assert samples[-1]["route_mile"] == 750.0
    assert samples[0]["eta"] == "2026-11-06T12:00:00+00:00"
    # Destination ETA is 10 hours later
    assert "22:00:00" in samples[-1]["eta"]


def test_sample_route_very_long_trip_capped():
    """Very long coast-to-coast route (2,800 miles) stride widens and never exceeds 12."""
    coords = np.array([[34.0, -118.0], [40.0, -74.0]], dtype=np.float64)
    cum_miles = np.array([0.0, 2800.0], dtype=np.float64)

    route = DrivingRoute(
        route_index=0,
        distance_miles=2800.0,
        duration_seconds=140000.0,
        geometry_polyline6="dummy",
        coords=coords,
        cum_miles=cum_miles,
    )

    samples = sample_route_for_weather(route)
    assert len(samples) == WEATHER_MAX_SAMPLES_PER_ROUTE
    assert samples[0]["route_mile"] == 0.0
    assert samples[-1]["route_mile"] == 2800.0
