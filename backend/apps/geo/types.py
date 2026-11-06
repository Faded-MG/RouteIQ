"""Geographic types and data classes.

Conforms to docs/ARCHITECTURE.md §7.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GeocodedLocation:
    """Result of geocoding a location query string."""

    query: str
    query_norm: str
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class DrivingRoute:
    """Parsed driving route from routing provider."""

    route_index: int
    distance_miles: float
    duration_seconds: float
    geometry_polyline6: str
    coords: np.ndarray  # float64[N, 2]
    cum_miles: np.ndarray  # float64[N]
