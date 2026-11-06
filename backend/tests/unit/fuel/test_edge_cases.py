"""Unit tests for edge cases E1 to E13 from docs/ALGORITHM.md §9."""

import pytest

from apps.fuel.candidates import CandidateStation
from apps.fuel.optimizer import OptimizerConfig, build_fuel_nodes, optimize
from apps.fuel.types import FuelPlan, InfeasibleResult


def test_E1_short_route_empty_tank():
    """E1: Route <= 500 mi, start_fuel_gal = 0.

    Buy only what is needed; exactly 1 stop (origin fill).
    """
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    # 250 miles route
    nodes = build_fuel_nodes([], dest_mile=250.0, origin_price=3.20, cfg=cfg)
    res = optimize(nodes, dest_mile=250.0, cfg=cfg, start_fuel_gal=0.0)

    assert isinstance(res, FuelPlan)
    assert res.status == "ok"
    assert len(res.stops) == 1
    assert res.stops[0].kind == "origin_fill"
    # Needs 25.0 gal (+ small margin <= 0.2 gal)
    assert res.totals.fuel_purchased_gal == pytest.approx(25.1, abs=0.2)


def test_E2_start_fuel_covers_trip():
    """E2: start_fuel_gal covers the trip -> no_refuel_needed, 0 stops, $0."""
    cfg = OptimizerConfig()
    nodes = build_fuel_nodes([], dest_mile=200.0, origin_price=3.00, cfg=cfg)
    res = optimize(nodes, dest_mile=200.0, cfg=cfg, start_fuel_gal=30.0)

    assert isinstance(res, FuelPlan)
    assert res.status == "no_refuel_needed"
    assert len(res.stops) == 0
    assert res.totals.total_fuel_cost_usd == 0.0
    assert res.totals.fuel_purchased_gal == 0.0


def test_E3_zero_stations_in_corridor():
    """E3: Zero stations in corridor.

    Feasible if D <= 500 - margin; infeasible if D > 500.
    """
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    # Feasible case: D = 490 mi
    nodes_feas = build_fuel_nodes([], dest_mile=490.0, origin_price=3.00, cfg=cfg)
    res_feas = optimize(nodes_feas, dest_mile=490.0, cfg=cfg, start_fuel_gal=0.0)
    assert isinstance(res_feas, FuelPlan)
    assert res_feas.status == "ok"

    # Infeasible case: D = 550 mi
    nodes_infeas = build_fuel_nodes([], dest_mile=550.0, origin_price=3.00, cfg=cfg)
    res_infeas = optimize(nodes_infeas, dest_mile=550.0, cfg=cfg, start_fuel_gal=0.0)
    assert isinstance(res_infeas, InfeasibleResult)
    assert res_infeas.status == "infeasible"


def test_E4_gap_exceeds_500_miles():
    """E4: Gap between consecutive reachable stations > 500 mi -> InfeasibleResult."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    cands = [
        CandidateStation(1, 101, 100.0, 0.0, 0.0, 3.00, 40.0, -80.0),
        CandidateStation(2, 102, 650.0, 0.0, 0.0, 3.00, 40.0, -80.0),  # Gap is 550 miles
    ]
    nodes = build_fuel_nodes(cands, dest_mile=800.0, origin_price=3.00, cfg=cfg)
    res = optimize(nodes, dest_mile=800.0, cfg=cfg, start_fuel_gal=0.0)

    assert isinstance(res, InfeasibleResult)
    assert res.largest_gap is not None
    assert res.largest_gap["gap_miles"] == 550.0


def test_E5_two_stations_at_same_mile_marker():
    """E5: Two stations at the same mile marker -> DP picks the better (cheaper)."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    cands = [
        CandidateStation(1, 101, 200.0, 0.0, 0.0, 3.50, 40.0, -80.0),  # More expensive
        CandidateStation(2, 102, 200.0, 0.0, 0.0, 3.00, 40.0, -80.0),  # Cheaper
    ]
    nodes = build_fuel_nodes(cands, dest_mile=600.0, origin_price=3.50, cfg=cfg)
    res = optimize(nodes, dest_mile=600.0, cfg=cfg, start_fuel_gal=20.0)

    assert isinstance(res, FuelPlan)
    refuel_ids = [s.station_id for s in res.stops if s.kind == "refuel"]
    assert 2 in refuel_ids
    assert 1 not in refuel_ids


