"""Planner orchestration service.

Conforms to docs/API_SPEC.md §4, §6 and docs/ALGORITHM.md §10.
Coordinates geocoding, routing, candidate matching, optimization, and validation.
"""

import time
from dataclasses import dataclass
from uuid import uuid4

import numpy as np

from apps.common.constants import (
    CIRCUITY_FACTOR,
    FUEL_UNIT_GAL,
    MAX_RANGE_MILES,
    MPG,
    ORIGIN_SNAP_MILES,
    RESERVE_GAL,
    STATION_CORRIDOR_MILES,
    TANK_CAPACITY_GAL,
)
from apps.common.errors import ApiError, ApiErrorCode
from apps.fuel.candidates import find_candidate_stations
from apps.fuel.optimizer import OptimizerConfig, build_fuel_nodes, optimize
from apps.fuel.types import InfeasibleResult
from apps.fuel.validator import validate_plan
from apps.geo.geocoding import GeocodingService
from apps.geo.geometry import (
    haversine_distance_miles,
    simplify_for_display,
)
from apps.geo.routing import RoutingService
from apps.stations.index import StationIndex, get_station_index
from apps.stations.models import Station


@dataclass(frozen=True)
class ResolvedLocation:
    label: str
    lat: float
    lon: float
    source: str
    cached: bool


