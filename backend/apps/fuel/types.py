"""Domain dataclasses for fuel optimization.

Conforms to docs/ALGORITHM.md, docs/API_SPEC.md §4.2, and docs/PLAN.md T11.
Pure Python domain types without Django, ORM, or HTTP imports.
"""

from dataclasses import asdict, dataclass
from typing import Any


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


@dataclass(frozen=True)
class FuelNode:
    """Internal optimization node along the route (origin, station, or destination)."""

    index: int
    snapped_mile: float
    route_mile: float
    price: float | None
    detour_miles: float
    half_detour_units: int
    gap_units_to_next: int
    is_origin: bool
    is_destination: bool
    station_id: int | None = None
    opis_id: int | None = None
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    lat: float = 0.0
    lon: float = 0.0
    kind: str = "refuel"  # "origin_fill" | "refuel"


@dataclass(frozen=True)
class FuelStop:
    """Refueling stop chosen by the optimizer."""

    stop_index: int
    kind: str  # "origin_fill" | "refuel"
    station_id: int
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    lat: float
    lon: float
    route_mile: float
    offset_miles: float
    detour_miles: float
    price_per_gal: float
    gallons_bought: float
    cost_usd: float
    fuel_after_arrival_gal: float
    fuel_after_purchase_gal: float
    fuel_after_depart_gal: float
    eta_iso: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict matching API_SPEC §4.2 stop schema."""
        return asdict(self)


@dataclass(frozen=True)
class PlanTotals:
    """Aggregated metrics for a refueling plan."""

    fuel_purchased_gal: float
    fuel_consumed_gal: float
    total_fuel_cost_usd: float
    avg_price_per_gal: float
    cost_per_mile_usd: float
    leftover_gal: float
    stops_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict matching API_SPEC §4.2 totals schema."""
        return asdict(self)


@dataclass(frozen=True)
class FuelPlan:
    """Feasible refueling plan for a driving route."""

    status: str  # "ok" | "no_refuel_needed"
    origin_price_source: str  # "nearest_station" | "state_median" | "national_median"
    stops: list[FuelStop]
    totals: PlanTotals

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict matching API_SPEC §4.2 fuel_plan schema."""
        return {
            "status": self.status,
            "origin_price_source": self.origin_price_source,
            "stops": [s.to_dict() for s in self.stops],
            "totals": self.totals.to_dict(),
        }


@dataclass(frozen=True)
class InfeasibleResult:
    """Infeasible route analysis with the largest reachability gap."""

    status: str = "infeasible"
    largest_gap: dict[str, float] | None = None  # from_mile, to_mile, gap_miles

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict matching API_SPEC §3 error details."""
        return {
            "status": self.status,
            "largest_gap": self.largest_gap or {},
        }
