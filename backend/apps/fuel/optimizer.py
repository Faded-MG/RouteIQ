"""Dynamic programming fuel optimizer.

Conforms to docs/ALGORITHM.md §6, §7, §8.
Pure Python and NumPy without Django/ORM imports.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import numpy as np

from apps.common.constants import (
    FUEL_UNIT_GAL,
    MPG,
    RESERVE_GAL,
    SAFETY_MARGIN_UNITS,
    START_FUEL_GAL,
    STOP_PENALTY_USD,
    TANK_CAPACITY_GAL,
)
from apps.fuel.types import (
    CandidateStation,
    FuelNode,
    FuelPlan,
    FuelStop,
    InfeasibleResult,
    PlanTotals,
)


@dataclass(frozen=True)
class OptimizerConfig:
    """Tunable parameters for the optimizer."""

    mpg: float = MPG
    tank_capacity_gal: float = TANK_CAPACITY_GAL
    fuel_unit_gal: float = FUEL_UNIT_GAL
    reserve_gal: float = RESERVE_GAL
    safety_margin_units: int = SAFETY_MARGIN_UNITS
    stop_penalty_usd: float = STOP_PENALTY_USD

    @property
    def capacity_units(self) -> int:
        return int(round(self.tank_capacity_gal / self.fuel_unit_gal))

    @property
    def reserve_units(self) -> int:
        return int(round(self.reserve_gal / self.fuel_unit_gal))

    @property
    def margin_units(self) -> int:
        return self.reserve_units + self.safety_margin_units


def running_argmin(tmp: np.ndarray, run_min: np.ndarray) -> np.ndarray:
    """Return index of first position attaining the running minimum."""
    n = len(tmp)
    new_min = np.empty(n, dtype=bool)
    new_min[0] = True
    new_min[1:] = run_min[1:] < run_min[:-1]
    indices = np.arange(n, dtype=np.int32)
    return np.maximum.accumulate(np.where(new_min, indices, 0))


def build_fuel_nodes(
    candidates: list[CandidateStation],
    dest_mile: float,
    origin_price: float,
    cfg: OptimizerConfig,
    origin_station_info: dict | None = None,
) -> list[FuelNode]:
    """Construct snapped FuelNodes for origin, candidate stations, and destination."""
    unit_miles = cfg.fuel_unit_gal * cfg.mpg

    # 1. Snap positions to grid (ALGORITHM §7)
    def snap(mile: float) -> float:
        return math.ceil(mile / unit_miles) * unit_miles

    nodes: list[FuelNode] = []

    # Origin node (position 0, detour 0, price p0)
    orig_info = origin_station_info or {}
    nodes.append(
        FuelNode(
            index=0,
            snapped_mile=0.0,
            route_mile=0.0,
            price=origin_price,
            detour_miles=0.0,
            half_detour_units=0,
            gap_units_to_next=0,  # filled below
            is_origin=True,
            is_destination=False,
            station_id=orig_info.get("station_id", 0),
            opis_id=orig_info.get("opis_id", 0),
            name=orig_info.get("name", "Origin Station"),
            address=orig_info.get("address", ""),
            city=orig_info.get("city", ""),
            state=orig_info.get("state", ""),
            lat=orig_info.get("lat", 0.0),
            lon=orig_info.get("lon", 0.0),
            kind="origin_fill",
        )
    )

    # Station nodes sorted by (snapped_mile, price, station_id)
    cand_nodes: list[FuelNode] = []
    for c in candidates:
        s_mile = snap(c.route_mile)
        half_detour_gal = (c.detour_miles / 2.0) / cfg.mpg
        h_units = int(math.ceil(half_detour_gal / cfg.fuel_unit_gal))
        cand_nodes.append(
            FuelNode(
                index=0,
                snapped_mile=s_mile,
                route_mile=c.route_mile,
                price=c.price,
                detour_miles=c.detour_miles,
                half_detour_units=h_units,
                gap_units_to_next=0,
                is_origin=False,
                is_destination=False,
                station_id=c.station_id,
                opis_id=c.opis_id,
                lat=c.lat,
                lon=c.lon,
                kind="refuel",
            )
        )

    cand_nodes.sort(key=lambda n: (n.snapped_mile, n.price or 0.0, n.station_id or 0))
    nodes.extend(cand_nodes)

    # Destination node
    nodes.append(
        FuelNode(
            index=len(nodes),
            snapped_mile=snap(dest_mile),
            route_mile=dest_mile,
            price=None,
            detour_miles=0.0,
            half_detour_units=0,
            gap_units_to_next=0,
            is_origin=False,
            is_destination=True,
        )
    )

    # Compute gaps and index
    final_nodes: list[FuelNode] = []
    num_nodes = len(nodes)
    for i in range(num_nodes):
        curr = nodes[i]
        if i < num_nodes - 1:
            nxt = nodes[i + 1]
            gap_miles = nxt.snapped_mile - curr.snapped_mile
            gap_units = int(round(gap_miles / unit_miles))
        else:
            gap_units = 0

        final_nodes.append(
            FuelNode(
                index=i,
                snapped_mile=curr.snapped_mile,
                route_mile=curr.route_mile,
                price=curr.price,
                detour_miles=curr.detour_miles,
                half_detour_units=curr.half_detour_units,
                gap_units_to_next=gap_units,
                is_origin=curr.is_origin,
                is_destination=curr.is_destination,
                station_id=curr.station_id,
                opis_id=curr.opis_id,
                name=curr.name,
                address=curr.address,
                city=curr.city,
                state=curr.state,
                lat=curr.lat,
                lon=curr.lon,
                kind=curr.kind,
            )
        )

    return final_nodes


def find_largest_gap(nodes: list[FuelNode], capacity_miles: float) -> dict[str, float]:
    """Find the pair of nodes with the largest gap exceeding capacity."""
    max_gap = 0.0
    from_m = 0.0
    to_m = 0.0
    for i in range(len(nodes) - 1):
        gap = nodes[i + 1].route_mile - nodes[i].route_mile
        if gap > max_gap:
            max_gap = gap
            from_m = nodes[i].route_mile
            to_m = nodes[i + 1].route_mile

    return {
        "from_mile": round(from_m, 2),
        "to_mile": round(to_m, 2),
        "gap_miles": round(max_gap, 2),
    }


def optimize(
    nodes: list[FuelNode],
    dest_mile: float,
    cfg: OptimizerConfig,
    start_fuel_gal: float = START_FUEL_GAL,
    origin_price_source: str = "nearest_station",
) -> FuelPlan | InfeasibleResult:
    """Exact dynamic programming fuel optimizer conforming to ALGORITHM §6."""
    C = cfg.capacity_units
    m = cfg.margin_units
    delta = cfg.fuel_unit_gal
    INF = float("inf")

    # If start_fuel already covers the entire trip
    needed_fuel = dest_mile / cfg.mpg + (m * delta)
    if start_fuel_gal >= needed_fuel:
        fuel_consumed = dest_mile / cfg.mpg
        leftover = start_fuel_gal - fuel_consumed
        return FuelPlan(
            status="no_refuel_needed",
            origin_price_source=origin_price_source,
            stops=[],
            totals=PlanTotals(
                fuel_purchased_gal=0.0,
                fuel_consumed_gal=round(fuel_consumed, 2),
                total_fuel_cost_usd=0.0,
                avg_price_per_gal=0.0,
                cost_per_mile_usd=0.0,
                leftover_gal=round(leftover, 2),
                stops_count=0,
            ),
        )

    start_units = int(round(start_fuel_gal / delta))
    A = np.full(C + 1, INF)
    A[min(start_units, C)] = 0.0

    back: list[tuple[np.ndarray, np.ndarray]] = []
    g_idx = np.arange(C + 1)

    # Loop over all nodes except destination
    for node in nodes[:-1]:
        B = A.copy()
        visit_mask = np.zeros(C + 1, dtype=bool)
        arrive_g = np.zeros(C + 1, dtype=np.int32)

        if node.price is not None:
            h = node.half_detour_units
            pd = node.price * delta
            pen = 0.0 if node.is_origin else cfg.stop_penalty_usd

            a = np.full(C + 1, INF)
            if h <= C:
                a[: C + 1 - h] = A[h:] + pen

            g_min = 0 if node.is_origin else m
            a[:g_min] = INF

            tmp = a - pd * g_idx
            run_min = np.minimum.accumulate(tmp)
            arg = running_argmin(tmp, run_min)

            V = pd * g_idx + run_min
            q = np.arange(h, C + 1)
            cand = V[q]
            tgt = q - h

            better = cand < B[tgt] - 1e-12
            better_tgt = tgt[better]
            B[better_tgt] = cand[better]
            visit_mask[better_tgt] = True
            arrive_g[better_tgt] = arg[q[better]]

        back.append((visit_mask, arrive_g))

        # Drive transition to next node
        gap = node.gap_units_to_next
        A_next = np.full(C + 1, INF)
        ok = np.arange(C + 1) >= gap + m
        A_next[(np.arange(C + 1) - gap)[ok]] = B[ok]
        A = A_next

    # Check destination feasibility: min over f >= m
    valid_f = np.arange(C + 1) >= m
    cost_at_dest = np.where(valid_f, A, INF)
    min_cost = float(np.min(cost_at_dest))

    if math.isinf(min_cost):
        return InfeasibleResult(
            status="infeasible",
            largest_gap=find_largest_gap(nodes, cfg.tank_capacity_gal * cfg.mpg),
        )

    f_star = int(np.argmin(cost_at_dest))

    # Reconstruction (ALGORITHM §6.6)
    curr_f = f_star
    raw_stops: list[dict] = []
    num_station_nodes = len(nodes) - 1

    for i in range(num_station_nodes - 1, -1, -1):
        node = nodes[i]
        visit_mask, arrive_g = back[i]

        # Fuel level upon departing node i (after any visit/purchase)
        f_depart = curr_f + node.gap_units_to_next

        if visit_mask[f_depart]:
            h_i = node.half_detour_units
            q = f_depart + h_i
            g = int(arrive_g[f_depart])
            b = q - g
            gallons_bought = b * delta
            f_arrive = g + h_i

            if gallons_bought > 0:
                raw_stops.append(
                    {
                        "node": node,
                        "gallons_bought": gallons_bought,
                        "q_units": q,
                        "g_units": g,
                        "curr_f": f_depart,
                        "f_arrive": f_arrive,
                    }
                )
        else:
            f_arrive = f_depart

        curr_f = f_arrive

    # Build FuelStop objects in forward order
    raw_stops.reverse()
    stops: list[FuelStop] = []

    # Simulation along the route to compute exact fuel levels
    fuel_sim = start_fuel_gal
    curr_pos = 0.0

    for idx, item in enumerate(raw_stops, start=1):
        node = item["node"]
        gal_bought = item["gallons_bought"]
        dist_leg = node.route_mile - curr_pos
        fuel_sim -= dist_leg / cfg.mpg

        half_detour_gal = (node.detour_miles / 2.0) / cfg.mpg
        fuel_sim -= half_detour_gal
        arrival_gal = max(0.0, fuel_sim)

        fuel_sim += gal_bought
        after_purchase_gal = fuel_sim

        fuel_sim -= half_detour_gal
        after_depart_gal = max(0.0, fuel_sim)
        curr_pos = node.route_mile

        # Exact Decimal calculation for money boundary
        price_dec = Decimal(str(node.price))
        gal_dec = Decimal(str(round(gal_bought, 4)))
        cost_dec = (price_dec * gal_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        stops.append(
            FuelStop(
                stop_index=idx,
                kind=node.kind,
                station_id=node.station_id or 0,
                opis_id=node.opis_id or 0,
                name=node.name,
                address=node.address,
                city=node.city,
                state=node.state,
                lat=node.lat,
                lon=node.lon,
                route_mile=round(node.route_mile, 2),
                offset_miles=round(node.detour_miles / (2.0 * 1.3), 2),
                detour_miles=round(node.detour_miles, 2),
                price_per_gal=round(float(node.price), 4),
                gallons_bought=round(gal_bought, 2),
                cost_usd=float(cost_dec),
                fuel_after_arrival_gal=round(arrival_gal, 2),
                fuel_after_purchase_gal=round(after_purchase_gal, 2),
                fuel_after_depart_gal=round(after_depart_gal, 2),
            )
        )

    # Final drive to destination
    fuel_sim -= (dest_mile - curr_pos) / cfg.mpg
    leftover_gal = max(0.0, fuel_sim)

    total_cost = sum(s.cost_usd for s in stops)
    total_purchased = sum(s.gallons_bought for s in stops)
    detour_fuel_total = sum(s.detour_miles / cfg.mpg for s in stops)
    total_consumed = (dest_mile / cfg.mpg) + detour_fuel_total

    avg_price = (total_cost / total_purchased) if total_purchased > 0 else 0.0
    cost_per_mile = (total_cost / dest_mile) if dest_mile > 0 else 0.0

    totals = PlanTotals(
        fuel_purchased_gal=round(total_purchased, 2),
        fuel_consumed_gal=round(total_consumed, 2),
        total_fuel_cost_usd=round(total_cost, 2),
        avg_price_per_gal=round(avg_price, 4),
        cost_per_mile_usd=round(cost_per_mile, 4),
        leftover_gal=round(leftover_gal, 2),
        stops_count=len(stops),
    )

    return FuelPlan(
        status="ok",
        origin_price_source=origin_price_source,
        stops=stops,
        totals=totals,
    )
