"""Unit tests for independent plan validator (reachability negative tests)."""

from apps.fuel.optimizer import OptimizerConfig
from apps.fuel.types import FuelPlan, FuelStop, PlanTotals
from apps.fuel.validator import validate_plan


def make_dummy_plan(stops: list[FuelStop]) -> FuelPlan:
    return FuelPlan(
        status="ok",
        origin_price_source="nearest_station",
        stops=stops,
        totals=PlanTotals(
            fuel_purchased_gal=sum(s.gallons_bought for s in stops),
            fuel_consumed_gal=40.0,
            total_fuel_cost_usd=100.0,
            avg_price_per_gal=3.0,
            cost_per_mile_usd=0.25,
            leftover_gal=0.0,
            stops_count=len(stops),
        ),
    )


def test_validator_accepts_valid_plan():
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    stops = [
        FuelStop(
            stop_index=1,
            kind="origin_fill",
            station_id=0,
            opis_id=0,
            name="Origin",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=0.0,
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=40.0,
            cost_usd=120.0,
            fuel_after_arrival_gal=0.0,
            fuel_after_purchase_gal=40.0,
            fuel_after_depart_gal=40.0,
        )
    ]
    plan = make_dummy_plan(stops)
    ok, err = validate_plan(plan, dest_mile=400.0, cfg=cfg, start_fuel_gal=0.0)
    assert ok is True
    assert err == ""


def test_validator_rejects_plan_running_dry_by_small_margin():
    """Plan that runs dry by 0.02 gal must be rejected."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    # Buy only 39.98 gal, but trip is 400 mi -> runs dry at mile 399.8 (needs 40.0 gal)
    stops = [
        FuelStop(
            stop_index=1,
            kind="origin_fill",
            station_id=0,
            opis_id=0,
            name="Origin",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=0.0,
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=39.98,
            cost_usd=119.94,
            fuel_after_arrival_gal=0.0,
            fuel_after_purchase_gal=39.98,
            fuel_after_depart_gal=39.98,
        )
    ]
    plan = make_dummy_plan(stops)
    ok, err = validate_plan(plan, dest_mile=400.0, cfg=cfg, start_fuel_gal=0.0)
    assert ok is False
    assert "Destination arrival fuel" in err


def test_validator_rejects_station_arrival_running_dry():
    """Plan running dry before reaching a station must be rejected."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    # Start with 10 gal (100 mi range), station is at mile 101.0
    stops = [
        FuelStop(
            stop_index=1,
            kind="refuel",
            station_id=1,
            opis_id=101,
            name="S1",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=101.0,
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=30.0,
            cost_usd=90.0,
            fuel_after_arrival_gal=0.0,
            fuel_after_purchase_gal=30.0,
            fuel_after_depart_gal=30.0,
        )
    ]
    plan = make_dummy_plan(stops)
    ok, err = validate_plan(plan, dest_mile=400.0, cfg=cfg, start_fuel_gal=10.0)
    assert ok is False
    assert "Stop 1 arrival fuel" in err


def test_validator_rejects_tank_overfill():
    """Purchasing more than tank capacity must be rejected."""
    cfg = OptimizerConfig(tank_capacity_gal=50.0)
    stops = [
        FuelStop(
            stop_index=1,
            kind="origin_fill",
            station_id=0,
            opis_id=0,
            name="Origin",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=0.0,
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=50.05,  # Exceeds 50.0 gal capacity
            cost_usd=150.15,
            fuel_after_arrival_gal=0.0,
            fuel_after_purchase_gal=50.05,
            fuel_after_depart_gal=50.05,
        )
    ]
    plan = make_dummy_plan(stops)
    ok, err = validate_plan(plan, dest_mile=400.0, cfg=cfg, start_fuel_gal=0.0)
    assert ok is False
    assert "exceeds capacity" in err


def test_validator_rejects_backward_stops():
    """Stops out of order (behind current vehicle position) must be rejected."""
    cfg = OptimizerConfig()
    stops = [
        FuelStop(
            stop_index=1,
            kind="refuel",
            station_id=1,
            opis_id=101,
            name="S1",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=200.0,
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=20.0,
            cost_usd=60.0,
            fuel_after_arrival_gal=10.0,
            fuel_after_purchase_gal=30.0,
            fuel_after_depart_gal=30.0,
        ),
        FuelStop(
            stop_index=2,
            kind="refuel",
            station_id=2,
            opis_id=102,
            name="S2",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=150.0,  # Backward!
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=20.0,
            cost_usd=60.0,
            fuel_after_arrival_gal=10.0,
            fuel_after_purchase_gal=30.0,
            fuel_after_depart_gal=30.0,
        ),
    ]
    plan = make_dummy_plan(stops)
    ok, err = validate_plan(plan, dest_mile=400.0, cfg=cfg, start_fuel_gal=30.0)
    assert ok is False
    assert "is behind vehicle position" in err


def test_validator_handles_infeasible_plan():
    plan = FuelPlan(
        status="infeasible",
        origin_price_source="nearest_station",
        stops=[],
        totals=PlanTotals(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0),
    )
    ok, err = validate_plan(plan, dest_mile=400.0)
    assert ok is True
    assert err == ""


def test_validator_handles_no_refuel_needed():
    plan = FuelPlan(
        status="no_refuel_needed",
        origin_price_source="nearest_station",
        stops=[],
        totals=PlanTotals(0.0, 20.0, 0.0, 0.0, 0.0, 10.0, 0),
    )
    # Sufficient start fuel: 30 gal for 200 mi (20 gal need)
    ok, err = validate_plan(plan, dest_mile=200.0, start_fuel_gal=30.0)
    assert ok is True

    # Insufficient start fuel: 10 gal for 200 mi (20 gal need)
    ok2, err2 = validate_plan(plan, dest_mile=200.0, start_fuel_gal=10.0)
    assert ok2 is False
    assert "insufficient" in err2


def test_validator_rejects_dest_behind_last_stop():
    stops = [
        FuelStop(
            stop_index=1,
            kind="origin_fill",
            station_id=0,
            opis_id=0,
            name="Origin",
            address="",
            city="",
            state="",
            lat=0.0,
            lon=0.0,
            route_mile=100.0,
            offset_miles=0.0,
            detour_miles=0.0,
            price_per_gal=3.0,
            gallons_bought=20.0,
            cost_usd=60.0,
            fuel_after_arrival_gal=0.0,
            fuel_after_purchase_gal=20.0,
            fuel_after_depart_gal=20.0,
        )
    ]
    plan = make_dummy_plan(stops)
    # Start with 20 gal so stop 1 at mile 100 is reachable (burns 10 gal)
    ok, err = validate_plan(plan, dest_mile=50.0, start_fuel_gal=20.0)
    assert ok is False
    assert "Destination mile 50.00 is behind last stop 100.00" in err
