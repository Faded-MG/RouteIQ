"""Unit tests for route selection and comparison logic.

Conforms to docs/PLAN.md T16, docs/ALGORITHM.md §10, and docs/TESTING.md §9 AT-13.
"""

from typing import Any

import pytest

from apps.fuel.types import FuelPlan, InfeasibleResult, PlanTotals
from apps.planner.selection import EvaluatedRoute, select_and_rank_routes


def make_evaluated_route(
    route_id: str,
    original_index: int,
    distance_miles: float,
    duration_minutes: float,
    total_fuel_cost_usd: float | None = 250.0,
    status: str = "ok",
    weather_risk: str | None = None,
    num_stops: int = 3,
) -> EvaluatedRoute:
    """Helper to construct an EvaluatedRoute for testing."""
    if status == "infeasible" or total_fuel_cost_usd is None:
        fp_res = InfeasibleResult(
            status="infeasible",
            largest_gap={"from_mile": 100.0, "to_mile": 650.0, "gap_miles": 550.0},
        )
        formatted_fp: dict[str, Any] = {
            "status": "infeasible",
            "origin_price_source": None,
            "stops": [],
            "totals": None,
            "infeasible": fp_res.largest_gap,
        }
    else:
        totals = PlanTotals(
            fuel_purchased_gal=distance_miles / 10.0,
            fuel_consumed_gal=distance_miles / 10.0,
            total_fuel_cost_usd=round(total_fuel_cost_usd, 2),
            avg_price_per_gal=3.15,
            cost_per_mile_usd=0.315,
            leftover_gal=0.0,
            stops_count=num_stops,
        )
        fp_res = FuelPlan(
            status=status,
            origin_price_source="nearest_station",
            stops=[object()] * num_stops,  # type: ignore[list-item]
            totals=totals,
        )
        formatted_fp = {
            "status": status,
            "origin_price_source": "nearest_station",
            "stops": [{"sequence": i + 1} for i in range(num_stops)],
            "totals": {
                "total_fuel_cost_usd": totals.total_fuel_cost_usd,
                "fuel_consumed_gal": totals.fuel_consumed_gal,
                "fuel_purchased_gal": totals.fuel_purchased_gal,
                "leftover_gal": totals.leftover_gal,
                "avg_price_per_gal": totals.avg_price_per_gal,
                "cost_per_mile_usd": totals.cost_per_mile_usd,
                "num_stops": num_stops,
                "extra_detour_miles": 5.0,
            },
        }

    return EvaluatedRoute(
        route_id=route_id,
        original_index=original_index,
        distance_miles=distance_miles,
        duration_minutes=duration_minutes,
        display_coords=[[-74.0, 40.7], [-87.6, 41.8]],
        fuel_plan_res=fp_res,
        formatted_fuel_plan=formatted_fp,
        weather={
            "status": "disabled" if weather_risk is None else "ok",
            "risk_level": weather_risk,
            "summary": None,
            "samples": [],
        },
    )


def test_single_feasible_route():
    """Single route returns rank 1, lowest_cost, considered 1."""
    r1 = make_evaluated_route("r1", 0, 790.0, 720.0, total_fuel_cost_usd=250.0)
    res = select_and_rank_routes([r1])

    assert res.recommended_route_id == "r1"
    assert res.reason == "lowest_cost"
    assert res.considered_count == 1
    assert res.discarded == []
    assert len(res.ranked_routes) == 1
    assert res.ranked_routes[0]["rank"] == 1
    assert res.ranked_routes[0]["is_recommended"] is True
    assert len(res.comparison) == 1
    assert res.comparison[0]["cost_delta_vs_recommended_usd"] == 0.00
    assert res.comparison[0]["duration_delta_minutes"] == 0


def test_two_feasible_routes_lowest_cost_wins():
    """Route with lower cost is recommended and comparison deltas computed."""
    r1 = make_evaluated_route("r1", 0, 800.0, 740.0, total_fuel_cost_usd=260.0)
    r2 = make_evaluated_route("r2", 1, 790.0, 720.0, total_fuel_cost_usd=250.0)

    res = select_and_rank_routes([r1, r2])

    assert res.recommended_route_id == "r2"
    assert res.reason == "lowest_cost"
    assert res.considered_count == 2
    assert res.discarded == []

    # r2 is rank 1, r1 is rank 2
    assert res.ranked_routes[0]["id"] == "r2"
    assert res.ranked_routes[0]["rank"] == 1
    assert res.ranked_routes[0]["is_recommended"] is True

    assert res.ranked_routes[1]["id"] == "r1"
    assert res.ranked_routes[1]["rank"] == 2
    assert res.ranked_routes[1]["is_recommended"] is False

    # Comparison deltas
    assert res.comparison[0]["route_id"] == "r2"
    assert res.comparison[0]["cost_delta_vs_recommended_usd"] == 0.00
    assert res.comparison[0]["duration_delta_minutes"] == 0

    assert res.comparison[1]["route_id"] == "r1"
    assert res.comparison[1]["cost_delta_vs_recommended_usd"] == 10.00
    assert res.comparison[1]["duration_delta_minutes"] == 20


