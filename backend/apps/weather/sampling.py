"""Route geospatial sampling for weather forecast queries.

Conforms to docs/ARCHITECTURE.md §6.5.
Samples routes at regular mile markers, computes ETAs, and de-duplicates coordinates.
"""

from datetime import UTC, datetime, timedelta

import numpy as np

from apps.common.constants import (
    WEATHER_MAX_SAMPLES_PER_ROUTE,
    WEATHER_SAMPLE_SPACING_MILES,
)
from apps.geo.types import DrivingRoute


def interpolate_coord_at_mile(
    coords: np.ndarray,
    cum_miles: np.ndarray,
    target_mile: float,
) -> tuple[float, float]:
    """Find the interpolated (lat, lon) on the route coordinates at target_mile."""
    if len(cum_miles) == 0:
        return 0.0, 0.0
    if target_mile <= cum_miles[0]:
        return float(coords[0, 0]), float(coords[0, 1])
    if target_mile >= cum_miles[-1]:
        return float(coords[-1, 0]), float(coords[-1, 1])

    idx = int(np.searchsorted(cum_miles, target_mile))
    if idx == 0:
        return float(coords[0, 0]), float(coords[0, 1])

    m0 = float(cum_miles[idx - 1])
    m1 = float(cum_miles[idx])
    seg_len = m1 - m0
    if seg_len <= 1e-6:
        return float(coords[idx, 0]), float(coords[idx, 1])

    frac = (target_mile - m0) / seg_len
    lat = float(coords[idx - 1, 0] + frac * (coords[idx, 0] - coords[idx - 1, 0]))
    lon = float(coords[idx - 1, 1] + frac * (coords[idx, 1] - coords[idx - 1, 1]))
    return lat, lon


def sample_route_for_weather(
    route: DrivingRoute,
    departure_time: datetime | None = None,
) -> list[dict]:
    """Generate weather sample checkpoints along a driving route.

    Checks:
    - Mile 0
    - Every ~100 miles
    - Destination mile
    - At most WEATHER_MAX_SAMPLES_PER_ROUTE (12) points
    """
    total_miles = float(route.distance_miles)
    duration_sec = float(route.duration_seconds)
    dep = departure_time or datetime.now(UTC)

    if total_miles <= 0.0:
        lat, lon = (
            (float(route.coords[0, 0]), float(route.coords[0, 1]))
            if len(route.coords) > 0
            else (0.0, 0.0)
        )
        return [
            {
                "route_mile": 0.0,
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "eta": dep.isoformat(),
                "eta_dt": dep,
            }
        ]

    # Stride widens if distance requires more than max samples
    stride = max(
        WEATHER_SAMPLE_SPACING_MILES,
        total_miles / (WEATHER_MAX_SAMPLES_PER_ROUTE - 1),
    )

    mile_markers = [0.0]
    curr_m = stride
    while curr_m < total_miles - 1e-4:
        mile_markers.append(round(curr_m, 1))
        curr_m += stride

    if not np.isclose(mile_markers[-1], total_miles):
        mile_markers.append(round(total_miles, 1))

    # Cap at WEATHER_MAX_SAMPLES_PER_ROUTE
    if len(mile_markers) > WEATHER_MAX_SAMPLES_PER_ROUTE:
        mile_markers = [
            round(float(m), 1) for m in np.linspace(0.0, total_miles, WEATHER_MAX_SAMPLES_PER_ROUTE)
        ]

    samples = []
    for m in mile_markers:
        frac = m / total_miles if total_miles > 0 else 0.0
        sample_eta = dep + timedelta(seconds=duration_sec * frac)
        lat, lon = interpolate_coord_at_mile(route.coords, route.cum_miles, m)
        samples.append(
            {
                "route_mile": round(m, 1),
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "eta": sample_eta.isoformat(),
                "eta_dt": sample_eta,
            }
        )

    return samples
