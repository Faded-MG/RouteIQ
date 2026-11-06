"""Unit tests for optimizer worked examples A, B, C from docs/ALGORITHM.md §11."""

import pytest

from apps.fuel.candidates import CandidateStation
from apps.fuel.optimizer import OptimizerConfig, build_fuel_nodes, optimize
from apps.fuel.types import FuelPlan, InfeasibleResult


def test_example_a_optimal_vs_naive():
    """Worked Example A: D = 900 mi, start_fuel = 0, p0 = 3.50.

    Stations: S1 (100 mi, $3.00), S2 (450 mi, $3.40), S3 (590 mi, $3.10).
    Expected: Origin buys 10.0 gal ($35.00), S1 buys 50.0 gal ($150.00),
    S3 buys 30.0 gal ($93.00). Total = $278.00. S2 skipped.
    """
    # Grid unit 0.1 for fast exact test or 0.01 with 0 margin for clean example check
    cfg = OptimizerConfig(fuel_unit_gal=0.1, safety_margin_units=0)
    cands = [
        CandidateStation(1, 101, 100.0, 0.0, 0.0, 3.00, 40.0, -80.0),
        CandidateStation(2, 102, 450.0, 0.0, 0.0, 3.40, 40.0, -80.0),
        CandidateStation(3, 103, 590.0, 0.0, 0.0, 3.10, 40.0, -80.0),
    ]
    nodes = build_fuel_nodes(cands, dest_mile=900.0, origin_price=3.50, cfg=cfg)
    result = optimize(nodes, dest_mile=900.0, cfg=cfg, start_fuel_gal=0.0)

    assert isinstance(result, FuelPlan)
    assert result.status == "ok"
    # S2 must be skipped
    stop_station_ids = [s.station_id for s in result.stops]
    assert 2 not in stop_station_ids
    assert len(result.stops) == 3

    # Total cost $278.00
    assert result.totals.total_fuel_cost_usd == pytest.approx(278.00, abs=0.5)

    # Gallons bought = 90 gal (900 mi / 10 mpg)
    assert result.totals.fuel_purchased_gal == pytest.approx(90.0, abs=0.5)

    # Naive baseline fill at every reachable stop: $347.40
    naive_cost = 347.40
    assert result.totals.total_fuel_cost_usd < naive_cost


def test_example_b_detour_breakeven():
    """Worked Example B: Two stations at mile 200.

    Station A: $3.00, offset 8 mi -> detour 20.8 mi (2.08 gal).
    Station B: $3.15, on route (detour 0).
    Breakeven at q = 41.6 gal.
    For small need q ~ 35, on-route B wins.
    For large need q ~ 48, detour A wins.
    """
    cfg = OptimizerConfig(fuel_unit_gal=0.1, safety_margin_units=0)

    # Sub-case 1: small need (dest at mile 550: from mile 200 need 350 mi = 35 gal)
    cands_small = [
        CandidateStation(1, 101, 200.0, 8.0, 20.8, 3.00, 40.0, -80.0),  # Station A (detour)
        CandidateStation(2, 102, 200.0, 0.0, 0.0, 3.15, 40.0, -80.0),  # Station B (on-route)
    ]
    nodes_small = build_fuel_nodes(cands_small, dest_mile=550.0, origin_price=3.50, cfg=cfg)
    res_small = optimize(nodes_small, dest_mile=550.0, cfg=cfg, start_fuel_gal=20.0)
    assert isinstance(res_small, FuelPlan)
    # Station B (on-route) should be chosen over A because need is only 35 gal < 41.6 gal
    chosen_small = [s.station_id for s in res_small.stops if s.kind == "refuel"]
    assert 2 in chosen_small
    assert 1 not in chosen_small

    # Sub-case 2: large need (dest at mile 680: from mile 200 need 480 mi = 48 gal)
    nodes_large = build_fuel_nodes(cands_small, dest_mile=680.0, origin_price=3.50, cfg=cfg)
    res_large = optimize(nodes_large, dest_mile=680.0, cfg=cfg, start_fuel_gal=20.0)
    assert isinstance(res_large, FuelPlan)
    # Station A (cheaper with detour) should be chosen because need is 48 gal > 41.6 gal
    chosen_large = [s.station_id for s in res_large.stops if s.kind == "refuel"]
    assert 1 in chosen_large


def test_example_c_infeasible_gap():
    """Worked Example C: Stations at miles 0 (origin), 300, and 850 on a 900-mile route.

    Gap between 300 and 850 is 550 mi > 500 mi capacity.
    Expected: InfeasibleResult with largest_gap = {from_mile: 300, to_mile: 850, gap_miles: 550}.
    """
    cfg = OptimizerConfig(fuel_unit_gal=0.1)
    cands = [
        CandidateStation(1, 101, 300.0, 0.0, 0.0, 3.00, 40.0, -80.0),
        CandidateStation(2, 102, 850.0, 0.0, 0.0, 3.10, 40.0, -80.0),
    ]
    nodes = build_fuel_nodes(cands, dest_mile=900.0, origin_price=3.50, cfg=cfg)
    result = optimize(nodes, dest_mile=900.0, cfg=cfg, start_fuel_gal=0.0)

    assert isinstance(result, InfeasibleResult)
    assert result.status == "infeasible"
    assert result.largest_gap is not None
    assert result.largest_gap["from_mile"] == 300.0
    assert result.largest_gap["to_mile"] == 850.0
    assert result.largest_gap["gap_miles"] == 550.0
