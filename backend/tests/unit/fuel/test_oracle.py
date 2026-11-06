"""Brute-force oracle, classical greedy, and property tests for fuel optimizer.

Conforms to docs/TESTING.md §5.
"""

import math
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.fuel.candidates import CandidateStation
from apps.fuel.optimizer import OptimizerConfig, build_fuel_nodes, optimize
from apps.fuel.types import FuelNode, FuelPlan, InfeasibleResult
from apps.fuel.validator import validate_plan

# ---------------------------------------------------------------------------
# Brute-force oracle implementation
# ---------------------------------------------------------------------------


def brute_force_optimal_cost(
    nodes: list[FuelNode],
    dest_mile: float,
    cfg: OptimizerConfig,
    start_fuel_units: int,
) -> float:
    """Exact recursive brute-force search over all visit/purchase decisions.

    Operates in discrete units on small instances (N <= 6, Tank <= 6).
    """
    C = cfg.capacity_units
    m = cfg.margin_units
    memo: dict[tuple[int, int], float] = {}

    def search(node_idx: int, fuel_on_route: int) -> float:
        if (node_idx, fuel_on_route) in memo:
            return memo[(node_idx, fuel_on_route)]

        curr_node = nodes[node_idx]

        # Base case: reached destination
        if curr_node.is_destination:
            return 0.0 if fuel_on_route >= m else float("inf")

        gap = curr_node.gap_units_to_next
        best_cost = float("inf")

        # Option 1: Skip current node (not applicable if origin has no start fuel)
        if not curr_node.is_origin or fuel_on_route > 0:
            if fuel_on_route >= gap + m:
                cost_skip = search(node_idx + 1, fuel_on_route - gap)
                if cost_skip < best_cost:
                    best_cost = cost_skip

        # Option 2: Visit current node (if it has a price)
        if curr_node.price is not None:
            h = curr_node.half_detour_units
            pd = curr_node.price * cfg.fuel_unit_gal
            pen = 0.0 if curr_node.is_origin else cfg.stop_penalty_usd
            g_min = 0 if curr_node.is_origin else m

            if fuel_on_route >= h + g_min:
                g = fuel_on_route - h
                # Try all purchase amounts b >= 0 such that g + b <= C
                for q in range(g, C + 1):
                    b = q - g
                    fuel_return = q - h
                    if fuel_return >= gap + m:
                        purchase_cost = pen + b * pd
                        cost_rest = search(node_idx + 1, fuel_return - gap)
                        total = purchase_cost + cost_rest
                        # Strict tie breaking: skip preferred over visit
                        if total < best_cost - 1e-12:
                            best_cost = total

        memo[(node_idx, fuel_on_route)] = best_cost
        return best_cost

    return search(0, start_fuel_units)


@settings(max_examples=250, deadline=None)
@given(
    dest_mile=st.integers(min_value=5, max_value=12),
    start_fuel=st.integers(min_value=0, max_value=3),
    reserve=st.integers(min_value=0, max_value=1),
    data=st.data(),
)
def test_dp_equals_bruteforce(dest_mile, start_fuel, reserve, data):
    """Oracle test: DP cost must equal brute force on small integer instances."""
    cfg = OptimizerConfig(
        mpg=1.0,
        tank_capacity_gal=5.0,
        fuel_unit_gal=1.0,
        reserve_gal=float(reserve),
        safety_margin_units=0,
        stop_penalty_usd=0.0,
    )

    num_stations = data.draw(st.integers(min_value=1, max_value=min(4, dest_mile - 2)))

    # Generate stations at distinct integer miles along the route
    station_miles = sorted(
        data.draw(
            st.sets(
                st.integers(min_value=1, max_value=dest_mile - 1),
                min_size=num_stations,
                max_size=num_stations,
            )
        )
    )

    cands: list[CandidateStation] = []
    for idx, mile in enumerate(station_miles, start=1):
        price = data.draw(st.sampled_from([2.0, 2.5, 3.0, 3.5, 4.0]))
        detour = data.draw(st.sampled_from([0.0, 2.0]))  # 0 or 1 unit each way
        offset = detour / (2.0 * 1.3)
        cands.append(
            CandidateStation(
                station_id=idx,
                opis_id=100 + idx,
                route_mile=float(mile),
                offset_miles=offset,
                detour_miles=detour,
                price=price,
                lat=40.0,
                lon=-80.0,
            )
        )

    orig_price = data.draw(st.sampled_from([2.0, 3.0, 4.0]))
    nodes = build_fuel_nodes(cands, float(dest_mile), orig_price, cfg)

    dp_result = optimize(nodes, float(dest_mile), cfg, start_fuel_gal=float(start_fuel))
    bf_cost = brute_force_optimal_cost(nodes, float(dest_mile), cfg, start_fuel)

    if math.isinf(bf_cost):
        assert isinstance(dp_result, InfeasibleResult)
    else:
        assert isinstance(dp_result, FuelPlan)
        assert dp_result.totals.total_fuel_cost_usd == pytest.approx(bf_cost, abs=1e-3)


# ---------------------------------------------------------------------------
# Classical greedy comparison for no-detour highway problem
# ---------------------------------------------------------------------------


