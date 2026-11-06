"""Unit tests for apps/fuel/types.py domain dataclasses."""

from dataclasses import FrozenInstanceError

import pytest

from apps.fuel.types import (
    CandidateStation,
    FuelNode,
    FuelPlan,
    FuelStop,
    InfeasibleResult,
    PlanTotals,
)


def test_candidate_station_frozen():
    cand = CandidateStation(1, 101, 10.0, 0.5, 1.3, 3.25, 40.0, -80.0)
    with pytest.raises(FrozenInstanceError):
        cand.price = 3.50  # type: ignore


def test_fuel_node_frozen():
    node = FuelNode(
        index=0,
        snapped_mile=0.0,
        route_mile=0.0,
        price=3.20,
        detour_miles=0.0,
        half_detour_units=0,
        gap_units_to_next=500,
        is_origin=True,
        is_destination=False,
    )
    with pytest.raises(FrozenInstanceError):
        node.snapped_mile = 10.0  # type: ignore
    assert node.is_origin is True


def test_fuel_stop_to_dict_and_frozen():
    stop = FuelStop(
        stop_index=1,
        kind="refuel",
        station_id=1,
        opis_id=101,
        name="Pilot Travel Center",
        address="100 Main St",
        city="Des Moines",
        state="IA",
        lat=41.5,
        lon=-93.6,
        route_mile=50.0,
        offset_miles=1.0,
        detour_miles=2.6,
        price_per_gal=3.25,
        gallons_bought=30.0,
        cost_usd=97.50,
        fuel_after_arrival_gal=5.0,
        fuel_after_purchase_gal=35.0,
        fuel_after_depart_gal=32.4,
    )
    with pytest.raises(FrozenInstanceError):
        stop.gallons_bought = 40.0  # type: ignore

    d = stop.to_dict()
    assert d["stop_index"] == 1
    assert d["kind"] == "refuel"
    assert d["gallons_bought"] == 30.0
    assert d["cost_usd"] == 97.50


def test_fuel_plan_and_totals_to_dict():
    totals = PlanTotals(
        fuel_purchased_gal=50.0,
        fuel_consumed_gal=48.0,
        total_fuel_cost_usd=160.0,
        avg_price_per_gal=3.20,
        cost_per_mile_usd=0.32,
        leftover_gal=2.0,
        stops_count=1,
    )
    plan = FuelPlan(
        status="ok",
        origin_price_source="nearest_station",
        stops=[],
        totals=totals,
    )
    d = plan.to_dict()
    assert d["status"] == "ok"
    assert d["origin_price_source"] == "nearest_station"
    assert d["totals"]["total_fuel_cost_usd"] == 160.0


def test_infeasible_result_to_dict():
    res = InfeasibleResult(
        status="infeasible",
        largest_gap={"from_mile": 300.0, "to_mile": 850.0, "gap_miles": 550.0},
    )
    d = res.to_dict()
    assert d["status"] == "infeasible"
    assert d["largest_gap"]["gap_miles"] == 550.0
