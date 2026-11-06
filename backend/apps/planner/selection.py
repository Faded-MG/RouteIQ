"""Route selection and comparison service.

Conforms to docs/ALGORITHM.md §10 and docs/API_SPEC.md §4.2.
Deterministic multi-route recommendation, ranking, and comparison row generation.
"""

from dataclasses import dataclass
from typing import Any

from apps.common.constants import MAX_DURATION_RATIO
from apps.fuel.types import FuelPlan, InfeasibleResult


@dataclass(frozen=True)
class EvaluatedRoute:
    """Internal container for an evaluated route before ranking."""

    route_id: str
    original_index: int
    distance_miles: float
    duration_minutes: float
    display_coords: list[list[float]]
    fuel_plan_res: FuelPlan | InfeasibleResult
    formatted_fuel_plan: dict[str, Any]
    weather: dict[str, Any]

    @property
    def is_feasible(self) -> bool:
        if isinstance(self.fuel_plan_res, InfeasibleResult):
            return False
        return self.fuel_plan_res.status in ("ok", "no_refuel_needed")

    @property
    def total_fuel_cost_usd(self) -> float | None:
        if self.is_feasible and hasattr(self.fuel_plan_res, "totals"):
            return self.fuel_plan_res.totals.total_fuel_cost_usd
        return None

    @property
    def avg_price_per_gal(self) -> float | None:
        if self.is_feasible and hasattr(self.fuel_plan_res, "totals"):
            return self.fuel_plan_res.totals.avg_price_per_gal
        return None

    @property
    def num_stops(self) -> int:
        if self.is_feasible and hasattr(self.fuel_plan_res, "stops"):
            return len(self.fuel_plan_res.stops)
        return 0

    @property
    def weather_risk(self) -> str | None:
        return self.weather.get("risk_level")


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of multi-route selection and ranking."""

    recommended_route_id: str
    reason: str
    considered_count: int
    discarded: list[dict[str, str]]
    ranked_routes: list[dict[str, Any]]
    comparison: list[dict[str, Any]]


def select_and_rank_routes(
    routes: list[EvaluatedRoute],
) -> SelectionResult:
    """Apply the deterministic route selection rules of ALGORITHM.md §10.

    Rules:
    1. Discard routes with an infeasible fuel plan.
    2. Discard routes slower than MAX_DURATION_RATIO (1.25) * fastest feasible duration.
    3. Discard routes with weather.risk_level == 'severe' if any non-severe route remains.
    4. Choose lowest total_fuel_cost_usd; ties -> lower duration -> lower route id.

    Returns SelectionResult with ranked routes (rank 1 = recommended) and comparison rows.
    """
    if not routes:
        raise ValueError("Cannot select from an empty list of routes.")

    considered_count = len(routes)
    discarded: list[dict[str, str]] = []

    # 1. Discard infeasible routes
    feasible_routes: list[EvaluatedRoute] = []
    for r in routes:
        if not r.is_feasible:
            discarded.append({"route_id": r.route_id, "why": "infeasible"})
        else:
            feasible_routes.append(r)

    if not feasible_routes:
        # All routes are infeasible; caller handles raising NO_FEASIBLE_FUEL_PLAN
        raise ValueError("All routes are infeasible.")

    # 2. Duration filter (relative to fastest feasible route)
    fastest_feasible_duration = min(r.duration_minutes for r in feasible_routes)
    max_allowed_duration = MAX_DURATION_RATIO * fastest_feasible_duration

    within_duration: list[EvaluatedRoute] = []
    for r in feasible_routes:
        if r.duration_minutes > max_allowed_duration:
            discarded.append({"route_id": r.route_id, "why": "duration_exceeds_limit"})
        else:
            within_duration.append(r)

    # 3. Severe weather filter
    severe_routes = [r for r in within_duration if r.weather_risk == "severe"]
    non_severe_routes = [r for r in within_duration if r.weather_risk != "severe"]

    avoided_severe = False
    if non_severe_routes and severe_routes:
        for r in severe_routes:
            discarded.append({"route_id": r.route_id, "why": "severe_weather"})
        candidates_pool = non_severe_routes
        avoided_severe = True
    else:
        candidates_pool = within_duration

    # 4. Tie-breaking and winner selection
    # Lowest total_fuel_cost_usd -> lower duration -> lower route id
    candidates_pool.sort(
        key=lambda r: (
            r.total_fuel_cost_usd if r.total_fuel_cost_usd is not None else float("inf"),
            r.duration_minutes,
            r.route_id,
        )
    )
    winner = candidates_pool[0]

    # Determine recommendation reason code
    if len(feasible_routes) == 1 and considered_count > 1:
        reason = "only_feasible_route"
    elif avoided_severe and any(
        sr.total_fuel_cost_usd is not None
        and winner.total_fuel_cost_usd is not None
        and sr.total_fuel_cost_usd < winner.total_fuel_cost_usd
        for sr in severe_routes
    ):
        reason = "lowest_cost_avoiding_severe_weather"
    elif any(d["why"] == "duration_exceeds_limit" for d in discarded) and any(
        r.total_fuel_cost_usd is not None
        and winner.total_fuel_cost_usd is not None
        and r.total_fuel_cost_usd < winner.total_fuel_cost_usd
        for r in feasible_routes
        if r.duration_minutes > max_allowed_duration
    ):
        reason = "lowest_cost_within_duration_limit"
    else:
        reason = "lowest_cost"

    # Order all routes: winner first (rank 1), other feasible routes, then infeasible routes
    other_feasible = [r for r in feasible_routes if r.route_id != winner.route_id]
    other_feasible.sort(
        key=lambda r: (
            r.total_fuel_cost_usd if r.total_fuel_cost_usd is not None else float("inf"),
            r.duration_minutes,
            r.route_id,
        )
    )
    infeasible_routes = [r for r in routes if not r.is_feasible]
    infeasible_routes.sort(key=lambda r: (r.duration_minutes, r.route_id))

    sorted_routes = [winner] + other_feasible + infeasible_routes

    # Build response Route and ComparisonRow objects
    ranked_route_dicts: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []

    for rank_idx, r in enumerate(sorted_routes, start=1):
        is_rec = r.route_id == winner.route_id
        ranked_route_dicts.append(
            {
                "id": r.route_id,
                "rank": rank_idx,
                "is_recommended": is_rec,
                "summary": {
                    "distance_miles": round(r.distance_miles, 1),
                    "duration_minutes": int(round(r.duration_minutes)),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": r.display_coords,
                },
                "fuel_plan": r.formatted_fuel_plan,
                "weather": r.weather,
            }
        )

        has_costs = (
            r.is_feasible
            and r.total_fuel_cost_usd is not None
            and winner.total_fuel_cost_usd is not None
        )
        if has_costs:
            cost_delta = (
                0.00
                if is_rec
                else round(float(r.total_fuel_cost_usd - winner.total_fuel_cost_usd), 2)
            )
        else:
            cost_delta = None

        duration_delta = int(round(r.duration_minutes - winner.duration_minutes))

        comparison_rows.append(
            {
                "route_id": r.route_id,
                "distance_miles": round(r.distance_miles, 1),
                "duration_minutes": int(round(r.duration_minutes)),
                "total_fuel_cost_usd": r.total_fuel_cost_usd,
                "num_stops": r.num_stops,
                "avg_price_per_gal": r.avg_price_per_gal,
                "weather_risk": r.weather_risk,
                "cost_delta_vs_recommended_usd": cost_delta,
                "duration_delta_minutes": duration_delta,
            }
        )

    return SelectionResult(
        recommended_route_id=winner.route_id,
        reason=reason,
        considered_count=considered_count,
        discarded=discarded,
        ranked_routes=ranked_route_dicts,
        comparison=comparison_rows,
    )
