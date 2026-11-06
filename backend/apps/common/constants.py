"""Constants and assumptions normative across all apps.

Source of truth: docs/ALGORITHM.md §2 and docs/ARCHITECTURE.md.
No magic numbers in other modules.
"""

# Vehicle & Assessment Parameters
MPG: float = 10.0
MAX_RANGE_MILES: float = 500.0
TANK_CAPACITY_GAL: float = 50.0
START_FUEL_GAL: float = 0.0
RESERVE_GAL: float = 0.0

# Optimizer Grid & Tuning Parameters
FUEL_UNIT_GAL: float = 0.01
SAFETY_MARGIN_UNITS: int = 1
STATION_CORRIDOR_MILES: float = 10.0
CIRCUITY_FACTOR: float = 1.3
ORIGIN_SNAP_MILES: float = 25.0
STOP_PENALTY_USD: float = 0.005
PRICE_AGGREGATION: str = "median"
MAX_CANDIDATES: int = 1500
MAX_DURATION_RATIO: float = 1.25

# Derived Parameters
RESERVE_UNITS: int = round(RESERVE_GAL / FUEL_UNIT_GAL)

# Operational & Provider Constants
GEOCODE_TTL_SECONDS: int = 30 * 86400  # 30 days
GEOCODE_NEGATIVE_TTL_SECONDS: int = 3600  # 1 hour
ROUTE_CACHE_TTL_SECONDS: int = 86400  # 24 hours
WEATHER_CACHE_TTL_SECONDS: int = 3600  # 1 hour
PLAN_CACHE_TTL_SECONDS: int = 3600  # 1 hour

NOMINATIM_MIN_INTERVAL_SECONDS: float = 1.05
HTTP_TIMEOUT_GEOCODING_SECONDS: float = 5.0
HTTP_TIMEOUT_ROUTING_SECONDS: float = 8.0
HTTP_TIMEOUT_WEATHER_SECONDS: float = 3.0

WEATHER_SAMPLE_SPACING_MILES: float = 100.0
WEATHER_MAX_SAMPLES_PER_ROUTE: int = 12

DISPLAY_GEOMETRY_MAX_POINTS: int = 2000
SIMPLIFICATION_TOLERANCE_MATCHING_MILES: float = 0.05
SIMPLIFICATION_TOLERANCE_DISPLAY_MILES: float = 0.25

# Geographic Bounds (Contiguous US)
US_BBOX_MIN_LAT: float = 24.0
US_BBOX_MAX_LAT: float = 49.5
US_BBOX_MIN_LON: float = -125.0
US_BBOX_MAX_LON: float = -66.5

MIN_ROUTE_MILES: float = 1.0
EARTH_RADIUS_MILES: float = 3958.7613
