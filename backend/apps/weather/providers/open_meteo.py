"""Open-Meteo weather provider and batched forecasting service.

Conforms to docs/ARCHITECTURE.md §6.5, docs/API_SPEC.md §4.2, and docs/PLAN.md T17.
Batched hourly weather forecasts for route samples with strict timeouts.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from django.conf import settings

from apps.common.constants import HTTP_TIMEOUT_WEATHER_SECONDS
from apps.geo.types import DrivingRoute
from apps.weather.interpret import aggregate_route_risk, interpret_sample_severity
from apps.weather.sampling import sample_route_for_weather
from apps.weather.types import RouteWeather, WeatherSample

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
METERS_TO_MILES = 0.000621371192237334


class OpenMeteoProvider:
    """Client for Open-Meteo batched hourly forecast API."""

    def __init__(self, base_url: str = OPEN_METEO_URL, app_contact: str | None = None) -> None:
        self.base_url = base_url
        self.app_contact = app_contact or getattr(settings, "APP_CONTACT", "")

    def fetch_forecasts_batched(
        self,
        points: list[tuple[float, float]],
    ) -> list[dict[str, Any]]:
        """Fetch hourly weather forecast for multiple coordinates in a single HTTP call.

        Open-Meteo accepts comma-separated lists of latitudes and longitudes.
        Returns a list of hourly forecast dicts matching the order of points.
        """
        if not points:
            return []

        lats_str = ",".join(f"{lat:.1f}" for lat, _ in points)
        lons_str = ",".join(f"{lon:.1f}" for _, lon in points)

        hourly_fields = (
            "temperature_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m,visibility"
        )
        params = {
            "latitude": lats_str,
            "longitude": lons_str,
            "hourly": hourly_fields,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "forecast_days": 16,
        }
        headers = {
            "User-Agent": f"FuelRoute/1.0 (+{self.app_contact})",
            "Accept": "application/json",
        }

        with httpx.Client(timeout=HTTP_TIMEOUT_WEATHER_SECONDS) as client:
            resp = client.get(self.base_url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning("Open-Meteo returned status HTTP %d", resp.status_code)
                raise RuntimeError(f"Open-Meteo HTTP {resp.status_code}")
            data = resp.json()

        if isinstance(data, dict):
            return [data]
        elif isinstance(data, list):
            return data
        else:
            raise RuntimeError("Unexpected Open-Meteo JSON structure")


class WeatherService:
    """Orchestrates route sampling, batched forecast retrieval, and interpretation."""

    def __init__(self, provider: OpenMeteoProvider | None = None) -> None:
        self.provider = provider or OpenMeteoProvider()

    def get_weather_for_routes(
        self,
        routes: list[DrivingRoute],
        departure_time: datetime | None = None,
    ) -> tuple[dict[str, RouteWeather], int]:
        """Fetch weather forecasts for all routes in exactly one external call.

        Returns:
            (route_weather_map, call_count)
            where route_weather_map is {route_id: RouteWeather}
        """
        if not routes:
            return {}, 0

        # 1. Sample all routes
        route_samples_map: dict[str, list[dict]] = {}
        unique_points_set: set[tuple[float, float]] = set()
        ordered_points: list[tuple[float, float]] = []

        for idx, r in enumerate(routes):
            r_id = f"r{idx + 1}"
            samples = sample_route_for_weather(r, departure_time=departure_time)
            route_samples_map[r_id] = samples
            for s in samples:
                pt = (round(float(s["lat"]), 1), round(float(s["lon"]), 1))
                if pt not in unique_points_set:
                    unique_points_set.add(pt)
                    ordered_points.append(pt)

        # 2. Batched query
        point_forecasts: dict[tuple[float, float], dict[str, Any]] = {}
        call_count = 0

        try:
            forecasts = self.provider.fetch_forecasts_batched(ordered_points)
            call_count = 1
            for pt, fcast in zip(ordered_points, forecasts, strict=False):
                point_forecasts[pt] = fcast
        except Exception as exc:
            logger.warning("Weather fetch failed; degrading to unavailable: %s", exc)
            # Graceful degradation per ARCHITECTURE §6.5
            return {
                f"r{idx + 1}": RouteWeather(
                    status="unavailable",
                    risk_level=None,
                    summary=None,
                    samples=[],
                )
                for idx in range(len(routes))
            }, call_count

        # 3. Interpret weather for each route's samples
        result_map: dict[str, RouteWeather] = {}

        for r_id, raw_samples in route_samples_map.items():
            processed_samples: list[WeatherSample] = []
            has_missing = False

            for s in raw_samples:
                pt = (round(float(s["lat"]), 1), round(float(s["lon"]), 1))
                fcast = point_forecasts.get(pt)
                hourly = fcast.get("hourly", {}) if fcast else {}

                time_list = hourly.get("time", [])
                eta_dt: datetime = s["eta_dt"]
                rounded_hour = eta_dt.replace(minute=0, second=0, microsecond=0) + (
                    timedelta(hours=1) if eta_dt.minute >= 30 else timedelta(0)
                )
                hour_iso = rounded_hour.strftime("%Y-%m-%dT%H:00")

                hour_idx = None
                if hour_iso in time_list:
                    hour_idx = time_list.index(hour_iso)
                elif time_list:
                    # Fallback to closest hour within available range
                    now_iso = (departure_time or datetime.now(UTC)).strftime("%Y-%m-%dT%H:00")
                    hour_idx = time_list.index(now_iso) if now_iso in time_list else 0

                if hour_idx is not None and hour_idx < len(hourly.get("temperature_2m", [])):
                    w_code = hourly.get("weather_code", [])[hour_idx]
                    t_f = hourly.get("temperature_2m", [])[hour_idx]
                    p_in = hourly.get("precipitation", [])[hour_idx]
                    w_mph = hourly.get("wind_speed_10m", [])[hour_idx]
                    g_mph = hourly.get("wind_gusts_10m", [])[hour_idx]
                    vis_m = hourly.get("visibility", [])[hour_idx]
                    vis_mi = round(vis_m * METERS_TO_MILES, 1) if vis_m is not None else None

                    cond, sev = interpret_sample_severity(
                        weather_code=w_code,
                        temperature_f=t_f,
                        precipitation_in=p_in,
                        wind_mph=w_mph,
                        gust_mph=g_mph,
                        visibility_mi=vis_mi,
                    )
                    processed_samples.append(
                        WeatherSample(
                            route_mile=s["route_mile"],
                            lat=s["lat"],
                            lon=s["lon"],
                            eta=s["eta"],
                            temperature_f=round(float(t_f), 1) if t_f is not None else None,
                            precipitation_in=round(float(p_in), 2) if p_in is not None else None,
                            wind_mph=round(float(w_mph), 1) if w_mph is not None else None,
                            gust_mph=round(float(g_mph), 1) if g_mph is not None else None,
                            visibility_mi=vis_mi,
                            weather_code=int(w_code) if w_code is not None else None,
                            condition=cond,
                            severity=sev,
                        )
                    )
                else:
                    has_missing = True

            risk_level, summary = aggregate_route_risk(processed_samples)
            status = "partial" if has_missing and processed_samples else "ok"
            if not processed_samples:
                status = "unavailable"
                risk_level = None
                summary = None

            result_map[r_id] = RouteWeather(
                status=status,
                risk_level=risk_level,
                summary=summary,
                samples=processed_samples,
            )

        return result_map, call_count