def classical_greedy_cost(
    dest_mile: float,
    orig_price: float,
    stations: list[tuple[float, float]],  # (mile, price)
    tank: float,
    mpg: float,
) -> float:
    """Look-ahead greedy policy without detours or stop penalties."""
    all_stops = [(0.0, orig_price)] + stations + [(dest_mile, 0.0)]
    n = len(all_stops)
    fuel = 0.0
    total_cost = Decimal("0.00")
    max_range = tank * mpg

    curr_idx = 0
    while curr_idx < n - 1:
        curr_mile, curr_price = all_stops[curr_idx]

        # Look ahead for cheaper station in range
        cheaper_idx = None
        for j in range(curr_idx + 1, n):
            dist = all_stops[j][0] - curr_mile
            if dist > max_range:
                break
            if all_stops[j][1] < curr_price:
                cheaper_idx = j
                break

        if cheaper_idx is not None:
            # Cheaper station found: buy just enough to reach it
            target_mile = all_stops[cheaper_idx][0]
            dist_needed = target_mile - curr_mile
            fuel_needed = dist_needed / mpg
            buy = max(0.0, fuel_needed - fuel)
            total_cost += Decimal(str(buy)) * Decimal(str(curr_price))
            fuel = fuel + buy - (dist_needed / mpg)
            curr_idx = cheaper_idx
        else:
            # No cheaper station: fill to capacity or to destination
            dist_to_dest = dest_mile - curr_mile
            if dist_to_dest <= max_range:
                fuel_needed = dist_to_dest / mpg
                buy = max(0.0, fuel_needed - fuel)
                total_cost += Decimal(str(buy)) * Decimal(str(curr_price))
                break
            else:
                buy = max(0.0, tank - fuel)
                total_cost += Decimal(str(buy)) * Decimal(str(curr_price))
                fuel = tank - (all_stops[curr_idx + 1][0] - curr_mile) / mpg
                curr_idx += 1

    return float(total_cost)


def test_dp_equals_classical_greedy_without_detours():
    """Look-ahead greedy equals DP for no-detour zero-penalty instances."""
    cfg = OptimizerConfig(fuel_unit_gal=0.1, stop_penalty_usd=0.0, safety_margin_units=0)
    dest_mile = 900.0
    orig_price = 3.50

    # Test with multiple station configurations
    test_cases = [
        [(100.0, 3.00), (450.0, 3.40), (590.0, 3.10)],
        [(150.0, 3.20), (300.0, 2.90), (600.0, 3.10), (750.0, 3.00)],
        [(200.0, 3.10), (400.0, 3.00), (600.0, 2.90)],
    ]

    for st_list in test_cases:
        cands = [
            CandidateStation(i, 100 + i, m, 0.0, 0.0, p, 40.0, -80.0)
            for i, (m, p) in enumerate(st_list, start=1)
        ]
        nodes = build_fuel_nodes(cands, dest_mile, orig_price, cfg)
        dp_res = optimize(nodes, dest_mile, cfg, start_fuel_gal=0.0)
        greedy_cost = classical_greedy_cost(
            dest_mile, orig_price, st_list, cfg.tank_capacity_gal, cfg.mpg
        )

        assert isinstance(dp_res, FuelPlan)
        assert dp_res.totals.total_fuel_cost_usd == pytest.approx(greedy_cost, abs=0.5)


# ---------------------------------------------------------------------------
# Mathematical properties (Hypothesis)
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    dest_mile=st.floats(min_value=200.0, max_value=800.0),
    orig_price=st.floats(min_value=2.50, max_value=4.50),
    data=st.data(),
)
def test_optimizer_properties(dest_mile, orig_price, data):
    """Property tests: validator pass, lower bound, upper bound, monotonicity."""
    cfg = OptimizerConfig(fuel_unit_gal=0.2, safety_margin_units=1)

    # Generate 1 to 5 stations
    num_stations = data.draw(st.integers(min_value=1, max_value=5))
    step = dest_mile / (num_stations + 1)
    cands: list[CandidateStation] = []
    prices: list[float] = [orig_price]

    for i in range(1, num_stations + 1):
        m = i * step
        p = round(data.draw(st.floats(min_value=2.00, max_value=5.00)), 2)
        prices.append(p)
        cands.append(CandidateStation(i, 100 + i, m, 0.0, 0.0, p, 40.0, -80.0))

    nodes = build_fuel_nodes(cands, dest_mile, orig_price, cfg)
    res = optimize(nodes, dest_mile, cfg, start_fuel_gal=0.0)

    if isinstance(res, FuelPlan) and res.status == "ok":
        # Property (a): Validator accepts every plan produced by DP
        ok, err = validate_plan(res, dest_mile, cfg, start_fuel_gal=0.0)
        assert ok is True, f"Validator failed on DP plan: {err}"

        # Property (b): Cost >= (D / MPG) * min_price
        min_p = min(prices)
        lower_bound = (dest_mile / cfg.mpg) * min_p
        # Allow small tolerance for grid snapping / stop penalty
        assert res.totals.total_fuel_cost_usd >= lower_bound - 0.50

        # Property (f): Leftover fuel is minimal (<= 5 gal)
        assert res.totals.leftover_gal <= 5.0