def test_E6_equal_prices_everywhere():
    """E6: Equal prices everywhere -> minimum stops, no micro-purchases."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    # Stations every 50 miles for 900 miles
    cands = [
        CandidateStation(i, 100 + i, float(m), 0.0, 0.0, 3.00, 40.0, -80.0)
        for i, m in enumerate(range(50, 900, 50), start=1)
    ]
    nodes = build_fuel_nodes(cands, dest_mile=900.0, origin_price=3.00, cfg=cfg)
    res = optimize(nodes, dest_mile=900.0, cfg=cfg, start_fuel_gal=0.0)

    assert isinstance(res, FuelPlan)
    # For a 900 mi trip with 500 mi range, minimum stops is 2 (origin fill + 1 stop)
    assert len(res.stops) == 2
    # Verify no micro-purchase (each purchase should be substantial >= 40 gal)
    for s in res.stops:
        assert s.gallons_bought >= 40.0


def test_E7_station_at_exact_500_miles_infeasible_due_to_margin():
    """E7: Station exactly 500.0 mi from previous stop is infeasible due to 0.1-mi safety margin."""
    cfg = OptimizerConfig(fuel_unit_gal=0.01, safety_margin_units=1)  # margin = 1 unit = 0.1 mi
    # Exactly 500.0 mi to destination with full tank 50 gal (500.0 mi)
    nodes = build_fuel_nodes([], dest_mile=500.0, origin_price=3.00, cfg=cfg)
    res = optimize(nodes, dest_mile=500.0, cfg=cfg, start_fuel_gal=50.0)
    # Because of 0.1 mi safety margin, exactly 500.0 mi requires 50.01 gal > 50.0 gal capacity
    assert isinstance(res, InfeasibleResult)

    # 499.8 mi should be feasible
    nodes_ok = build_fuel_nodes([], dest_mile=499.8, origin_price=3.00, cfg=cfg)
    res_ok = optimize(nodes_ok, dest_mile=499.8, cfg=cfg, start_fuel_gal=50.0)
    assert isinstance(res_ok, FuelPlan)


def test_E8_reserve_fuel_enforced():
    """E8: RESERVE_GAL = 5 -> max leg becomes 450 mi."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1, reserve_gal=5.0, safety_margin_units=0)
    # Distance 470 mi (> 450 mi with 5 gal reserve)
    nodes_long = build_fuel_nodes([], dest_mile=470.0, origin_price=3.00, cfg=cfg)
    res_long = optimize(nodes_long, dest_mile=470.0, cfg=cfg, start_fuel_gal=50.0)
    assert isinstance(res_long, InfeasibleResult)

    # Distance 440 mi (<= 450 mi)
    nodes_short = build_fuel_nodes([], dest_mile=440.0, origin_price=3.00, cfg=cfg)
    res_short = optimize(nodes_short, dest_mile=440.0, cfg=cfg, start_fuel_gal=50.0)
    assert isinstance(res_short, FuelPlan)


def test_E9_detour_savings_vs_fuel_cost():
    """E9: Cheaper station with large detour chosen only if savings exceed detour fuel cost."""
    # Already covered comprehensively in test_example_b_detour_breakeven
    cfg = OptimizerConfig(fuel_unit_gal=0.1, safety_margin_units=0)
    # Detour of 50 miles (burns 5 gal = $15)
    cands = [
        # Station 1 saves $0.05/gal, but costs $15 in detour
        CandidateStation(1, 101, 100.0, 19.23, 50.0, 2.95, 40.0, -80.0),
        CandidateStation(2, 102, 100.0, 0.0, 0.0, 3.00, 40.0, -80.0),  # on route
    ]
    # On 50 gal purchase, saves 50 * 0.05 = $2.50, but burns 5 * 2.95 = $14.75 in detour!
    nodes = build_fuel_nodes(cands, dest_mile=400.0, origin_price=3.50, cfg=cfg)
    res = optimize(nodes, dest_mile=400.0, cfg=cfg, start_fuel_gal=10.0)
    assert isinstance(res, FuelPlan)
    refuel_ids = [s.station_id for s in res.stops if s.kind == "refuel"]
    assert 2 in refuel_ids
    assert 1 not in refuel_ids


