"""Independent plan validator.

Conforms to docs/ALGORITHM.md §6.7.
Pure Python without Django/ORM imports.
"""

from apps.common.constants import MPG, RESERVE_GAL, START_FUEL_GAL, TANK_CAPACITY_GAL
from apps.fuel.optimizer import OptimizerConfig
from apps.fuel.types import FuelPlan


def validate_plan(
    plan: FuelPlan,
    dest_mile: float,
    cfg: OptimizerConfig | None = None,
    start_fuel_gal: float = START_FUEL_GAL,
) -> tuple[bool, str]:
    """Re-simulate the fuel plan with exact float distances (unsnapped miles).

    Returns (True, "") if the plan is physically reachable and valid,
    or (False, error_message) describing the exact failure.
    """
    if plan.status == "infeasible":
        return True, ""

    mpg = cfg.mpg if cfg else MPG
    capacity = cfg.tank_capacity_gal if cfg else TANK_CAPACITY_GAL
    reserve = cfg.reserve_gal if cfg else RESERVE_GAL

    if plan.status == "no_refuel_needed":
        needed = dest_mile / mpg
        if start_fuel_gal - needed < reserve - 1e-9:
            return (
                False,
                f"Start fuel {start_fuel_gal:.2f} gal insufficient for {dest_mile:.2f} mi trip",
            )
        return True, ""

    fuel = start_fuel_gal
    pos = 0.0

    for i, stop in enumerate(plan.stops):
        # 1. Monotonic route progress
        if stop.route_mile < pos - 1e-9:
            return (
                False,
                f"Stop {i + 1} at mile {stop.route_mile:.2f} is behind vehicle position {pos:.2f}",
            )

        # 2. Drive to station approach along route
        dist_to_station = stop.route_mile - pos
        fuel -= dist_to_station / mpg

        # 3. Outbound half-detour to station
        half_detour_dist = stop.detour_miles / 2.0
        fuel -= half_detour_dist / mpg

        # Arrival at station must satisfy reserve requirement
        if fuel < reserve - 1e-9:
            return (
                False,
                f"Stop {i + 1} arrival fuel {fuel:.4f} gal is below reserve {reserve:.4f} gal",
            )

        # 4. Refuel at station
        if stop.gallons_bought < -1e-9:
            return False, f"Stop {i + 1} has negative purchase: {stop.gallons_bought:.4f} gal"

        fuel += stop.gallons_bought
        if fuel > capacity + 1e-9:
            return (
                False,
                f"Stop {i + 1} fuel {fuel:.4f} gal exceeds capacity {capacity:.4f} gal",
            )

        # 5. Inbound half-detour back to route
        fuel -= half_detour_dist / mpg
        if fuel < -1e-9:
            return (
                False,
                f"Stop {i + 1} return to route fuel {fuel:.4f} gal is negative",
            )

        pos = stop.route_mile

    # 6. Final drive to destination
    if dest_mile < pos - 1e-9:
        return False, f"Destination mile {dest_mile:.2f} is behind last stop {pos:.2f}"

    fuel -= (dest_mile - pos) / mpg
    if fuel < reserve - 1e-9:
        return (
            False,
            f"Destination arrival fuel {fuel:.4f} gal is below reserve {reserve:.4f} gal",
        )

    return True, ""