def plan_trip(
    start_data: dict,
    finish_data: dict,
    options_data: dict | None = None,
    geocoding_service: GeocodingService | None = None,
    routing_service: RoutingService | None = None,
    station_index: StationIndex | None = None,
) -> dict:
    """Orchestrate trip planning and return a dictionary conforming to PlanResponse."""
    t_start = time.perf_counter()
    options = options_data or {}
    start_fuel_gal = float(options.get("start_fuel_gal", 0.0))

    geo_service = geocoding_service or GeocodingService()
    route_service = routing_service or RoutingService()
    st_index = station_index or get_station_index()

    # Track metrics
    external_calls = {"geocoding": 0, "routing": 0, "weather": 0}
    cache_meta = {"plan": "miss", "geocode": [], "route": "miss", "weather": "disabled"}

    # 1. Geocode start and finish
    t_geo_start = time.perf_counter()

    def resolve_location(loc_dict: dict, which: str) -> ResolvedLocation:
        if "query" in loc_dict:
            res, is_cached = geo_service.geocode_with_meta(loc_dict["query"], which=which)
            if not is_cached:
                external_calls["geocoding"] += 1
            cache_meta["geocode"].append("hit" if is_cached else "miss")
            return ResolvedLocation(
                label=res.label,
                lat=res.lat,
                lon=res.lon,
                source="geocoded",
                cached=is_cached,
            )
        else:
            lat = float(loc_dict["lat"])
            lon = float(loc_dict["lon"])
            cache_meta["geocode"].append("miss")
            return ResolvedLocation(
                label=f"{lat:.4f}, {lon:.4f}",
                lat=lat,
                lon=lon,
                source="coordinates",
                cached=False,
            )

    start_res = resolve_location(start_data, "start")
    finish_res = resolve_location(finish_data, "finish")
    t_geo = int((time.perf_counter() - t_geo_start) * 1000)

    # Validate distance between start and finish
    straight_dist = haversine_distance_miles(
        start_res.lat, start_res.lon, finish_res.lat, finish_res.lon
    )
    if straight_dist < 1.0:
        raise ApiError(
            code=ApiErrorCode.ROUTE_TOO_SHORT,
            message="Start and finish locations must be at least 1 mile apart.",
            status_code=422,
        )

    # 2. Routing
    t_route_start = time.perf_counter()
    routes, route_cached = route_service.get_routes_with_meta(
        start_res.lat,
        start_res.lon,
        finish_res.lat,
        finish_res.lon,
    )
    if not route_cached:
        external_calls["routing"] += 1
    cache_meta["route"] = "hit" if route_cached else "miss"
    t_route = int((time.perf_counter() - t_route_start) * 1000)

    # For P0: evaluate the first route (or all returned routes)
    # Take first route as primary/recommended
    primary_route = routes[0]

    # 3. Candidate stations matching
    t_match_start = time.perf_counter()
    candidates = find_candidate_stations(
        primary_route.coords,
        primary_route.cum_miles,
        st_index,
    )
    t_match = int((time.perf_counter() - t_match_start) * 1000)

    # 4. Origin price resolution
    # Find nearest station to origin in StationIndex
    d_lat = np.radians(st_index.lat - start_res.lat)
    d_lon = np.radians(st_index.lon - start_res.lon)
    a = (
        np.sin(d_lat / 2.0) ** 2
        + np.cos(np.radians(start_res.lat))
        * np.cos(np.radians(st_index.lat))
        * np.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))
    dists_to_start = 3958.7613 * c

    min_idx = int(np.argmin(dists_to_start))
    nearest_dist = float(dists_to_start[min_idx])

    origin_station_info = None
    if nearest_dist <= ORIGIN_SNAP_MILES:
        nearest_station_id = int(st_index.id[min_idx])
        origin_price = float(st_index.price[min_idx])
        origin_price_source = "nearest_station"

        st_obj = Station.objects.filter(id=nearest_station_id).first()
        if st_obj:
            origin_station_info = {
                "station_id": st_obj.id,
                "opis_id": st_obj.opis_id,
                "name": st_obj.name,
                "address": st_obj.address,
                "city": st_obj.city,
                "state": st_obj.state,
                "lat": st_obj.lat,
                "lon": st_obj.lon,
            }
    else:
        origin_price = st_index.national_median
        origin_price_source = "state_median"

    # 5. Optimization & Validation
    t_opt_start = time.perf_counter()
    cfg = OptimizerConfig(
        mpg=MPG,
        tank_capacity_gal=TANK_CAPACITY_GAL,
        fuel_unit_gal=FUEL_UNIT_GAL,
        reserve_gal=RESERVE_GAL,
    )

    nodes = build_fuel_nodes(
        candidates=candidates,
        dest_mile=primary_route.distance_miles,
        origin_price=origin_price,
        cfg=cfg,
        origin_station_info=origin_station_info,
    )

    fuel_plan_res = optimize(
        nodes=nodes,
        dest_mile=primary_route.distance_miles,
        cfg=cfg,
        start_fuel_gal=start_fuel_gal,
        origin_price_source=origin_price_source,
    )

    # 6. Validate Plan
    if fuel_plan_res.status in ("ok", "no_refuel_needed"):
        ok, err = validate_plan(
            fuel_plan_res,
            primary_route.distance_miles,
            cfg,
            start_fuel_gal,
        )
        if not ok:
            raise ApiError(
                code=ApiErrorCode.INTERNAL_ERROR,
                message=f"Optimizer produced unreachable plan: {err}",
                status_code=500,
            )
    t_opt = int((time.perf_counter() - t_opt_start) * 1000)

    # 7. Format Output
    duration_min = primary_route.duration_seconds / 60.0
    display_points = simplify_for_display(primary_route.coords)
    display_coords = [[round(float(lon), 5), round(float(lat), 5)] for lat, lon in display_points]

    if isinstance(fuel_plan_res, InfeasibleResult):
        raise ApiError(
            code=ApiErrorCode.NO_FEASIBLE_FUEL_PLAN,
            message="No refueling plan keeps the vehicle within a 500-mile range on this route.",
            status_code=422,
            details={"largest_gap": fuel_plan_res.largest_gap},
        )

    # Fetch station details in bulk for stops
    station_ids_in_stops = [s.station_id for s in fuel_plan_res.stops if s.station_id > 0]
    station_map = {}
    if station_ids_in_stops:
        for st in Station.objects.filter(id__in=station_ids_in_stops):
            station_map[st.id] = {
                "id": st.id,
                "opis_id": st.opis_id,
                "name": st.name,
                "address": st.address,
                "city": st.city,
                "state": st.state,
                "lat": st.lat,
                "lon": st.lon,
                "position_precision": "place_centroid",
            }

    formatted_stops = []
    speed_mpm = (primary_route.distance_miles / duration_min) if duration_min > 0 else 1.0

    for idx, stop in enumerate(fuel_plan_res.stops, start=1):
        st_info = station_map.get(
            stop.station_id,
            {
                "id": stop.station_id,
                "opis_id": stop.opis_id,
                "name": stop.name,
                "address": stop.address,
                "city": stop.city,
                "state": stop.state,
                "lat": stop.lat,
                "lon": stop.lon,
                "position_precision": "place_centroid",
            },
        )
        eta_min = 0 if stop.kind == "origin_fill" else int(round(stop.route_mile / speed_mpm))

        formatted_stops.append(
            {
                "sequence": idx,
                "kind": "origin_fill" if stop.kind == "origin_fill" else "en_route",
                "station": st_info,
                "route_mile": stop.route_mile,
                "offset_miles": stop.offset_miles,
                "detour_miles": stop.detour_miles,
                "arrival_fuel_gal": stop.fuel_after_arrival_gal,
                "gallons_bought": stop.gallons_bought,
                "price_per_gal": stop.price_per_gal,
                "cost_usd": stop.cost_usd,
                "fuel_after_gal": stop.fuel_after_depart_gal,
                "eta_minutes_from_start": eta_min,
            }
        )

    formatted_fuel_plan = {
        "status": fuel_plan_res.status,
        "origin_price_source": fuel_plan_res.origin_price_source,
        "stops": formatted_stops,
        "totals": {
            "total_fuel_cost_usd": fuel_plan_res.totals.total_fuel_cost_usd,
            "fuel_consumed_gal": fuel_plan_res.totals.fuel_consumed_gal,
            "fuel_purchased_gal": fuel_plan_res.totals.fuel_purchased_gal,
            "leftover_gal": fuel_plan_res.totals.leftover_gal,
            "avg_price_per_gal": fuel_plan_res.totals.avg_price_per_gal,
            "cost_per_mile_usd": fuel_plan_res.totals.cost_per_mile_usd,
            "num_stops": len(formatted_stops),
            "extra_detour_miles": round(sum(s.detour_miles for s in fuel_plan_res.stops), 2),
        },
    }
    total_cost_usd = fuel_plan_res.totals.total_fuel_cost_usd
    avg_price = fuel_plan_res.totals.avg_price_per_gal
    rec_reason = "lowest_cost"
    discarded_routes = []

    route_obj = {
        "id": "r1",
        "rank": 1,
        "is_recommended": True,
        "summary": {
            "distance_miles": round(primary_route.distance_miles, 1),
            "duration_minutes": int(round(duration_min)),
        },
        "geometry": {
            "type": "LineString",
            "coordinates": display_coords,
        },
        "fuel_plan": formatted_fuel_plan,
        "weather": {
            "status": "disabled",
            "risk_level": None,
            "summary": None,
            "samples": [],
        },
    }

    comparison_row = {
        "route_id": "r1",
        "distance_miles": round(primary_route.distance_miles, 1),
        "duration_minutes": int(round(duration_min)),
        "total_fuel_cost_usd": total_cost_usd,
        "num_stops": len(formatted_stops),
        "avg_price_per_gal": avg_price,
        "weather_risk": None,
        "cost_delta_vs_recommended_usd": 0.00,
        "duration_delta_minutes": 0,
    }

    t_total = int((time.perf_counter() - t_start) * 1000)

    return {
        "request_id": str(uuid4()),
        "status": "ok",
        "assumptions": {
            "mpg": MPG,
            "max_range_miles": MAX_RANGE_MILES,
            "tank_capacity_gal": TANK_CAPACITY_GAL,
            "start_fuel_gal": start_fuel_gal,
            "reserve_gal": RESERVE_GAL,
            "station_corridor_miles": STATION_CORRIDOR_MILES,
            "circuity_factor": CIRCUITY_FACTOR,
            "fuel_unit_gal": FUEL_UNIT_GAL,
            "leftover_fuel_value_usd": 0,
        },
        "start": {
            "label": start_res.label,
            "lat": start_res.lat,
            "lon": start_res.lon,
            "source": start_res.source,
            "cached": start_res.cached,
        },
        "finish": {
            "label": finish_res.label,
            "lat": finish_res.lat,
            "lon": finish_res.lon,
            "source": finish_res.source,
            "cached": finish_res.cached,
        },
        "recommended_route_id": "r1",
        "recommendation": {
            "reason": rec_reason,
            "considered": 1,
            "discarded": discarded_routes,
        },
        "routes": [route_obj],
        "comparison": [comparison_row],
        "meta": {
            "external_calls": external_calls,
            "cache": cache_meta,
            "timings_ms": {
                "total": t_total,
                "geocode": t_geo,
                "routing": t_route,
                "matching": t_match,
                "optimization": t_opt,
                "weather": 0,
            },
            "data": {
                "station_count": len(st_index),
                "stations_data_version": st_index.data_version,
                "station_position_precision": "place_centroid",
                "price_aggregation": "median",
            },
            "attribution": [
                "Routing © OSRM contributors, data © OpenStreetMap contributors (ODbL)",
                "Geocoding © OpenStreetMap contributors",
                "Weather data by Open-Meteo.com (CC BY 4.0)",
            ],
        },
    }
