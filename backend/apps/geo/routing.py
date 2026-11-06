"""OSRM Routing provider and RouteCache service.

Conforms to docs/ARCHITECTURE.md §3, §6.1, §6.6, docs/API_SPEC.md §3, and docs/PLAN.md T10.
"""

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
from django.conf import settings
from django.utils import timezone

from apps.common.constants import (
    HTTP_TIMEOUT_ROUTING_SECONDS,
    MIN_ROUTE_MILES,
    ROUTE_CACHE_TTL_SECONDS,
)
from apps.common.errors import ApiError, ApiErrorCode
from apps.geo.geometry import cumulative_distances, decode_polyline6, haversine_distance_miles
from apps.geo.models import RouteCache
from apps.geo.types import DrivingRoute

logger = logging.getLogger(__name__)

METERS_TO_MILES = 0.000621371192237334


def compute_route_cache_key(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    alternatives: bool,
    provider: str = "osrm",
    profile: str = "driving",
) -> str:
    """Compute sha256 cache key from rounded coordinates and routing parameters."""
    r_lat1 = round(lat1, 4)
    r_lon1 = round(lon1, 4)
    r_lat2 = round(lat2, 4)
    r_lon2 = round(lon2, 4)
    alt_str = "3" if alternatives else "false"
    key_raw = f"{provider}|{profile}|{alt_str}|{r_lat1},{r_lon1},{r_lat2},{r_lon2}"
    return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()


class OSRMRoutingProvider:
    """Client for OSRM driving routes."""

    def __init__(
        self,
        base_url: str | None = None,
        app_contact: str | None = None,
    ) -> None:
        self.base_url = (base_url or getattr(settings, "OSRM_BASE_URL", "")).rstrip("/")
        self.app_contact = app_contact or getattr(settings, "APP_CONTACT", "")

    def get_routes_raw(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        alternatives: bool = True,
    ) -> dict[str, Any]:
        """Query OSRM API for driving routes between coordinates."""
        # Check straight line minimum distance
        straight_dist = haversine_distance_miles(lat1, lon1, lat2, lon2)
        if straight_dist < MIN_ROUTE_MILES:
            raise ApiError(
                code=ApiErrorCode.ROUTE_TOO_SHORT,
                message="Start and destination must be at least 1 mile apart.",
                status_code=422,
                details={"straight_line_miles": round(float(straight_dist), 2)},
            )

        coords_str = f"{lon1:.5f},{lat1:.5f};{lon2:.5f},{lat2:.5f}"
        url = f"{self.base_url}/route/v1/driving/{coords_str}"
        alt_param = "3" if alternatives else "false"
        params = {
            "overview": "full",
            "geometries": "polyline6",
            "alternatives": alt_param,
            "steps": "false",
            "annotations": "false",
        }
        headers = {
            "User-Agent": f"FuelRoute/1.0 (+{self.app_contact})",
            "Accept": "application/json",
        }

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT_ROUTING_SECONDS) as client:
                response = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("OSRM routing timeout for coordinates %s", coords_str)
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_TIMEOUT,
                message="OSRM routing service timed out.",
                status_code=504,
                details={"provider": "osrm"},
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("OSRM routing request error: %s", exc)
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_UNAVAILABLE,
                message="OSRM routing service unreachable.",
                status_code=503,
                details={"provider": "osrm"},
            ) from exc

        if response.status_code in (429, 503):
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_UNAVAILABLE,
                message="OSRM routing service rate-limited or unavailable.",
                status_code=503,
                details={"provider": "osrm"},
            )
        if response.status_code != 200:
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message=f"OSRM returned unexpected status HTTP {response.status_code}.",
                status_code=502,
                details={"provider": "osrm"},
            )

        try:
            data = response.json()
        except Exception as exc:
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message="OSRM returned malformed JSON.",
                status_code=502,
                details={"provider": "osrm"},
            ) from exc

        code = data.get("code")
        if code == "NoRoute":
            raise ApiError(
                code=ApiErrorCode.ROUTE_NOT_FOUND,
                message="No drivable route found between these locations.",
                status_code=422,
                details={"osrm_code": "NoRoute"},
            )
        if code != "Ok":
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message=f"OSRM returned error code: {code}",
                status_code=502,
                details={"provider": "osrm", "osrm_code": code},
            )

        if not data.get("routes"):
            raise ApiError(
                code=ApiErrorCode.ROUTE_NOT_FOUND,
                message="No routes returned by routing provider.",
                status_code=422,
                details={"provider": "osrm"},
            )

        return data


class RoutingService:
    """Manages route caching and parses raw OSRM responses into DrivingRoute instances."""

    def __init__(
        self,
        provider: OSRMRoutingProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider or OSRMRoutingProvider()
        self.clock = clock or timezone.now

    def get_routes(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        alternatives: bool = True,
    ) -> list[DrivingRoute]:
        """Fetch and parse driving routes, using RouteCache when available."""
        # 0. Check minimum route distance
        straight_dist = haversine_distance_miles(lat1, lon1, lat2, lon2)
        if straight_dist < MIN_ROUTE_MILES:
            raise ApiError(
                code=ApiErrorCode.ROUTE_TOO_SHORT,
                message="Start and destination must be at least 1 mile apart.",
                status_code=422,
                details={"straight_line_miles": round(float(straight_dist), 2)},
            )

        key = compute_route_cache_key(lat1, lon1, lat2, lon2, alternatives)
        now = self.clock()

        # 1. Cache lookup
        cached = (
            RouteCache.objects.filter(key=key, expires_at__gt=now).order_by("-expires_at").first()
        )
        if cached is not None:
            raw_data = cached.raw_response
        else:
            # 2. Outbound OSRM call
            raw_data = self.provider.get_routes_raw(
                lat1, lon1, lat2, lon2, alternatives=alternatives
            )
            RouteCache.objects.update_or_create(
                key=key,
                defaults={
                    "raw_response": raw_data,
                    "provider": "osrm",
                    "expires_at": now + timedelta(seconds=ROUTE_CACHE_TTL_SECONDS),
                },
            )

        # 3. Parse routes
        raw_routes = raw_data.get("routes", [])
        parsed_routes: list[DrivingRoute] = []

        for idx, r in enumerate(raw_routes):
            dist_meters = float(r["distance"])
            dist_miles = dist_meters * METERS_TO_MILES
            duration_sec = float(r["duration"])
            geometry = str(r["geometry"])

            coords = decode_polyline6(geometry)
            cum = cumulative_distances(coords, target_total_miles=dist_miles)

            parsed_routes.append(
                DrivingRoute(
                    route_index=idx,
                    distance_miles=round(dist_miles, 2),
                    duration_seconds=round(duration_sec, 1),
                    geometry_polyline6=geometry,
                    coords=coords,
                    cum_miles=cum,
                )
            )

        return parsed_routes