def test_tie_breaking_by_duration_then_id():
    """Equal cost ties broken by duration; equal duration ties broken by id."""
    # Cost equal, r2 has shorter duration
    r1 = make_evaluated_route("r1", 0, 790.0, 730.0, total_fuel_cost_usd=250.0)
    r2 = make_evaluated_route("r2", 1, 790.0, 710.0, total_fuel_cost_usd=250.0)
    res = select_and_rank_routes([r1, r2])
    assert res.recommended_route_id == "r2"

    # Cost and duration equal -> r1 wins by id ("r1" < "r2")
    r1_same = make_evaluated_route("r1", 0, 790.0, 700.0, total_fuel_cost_usd=250.0)
    r2_same = make_evaluated_route("r2", 1, 790.0, 700.0, total_fuel_cost_usd=250.0)
    res_same = select_and_rank_routes([r1_same, r2_same])
    assert res_same.recommended_route_id == "r1"


def test_discard_infeasible_route_and_only_feasible_reason():
    """Infeasible route discarded; when 1 feasible route remains, reason is only_feasible_route."""
    r1 = make_evaluated_route("r1", 0, 790.0, 720.0, status="infeasible")
    r2 = make_evaluated_route("r2", 1, 800.0, 730.0, total_fuel_cost_usd=260.0, status="ok")

    res = select_and_rank_routes([r1, r2])

    assert res.recommended_route_id == "r2"
    assert res.reason == "only_feasible_route"
    assert res.discarded == [{"route_id": "r1", "why": "infeasible"}]

    # Ranked routes: r2 rank 1, r1 rank 2
    assert res.ranked_routes[0]["id"] == "r2"
    assert res.ranked_routes[1]["id"] == "r1"
    assert res.ranked_routes[1]["fuel_plan"]["status"] == "infeasible"

    # Comparison row for infeasible route has null cost and null cost delta
    r1_comp = [c for c in res.comparison if c["route_id"] == "r1"][0]
    assert r1_comp["total_fuel_cost_usd"] is None
    assert r1_comp["cost_delta_vs_recommended_usd"] is None
    assert r1_comp["num_stops"] == 0


def test_duration_ratio_limit_discards_slow_cheaper_route():
    """Route slower than 1.25x fastest feasible route is discarded (ALGORITHM §10 Rule 2)."""
    # Fastest feasible is r1: 600 min. Max allowed is 1.25 * 600 = 750 min.
    # r2 is cheaper ($230 vs $250) but takes 800 min (> 750 min).
    r1 = make_evaluated_route("r1", 0, 750.0, 600.0, total_fuel_cost_usd=250.0)
    r2 = make_evaluated_route("r2", 1, 740.0, 800.0, total_fuel_cost_usd=230.0)

    res = select_and_rank_routes([r1, r2])

    assert res.recommended_route_id == "r1"
    assert res.reason == "lowest_cost_within_duration_limit"
    assert res.discarded == [{"route_id": "r2", "why": "duration_exceeds_limit"}]


def test_severe_weather_avoidance_discards_cheaper_severe_route():
    """Cheaper route with severe weather discarded if non-severe feasible route exists (AT-13)."""
    # r1 is $240, severe weather
    # r2 is $260, non-severe (low)
    # r3 is $270, non-severe (none)
    r1 = make_evaluated_route(
        "r1", 0, 780.0, 700.0, total_fuel_cost_usd=240.0, weather_risk="severe"
    )
    r2 = make_evaluated_route("r2", 1, 790.0, 710.0, total_fuel_cost_usd=260.0, weather_risk="low")
    r3 = make_evaluated_route("r3", 2, 800.0, 720.0, total_fuel_cost_usd=270.0, weather_risk="none")

    res = select_and_rank_routes([r1, r2, r3])

    assert res.recommended_route_id == "r2"
    assert res.reason == "lowest_cost_avoiding_severe_weather"
    assert res.discarded == [{"route_id": "r1", "why": "severe_weather"}]
    assert res.ranked_routes[0]["id"] == "r2"


def test_all_routes_severe_weather_picks_lowest_cost():
    """If all feasible routes have severe weather, rule 3 preserves them and picks lowest cost."""
    r1 = make_evaluated_route(
        "r1", 0, 780.0, 700.0, total_fuel_cost_usd=240.0, weather_risk="severe"
    )
    r2 = make_evaluated_route(
        "r2", 1, 790.0, 710.0, total_fuel_cost_usd=260.0, weather_risk="severe"
    )

    res = select_and_rank_routes([r1, r2])

    assert res.recommended_route_id == "r1"
    assert res.reason == "lowest_cost"
    assert res.discarded == []


def test_all_routes_infeasible_raises_error():
    """When all routes are infeasible, select_and_rank_routes raises ValueError."""
    r1 = make_evaluated_route("r1", 0, 780.0, 700.0, status="infeasible")
    r2 = make_evaluated_route("r2", 1, 790.0, 710.0, status="infeasible")

    with pytest.raises(ValueError, match="All routes are infeasible"):
        select_and_rank_routes([r1, r2])
