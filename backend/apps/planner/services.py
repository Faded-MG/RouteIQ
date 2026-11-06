"""Planner orchestration service.

Conforms to docs/API_SPEC.md §4, §6 and docs/ALGORITHM.md §10.
Coordinates geocoding, routing, candidate matching, optimization, validation,
multi-route selection, ranking, and comparison.
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
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
from apps.planner.selection import EvaluatedRoute, select_and_rank_routes
from apps.stations.index import StationIndex, get_station_index
from apps.stations.models import Station
from apps.weather.providers.open_meteo import WeatherService


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
    weather_service: WeatherService | None = None,
    weather_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Orchestrate trip planning and return a dictionary conforming to PlanResponse."""
    t_start = time.perf_counter()
    options = options_data or {}
    start_fuel_gal = float(options.get("start_fuel_gal", 0.0))
    use_alternatives = bool(options.get("alternatives", True))

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
        alternatives=use_alternatives,
    )
    if not route_cached:
        external_calls["routing"] += 1
    cache_meta["route"] = "hit" if route_cached else "miss"
    t_route = int((time.perf_counter() - t_route_start) * 1000)

    if not use_alternatives and len(routes) > 1:
        routes = routes[:1]

    # 2b. Weather forecast (optional P1 extra, exactly 1 batched call for all routes)
    t_wx_start = time.perf_counter()
    include_weather = bool(options.get("include_weather", True))
    dep_str = options.get("departure_time")
    dep_dt = None
    if dep_str:
        try:
            dep_dt = datetime.fromisoformat(dep_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    wx_service = weather_service or WeatherService()
    weather_results: dict[str, dict[str, Any]] = {}

    if weather_overrides is not None:
        weather_results = weather_overrides
        cache_meta["weather"] = "miss"
    elif include_weather:
        route_weather_map, wx_calls = wx_service.get_weather_for_routes(
            routes, departure_time=dep_dt
        )
        external_calls["weather"] += wx_calls
        cache_meta["weather"] = "miss" if wx_calls > 0 else "unavailable"
        weather_results = {r_id: rw.to_dict() for r_id, rw in route_weather_map.items()}
    else:
        cache_meta["weather"] = "disabled"

    t_weather = int((time.perf_counter() - t_wx_start) * 1000)

    # 3. Origin price resolution (identical for all routes from this origin)
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

    # 4. Evaluate each route independently
    cfg = OptimizerConfig(
        mpg=MPG,
        tank_capacity_gal=TANK_CAPACITY_GAL,
        fuel_unit_gal=FUEL_UNIT_GAL,
        reserve_gal=RESERVE_GAL,
    )

    total_matching_time = 0.0
    total_opt_time = 0.0
    evaluated_raw_routes = []

    for r in routes:
        t_m0 = time.perf_counter()
        candidates = find_candidate_stations(r.coords, r.cum_miles, st_index)
        total_matching_time += time.perf_counter() - t_m0

        t_o0 = time.perf_counter()
        nodes = build_fuel_nodes(
            candidates=candidates,
            dest_mile=r.distance_miles,
            origin_price=origin_price,
            cfg=cfg,
            origin_station_info=origin_station_info,
        )
        fuel_plan_res = optimize(
            nodes=nodes,
            dest_mile=r.distance_miles,
            cfg=cfg,
            start_fuel_gal=start_fuel_gal,
            origin_price_source=origin_price_source,
        )

        if fuel_plan_res.status in ("ok", "no_refuel_needed"):
            ok, err = validate_plan(
                fuel_plan_res,
                r.distance_miles,
                cfg,
                start_fuel_gal,
            )
            if not ok:
                raise ApiError(
                    code=ApiErrorCode.INTERNAL_ERROR,
                    message=f"Optimizer produced unreachable plan: {err}",
                    status_code=500,
                )
        total_opt_time += time.perf_counter() - t_o0

        display_points = simplify_for_display(r.coords)
        display_coords = [
            [round(float(lon), 5), round(float(lat), 5)] for lat, lon in display_points
        ]

        evaluated_raw_routes.append((r, fuel_plan_res, display_coords))

    # 5. Check if ALL routes are infeasible
    has_feasible = any(
        not isinstance(fp, InfeasibleResult) and fp.status in ("ok", "no_refuel_needed")
        for _, fp, _ in evaluated_raw_routes
    )
    if not has_feasible:
        first_fp = evaluated_raw_routes[0][1]
        largest_gap = first_fp.largest_gap if isinstance(first_fp, InfeasibleResult) else {}
        raise ApiError(
            code=ApiErrorCode.NO_FEASIBLE_FUEL_PLAN,
            message="No refueling plan keeps the vehicle within a 500-mile range on this route.",
            status_code=422,
            details={"largest_gap": largest_gap},
        )

    # 6. Bulk fetch station details for all stops
    station_ids_in_stops = set()
    for _, fp, _ in evaluated_raw_routes:
        if not isinstance(fp, InfeasibleResult) and hasattr(fp, "stops"):
            for s in fp.stops:
                if s.station_id > 0:
                    station_ids_in_stops.add(s.station_id)

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

    # 7. Construct EvaluatedRoute objects
    evaluated_routes: list[EvaluatedRoute] = []
    for idx, (r, fp, display_coords) in enumerate(evaluated_raw_routes):
        route_id = f"r{idx + 1}"
        duration_min = r.duration_seconds / 60.0
        speed_mpm = (r.distance_miles / duration_min) if duration_min > 0 else 1.0

        if isinstance(fp, InfeasibleResult):
            formatted_fp = {
                "status": "infeasible",
                "origin_price_source": None,
                "stops": [],
                "totals": None,
                "infeasible": fp.largest_gap,
            }
        else:
            formatted_stops = []
            for s_idx, stop in enumerate(fp.stops, start=1):
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
                eta_min = (
                    0 if stop.kind == "origin_fill" else int(round(stop.route_mile / speed_mpm))
                )
                formatted_stops.append(
                    {
                        "sequence": s_idx,
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

            formatted_fp = {
                "status": fp.status,
                "origin_price_source": fp.origin_price_source,
                "stops": formatted_stops,
                "totals": {
                    "total_fuel_cost_usd": fp.totals.total_fuel_cost_usd,
                    "fuel_consumed_gal": fp.totals.fuel_consumed_gal,
                    "fuel_purchased_gal": fp.totals.fuel_purchased_gal,
                    "leftover_gal": fp.totals.leftover_gal,
                    "avg_price_per_gal": fp.totals.avg_price_per_gal,
                    "cost_per_mile_usd": fp.totals.cost_per_mile_usd,
                    "num_stops": len(formatted_stops),
                    "extra_detour_miles": round(sum(s.detour_miles for s in fp.stops), 2),
                },
            }

        weather_obj = weather_results.get(
            route_id,
            {
                "status": "disabled" if not include_weather else "unavailable",
                "risk_level": None,
                "summary": None,
                "samples": [],
            },
        )

        evaluated_routes.append(
            EvaluatedRoute(
                route_id=route_id,
                original_index=idx,
                distance_miles=r.distance_miles,
                duration_minutes=duration_min,
                display_coords=display_coords,
                fuel_plan_res=fp,
                formatted_fuel_plan=formatted_fp,
                weather=weather_obj,
            )
        )

    # 8. Selection and ranking
    selection = select_and_rank_routes(evaluated_routes)

    t_total = int((time.perf_counter() - t_start) * 1000)
    t_match = int(total_matching_time * 1000)
    t_opt = int(total_opt_time * 1000)

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
        "recommended_route_id": selection.recommended_route_id,
        "recommendation": {
            "reason": selection.reason,
            "considered": selection.considered_count,
            "discarded": selection.discarded,
        },
        "routes": selection.ranked_routes,
        "comparison": selection.comparison,
        "meta": {
            "external_calls": external_calls,
            "cache": cache_meta,
            "timings_ms": {
                "total": t_total,
                "geocode": t_geo,
                "routing": t_route,
                "matching": t_match,
                "optimization": t_opt,
                "weather": t_weather,
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
