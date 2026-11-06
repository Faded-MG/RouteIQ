"""Geocoding service with Nominatim provider, cross-worker throttling, and caching.

Conforms to docs/ARCHITECTURE.md §5, §6.8 and docs/API_SPEC.md §3.
"""

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.common.constants import (
    GEOCODE_NEGATIVE_TTL_SECONDS,
    GEOCODE_TTL_SECONDS,
    HTTP_TIMEOUT_GEOCODING_SECONDS,
    NOMINATIM_MIN_INTERVAL_SECONDS,
    US_BBOX_MAX_LAT,
    US_BBOX_MAX_LON,
    US_BBOX_MIN_LAT,
    US_BBOX_MIN_LON,
)
from apps.common.errors import ApiError, ApiErrorCode
from apps.geo.models import GeocodeCache
from apps.geo.types import GeocodedLocation

logger = logging.getLogger(__name__)

NOMINATIM_ADVISORY_LOCK_ID = 84729104
THROTTLE_CACHE_KEY = "nominatim_next_available_ts"


def normalize_query(query: str) -> str:
    """Normalize location query: lowercase, trim, collapse whitespace, strip punctuation."""
    s = query.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


class NominatimProvider:
    """Client for OpenStreetMap Nominatim geocoding API conforming to usage policy."""

    def __init__(
        self,
        base_url: str | None = None,
        app_contact: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_url = (base_url or getattr(settings, "NOMINATIM_BASE_URL", "")).rstrip("/")
        self.app_contact = app_contact or getattr(settings, "APP_CONTACT", "")
        self.clock = clock or timezone.now

    def _acquire_scheduled_slot(self) -> float:
        """Reserve next available execution timestamp under advisory lock, sleep outside."""
        timeout_seconds = 3.0
        acquired = False

        # Attempt to acquire advisory lock within 3 seconds
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [NOMINATIM_ADVISORY_LOCK_ID])
            acquired = cursor.fetchone()[0]

            if not acquired:
                start_wait = time.monotonic()
                while time.monotonic() - start_wait < timeout_seconds:
                    time.sleep(0.05)
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", [NOMINATIM_ADVISORY_LOCK_ID])
                    if cursor.fetchone()[0]:
                        acquired = True
                        break

            if not acquired:
                raise ApiError(
                    code=ApiErrorCode.UPSTREAM_UNAVAILABLE,
                    message="Nominatim throttle lock timeout.",
                    status_code=503,
                    details={"provider": "nominatim"},
                )

            try:
                now_ts = time.time()
                last_reserved = cache.get(THROTTLE_CACHE_KEY, 0.0)
                next_available = max(now_ts, last_reserved + NOMINATIM_MIN_INTERVAL_SECONDS)
                cache.set(THROTTLE_CACHE_KEY, next_available, timeout=60)
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [NOMINATIM_ADVISORY_LOCK_ID])

        return next_available

    def geocode(self, query: str) -> dict[str, Any] | None:
        """Perform throttled HTTP request to Nominatim API."""
        next_ts = self._acquire_scheduled_slot()
        delay = next_ts - time.time()
        if delay > 0:
            time.sleep(delay)

        url = f"{self.base_url}/search"
        params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"}
        headers = {
            "User-Agent": f"FuelRoute/1.0 (+{self.app_contact})",
            "Accept": "application/json",
        }

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT_GEOCODING_SECONDS) as client:
                response = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("Nominatim geocoding timeout for query '%s'", query)
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_TIMEOUT,
                message="Nominatim geocoding service timed out.",
                status_code=504,
                details={"provider": "nominatim"},
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Nominatim geocoding request error: %s", exc)
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_UNAVAILABLE,
                message="Nominatim geocoding service unreachable.",
                status_code=503,
                details={"provider": "nominatim"},
            ) from exc

        if response.status_code in (429, 503):
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_UNAVAILABLE,
                message="Nominatim geocoding service rate-limited or unavailable.",
                status_code=503,
                details={"provider": "nominatim"},
            )
        if response.status_code != 200:
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message=f"Nominatim returned unexpected status HTTP {response.status_code}.",
                status_code=502,
                details={"provider": "nominatim"},
            )

        try:
            results = response.json()
        except Exception as exc:
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message="Nominatim returned malformed JSON.",
                status_code=502,
                details={"provider": "nominatim"},
            ) from exc

        if not isinstance(results, list):
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message="Nominatim response was not a JSON array.",
                status_code=502,
                details={"provider": "nominatim"},
            )

        return results[0] if results else None


