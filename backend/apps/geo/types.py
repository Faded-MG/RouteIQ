"""Geographic types and data classes.

Conforms to docs/ARCHITECTURE.md §7.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GeocodedLocation:
    """Result of geocoding a location query string."""

    query: str
    query_norm: str
    label: str
    lat: float
    lon: float
