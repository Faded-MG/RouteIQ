"""Serializers for request validation and response formatting.

Conforms to docs/API_SPEC.md §4 and §6.
"""

import re
from datetime import UTC, datetime

from rest_framework import serializers

from apps.common.constants import (
    CIRCUITY_FACTOR,
    FUEL_UNIT_GAL,
    MAX_RANGE_MILES,
    MPG,
    RESERVE_GAL,
    STATION_CORRIDOR_MILES,
    TANK_CAPACITY_GAL,
    US_BBOX_MAX_LAT,
    US_BBOX_MAX_LON,
    US_BBOX_MIN_LAT,
    US_BBOX_MIN_LON,
)


class StrictSerializer(serializers.Serializer):
    """Serializer that rejects any unknown keys."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected a dictionary.")
        unknown = set(data.keys()) - set(self.fields.keys())
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class LocationInputSerializer(StrictSerializer):
    """Location input accepting either query string or lat/lon coordinates."""

    query = serializers.CharField(
        required=False,
        min_length=3,
        max_length=200,
        trim_whitespace=True,
    )
    lat = serializers.FloatField(
        required=False,
        min_value=US_BBOX_MIN_LAT,
        max_value=US_BBOX_MAX_LAT,
    )
    lon = serializers.FloatField(
        required=False,
        min_value=US_BBOX_MIN_LON,
        max_value=US_BBOX_MAX_LON,
    )

    def validate_query(self, value):
        if "\x00" in value:
            raise serializers.ValidationError("Null bytes are not allowed in query.")
        return value

    def validate(self, attrs):
        has_query = "query" in attrs and attrs["query"]
        has_lat = "lat" in attrs and attrs["lat"] is not None
        has_lon = "lon" in attrs and attrs["lon"] is not None

        if has_query and (has_lat or has_lon):
            raise serializers.ValidationError(
                "Provide either 'query' or 'lat' and 'lon', not both."
            )

        if not has_query and not (has_lat and has_lon):
            raise serializers.ValidationError(
                "Must provide either 'query' or both 'lat' and 'lon'."
            )

        return attrs


class OptionsInputSerializer(StrictSerializer):
    """Optional tuning parameters for trip planning."""

    start_fuel_gal = serializers.FloatField(
        required=False,
        default=0.0,
        min_value=0.0,
        max_value=TANK_CAPACITY_GAL,
    )
    departure_time = serializers.CharField(
        required=False,
        default=None,
    )
    include_weather = serializers.BooleanField(
        required=False,
        default=True,
    )
    alternatives = serializers.BooleanField(
        required=False,
        default=True,
    )

    def validate_departure_time(self, value):
        if not value:
            return None

        # Parse ISO-8601 with timezone
        try:
            # Handle trailing Z
            iso_str = re.sub(r"Z$", "+00:00", value)
            dt = datetime.fromisoformat(iso_str)
        except (ValueError, TypeError) as exc:
            raise serializers.ValidationError(
                "departure_time must be a valid ISO-8601 datetime string with timezone."
            ) from exc

        if dt.tzinfo is None:
            raise serializers.ValidationError("departure_time must include timezone offset.")

        now = datetime.now(UTC)
        diff_seconds = (dt - now).total_seconds()

        # Between now - 1h and now + 14d
        if diff_seconds < -3600:
            raise serializers.ValidationError(
                "departure_time cannot be more than 1 hour in the past."
            )
        if diff_seconds > 14 * 86400:
            raise serializers.ValidationError(
                "departure_time cannot be more than 14 days in the future."
            )

        return dt.isoformat()


class PlanRequestSerializer(StrictSerializer):
    """Root plan request serializer."""

    start = LocationInputSerializer(required=True)
    finish = LocationInputSerializer(required=True)
    options = OptionsInputSerializer(required=False, default=dict)


# ---------------------------------------------------------------------------
# Response Serializers (used for contract verification and schema enforcement)
# ---------------------------------------------------------------------------


class LocationResponseSerializer(serializers.Serializer):
    label = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    source = serializers.ChoiceField(choices=["geocoded", "coordinates"])
    cached = serializers.BooleanField()


class StationResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    opis_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField(allow_blank=True)
    city = serializers.CharField()
    state = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    position_precision = serializers.CharField()


class StopResponseSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["origin_fill", "en_route"])
    station = StationResponseSerializer()
    route_mile = serializers.FloatField()
    offset_miles = serializers.FloatField()
    detour_miles = serializers.FloatField()
    arrival_fuel_gal = serializers.FloatField()
    gallons_bought = serializers.FloatField()
    price_per_gal = serializers.FloatField()
    cost_usd = serializers.FloatField()
    fuel_after_gal = serializers.FloatField()
    eta_minutes_from_start = serializers.IntegerField()


class PlanTotalsSerializer(serializers.Serializer):
    total_fuel_cost_usd = serializers.FloatField()
    fuel_consumed_gal = serializers.FloatField()
    fuel_purchased_gal = serializers.FloatField()
    leftover_gal = serializers.FloatField()
    avg_price_per_gal = serializers.FloatField()
    cost_per_mile_usd = serializers.FloatField()
    num_stops = serializers.IntegerField()
    extra_detour_miles = serializers.FloatField()


class InfeasibleDetailSerializer(serializers.Serializer):
    from_mile = serializers.FloatField()
    to_mile = serializers.FloatField()
    gap_miles = serializers.FloatField()


class FuelPlanResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "no_refuel_needed", "infeasible"])
    origin_price_source = serializers.CharField(allow_null=True)
    stops = StopResponseSerializer(many=True)
    totals = PlanTotalsSerializer(required=False, allow_null=True)
    infeasible = InfeasibleDetailSerializer(required=False, allow_null=True)


class WeatherResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "partial", "unavailable", "disabled"])
    risk_level = serializers.CharField(allow_null=True)
    summary = serializers.CharField(allow_null=True)
    samples = serializers.ListField(child=serializers.DictField())


class RouteResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    rank = serializers.IntegerField()
    is_recommended = serializers.BooleanField()
    summary = serializers.DictField()
    geometry = serializers.DictField()
    fuel_plan = FuelPlanResponseSerializer()
    weather = WeatherResponseSerializer()


class ComparisonRowSerializer(serializers.Serializer):
    route_id = serializers.CharField()
    distance_miles = serializers.FloatField()
    duration_minutes = serializers.IntegerField()
    total_fuel_cost_usd = serializers.FloatField(allow_null=True)
    num_stops = serializers.IntegerField()
    avg_price_per_gal = serializers.FloatField(allow_null=True)
    weather_risk = serializers.CharField(allow_null=True)
    cost_delta_vs_recommended_usd = serializers.FloatField(allow_null=True)
    duration_delta_minutes = serializers.IntegerField()


class MetaSerializer(serializers.Serializer):
    external_calls = serializers.DictField()
    cache = serializers.DictField()
    timings_ms = serializers.DictField()
    data = serializers.DictField()
    attribution = serializers.ListField(child=serializers.CharField())


class AssumptionsSerializer(serializers.Serializer):
    mpg = serializers.FloatField(default=MPG)
    max_range_miles = serializers.FloatField(default=MAX_RANGE_MILES)
    tank_capacity_gal = serializers.FloatField(default=TANK_CAPACITY_GAL)
    start_fuel_gal = serializers.FloatField()
    reserve_gal = serializers.FloatField(default=RESERVE_GAL)
    station_corridor_miles = serializers.FloatField(default=STATION_CORRIDOR_MILES)
    circuity_factor = serializers.FloatField(default=CIRCUITY_FACTOR)
    fuel_unit_gal = serializers.FloatField(default=FUEL_UNIT_GAL)
    leftover_fuel_value_usd = serializers.IntegerField(default=0)


class PlanResponseSerializer(serializers.Serializer):
    """Full PlanResponse serializer confirming to API_SPEC §4.2."""

    request_id = serializers.CharField()
    status = serializers.CharField()
    assumptions = AssumptionsSerializer()
    start = LocationResponseSerializer()
    finish = LocationResponseSerializer()
    recommended_route_id = serializers.CharField()
    recommendation = serializers.DictField()
    routes = RouteResponseSerializer(many=True)
    comparison = ComparisonRowSerializer(many=True)
    meta = MetaSerializer()