class GeocodingService:
    """Service that manages query normalization, positive/negative caching, and geocoding."""

    def __init__(
        self,
        provider: NominatimProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.clock = clock or timezone.now
        self.provider = provider or NominatimProvider(clock=self.clock)

    def geocode(self, query: str, which: str = "location") -> GeocodedLocation:
        """Resolve a query string to a valid US location with caching."""
        loc, _ = self.geocode_with_meta(query, which=which)
        return loc

    def geocode_with_meta(
        self, query: str, which: str = "location"
    ) -> tuple[GeocodedLocation, bool]:
        """Resolve a query string, returning (location, is_cached)."""
        query_norm = normalize_query(query)
        if not query_norm:
            raise ApiError(
                code=ApiErrorCode.VALIDATION_ERROR,
                message="Location query cannot be empty.",
                status_code=400,
                details={"which": which},
            )

        now = self.clock()

        # 1. Cache lookup
        cached = (
            GeocodeCache.objects.filter(query_norm=query_norm, expires_at__gt=now)
            .order_by("-expires_at")
            .first()
        )
        if cached is not None:
            # Negative cache entry
            if cached.lat is None or cached.lon is None:
                raise ApiError(
                    code=ApiErrorCode.LOCATION_NOT_FOUND,
                    message=f"Location '{query}' could not be resolved.",
                    status_code=422,
                    details={"which": which, "query": query},
                )
            return (
                GeocodedLocation(
                    query=query,
                    query_norm=query_norm,
                    label=cached.label,
                    lat=cached.lat,
                    lon=cached.lon,
                ),
                True,
            )

        # 2. Provider call
        result = self.provider.geocode(query)

        # 3. Handle not found
        if not result:
            # Negative cache for 1 hour
            GeocodeCache.objects.update_or_create(
                query_norm=query_norm,
                defaults={
                    "label": "",
                    "lat": None,
                    "lon": None,
                    "provider": "nominatim",
                    "raw": None,
                    "expires_at": now + timedelta(seconds=GEOCODE_NEGATIVE_TTL_SECONDS),
                },
            )
            raise ApiError(
                code=ApiErrorCode.LOCATION_NOT_FOUND,
                message=f"Location '{query}' could not be resolved.",
                status_code=422,
                details={"which": which, "query": query},
            )

        try:
            lat = float(result["lat"])
            lon = float(result["lon"])
            label = str(result.get("display_name", query))
        except (KeyError, ValueError) as exc:
            raise ApiError(
                code=ApiErrorCode.UPSTREAM_BAD_RESPONSE,
                message="Nominatim result missing lat/lon coordinates.",
                status_code=502,
                details={"provider": "nominatim"},
            ) from exc

        # 4. Check contiguous US bounding box
        in_lat = US_BBOX_MIN_LAT <= lat <= US_BBOX_MAX_LAT
        in_lon = US_BBOX_MIN_LON <= lon <= US_BBOX_MAX_LON
        if not (in_lat and in_lon):
            # Negative cache
            GeocodeCache.objects.update_or_create(
                query_norm=query_norm,
                defaults={
                    "label": label,
                    "lat": None,
                    "lon": None,
                    "provider": "nominatim",
                    "raw": result,
                    "expires_at": now + timedelta(seconds=GEOCODE_NEGATIVE_TTL_SECONDS),
                },
            )
            raise ApiError(
                code=ApiErrorCode.LOCATION_OUTSIDE_US,
                message=f"Location '{query}' ({lat:.4f}, {lon:.4f}) is outside the contiguous US.",
                status_code=422,
                details={"which": which, "query": query, "lat": lat, "lon": lon},
            )

        # 5. Positive cache for 30 days
        GeocodeCache.objects.update_or_create(
            query_norm=query_norm,
            defaults={
                "label": label,
                "lat": lat,
                "lon": lon,
                "provider": "nominatim",
                "raw": result,
                "expires_at": now + timedelta(seconds=GEOCODE_TTL_SECONDS),
            },
        )

        return (
            GeocodedLocation(
                query=query,
                query_norm=query_norm,
                label=label,
                lat=lat,
                lon=lon,
            ),
            False,
        )
