"""Weather domain types.

Conforms to docs/ARCHITECTURE.md §6.5 and docs/API_SPEC.md §4.2.
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class WeatherSample:
    """Weather sample at a specific route mile and ETA."""

    route_mile: float
    lat: float
    lon: float
    eta: str
    temperature_f: float | None
    precipitation_in: float | None
    wind_mph: float | None
    gust_mph: float | None
    visibility_mi: float | None
    weather_code: int | None
    condition: str
    severity: str  # "none" | "low" | "moderate" | "severe"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteWeather:
    """Weather assessment for a complete driving route."""

    status: str  # "ok" | "partial" | "unavailable" | "disabled"
    risk_level: str | None  # "none" | "low" | "moderate" | "severe" | None
    summary: str | None
    samples: list[WeatherSample]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "samples": [s.to_dict() for s in self.samples],
        }