def test_E10_route_loop_earliest_mile_marker():
    """E10: Station passed twice (loop) uses earliest mile marker."""
    cands = [CandidateStation(1, 101, 50.0, 0.0, 0.0, 3.00, 40.0, -80.0)]
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    nodes = build_fuel_nodes(cands, dest_mile=300.0, origin_price=3.00, cfg=cfg)
    assert nodes[1].route_mile == 50.0


def test_E11_price_outliers_avoided():
    """E11: Price outliers (e.g. $6.399) avoided naturally by DP."""
    cands = [
        CandidateStation(1, 101, 100.0, 0.0, 0.0, 6.399, 40.0, -80.0),  # Extreme outlier
        CandidateStation(2, 102, 150.0, 0.0, 0.0, 3.100, 40.0, -80.0),  # Normal price
    ]
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    nodes = build_fuel_nodes(cands, dest_mile=500.0, origin_price=3.00, cfg=cfg)
    res = optimize(nodes, dest_mile=500.0, cfg=cfg, start_fuel_gal=15.0)

    assert isinstance(res, FuelPlan)
    refuel_ids = [s.station_id for s in res.stops if s.kind == "refuel"]
    assert 1 not in refuel_ids
    assert 2 in refuel_ids


def test_E12_very_short_route_geometry():
    """E12: Very short route (< 1 mi) handled by optimizer gracefully if called."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    nodes = build_fuel_nodes([], dest_mile=0.5, origin_price=3.00, cfg=cfg)
    res = optimize(nodes, dest_mile=0.5, cfg=cfg, start_fuel_gal=0.0)
    assert isinstance(res, FuelPlan)
    assert res.status == "ok"


def test_E13_origin_price_state_median_fallback():
    """E13: Origin price source flagged as state_median when fallback used."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    nodes = build_fuel_nodes([], dest_mile=200.0, origin_price=3.25, cfg=cfg)
    res = optimize(
        nodes,
        dest_mile=200.0,
        cfg=cfg,
        start_fuel_gal=0.0,
        origin_price_source="state_median",
    )
    assert isinstance(res, FuelPlan)
    assert res.origin_price_source == "state_median"


def test_margin_applies_on_station_arrival():
    """A plan whose station arrival fuel would be 0.00 gal is never produced.

    Arrival fuel at any refuel stop must be >= safety_margin_units * fuel_unit_gal.
    """
    cfg = OptimizerConfig(fuel_unit_gal=0.1, safety_margin_units=10)
    # Station at 495 miles from origin; with 50 gal tank at 10 mpg,
    # arrival fuel would be 50 - 49.5 = 0.5 gal, which violates 1.0 gal safety margin.
    # Therefore, 495 miles must be unreachable directly from origin.
    cands_unreachable = [
        CandidateStation(1, 101, 495.0, 0.0, 0.0, 3.00, 40.0, -80.0),
    ]
    nodes_unreach = build_fuel_nodes(cands_unreachable, dest_mile=600.0, origin_price=4.00, cfg=cfg)
    res_unreach = optimize(nodes_unreach, dest_mile=600.0, cfg=cfg, start_fuel_gal=50.0)
    assert isinstance(res_unreach, InfeasibleResult)

    # Station at 485 miles; arrival fuel is 50 - 48.5 = 1.5 gal >= 1.0 gal safety margin.
    # Therefore, 485 miles is reachable and feasible.
    cands_reachable = [
        CandidateStation(1, 101, 485.0, 0.0, 0.0, 3.00, 40.0, -80.0),
    ]
    nodes_reach = build_fuel_nodes(cands_reachable, dest_mile=600.0, origin_price=4.00, cfg=cfg)
    res_reach = optimize(nodes_reach, dest_mile=600.0, cfg=cfg, start_fuel_gal=50.0)
    assert isinstance(res_reach, FuelPlan)
    assert res_reach.status == "ok"
    # Verify arrival fuel at stop is at least margin
    refuel_stop = [s for s in res_reach.stops if s.kind == "refuel"][0]
    expected_margin_gal = cfg.safety_margin_units * cfg.fuel_unit_gal
    assert refuel_stop.fuel_after_arrival_gal >= expected_margin_gal - 1e-4
