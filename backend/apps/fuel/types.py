"""Domain dataclasses for fuel optimization.

Conforms to docs/ALGORITHM.md and docs/PLAN.md T11.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateStation:
    """Eligible refueling station projected onto the route corridor."""

    station_id: int
    opis_id: int
    route_mile: float
    offset_miles: float
    detour_miles: float
    price: float
    lat: float
    lon: float
