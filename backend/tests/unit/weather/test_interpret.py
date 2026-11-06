"""Unit tests for WMO weather interpretation and route risk aggregation.

Conforms to docs/ARCHITECTURE.md §6.5 table requirements and docs/PLAN.md T17:
"every table row has a test".
"""

from apps.weather.interpret import aggregate_route_risk, interpret_sample_severity
from apps.weather.types import WeatherSample


def test_wmo_code_interpretation_table_rows():
    """Verify each condition and severity category in ARCHITECTURE §6.5."""
    # WMO 0–3 -> none
    for code in [0, 1, 2, 3]:
        cond, sev = interpret_sample_severity(code, 65.0, 0.0, 5.0, 10.0, 10.0)
        assert sev == "none"

    # WMO 45, 48 (fog) -> moderate
    for code in [45, 48]:
        cond, sev = interpret_sample_severity(code, 50.0, 0.0, 5.0, 10.0, 5.0)
        assert sev == "moderate"

    # WMO 51–55, 61, 63, 80, 81 -> low
    for code in [51, 53, 55, 61, 63, 80, 81]:
        cond, sev = interpret_sample_severity(code, 55.0, 0.05, 10.0, 15.0, 8.0)
        assert sev == "low"

    # WMO 65, 82 -> moderate
    for code in [65, 82]:
        cond, sev = interpret_sample_severity(code, 55.0, 0.20, 15.0, 20.0, 5.0)
        assert sev == "moderate"

    # WMO 71, 73, 85 -> moderate
    for code in [71, 73, 85]:
        cond, sev = interpret_sample_severity(code, 32.0, 0.10, 10.0, 15.0, 4.0)
        assert sev == "moderate"

    # WMO 56, 57, 66, 67, 75, 77, 86, 95, 96, 99 -> severe
    for code in [56, 57, 66, 67, 75, 77, 86, 95, 96, 99]:
        cond, sev = interpret_sample_severity(code, 30.0, 0.10, 15.0, 25.0, 3.0)
        assert sev == "severe"


def test_environmental_metric_triggers():
    """Verify visibility, precipitation, wind gusts, and freezing temp triggers."""
    # Visibility < 1 mi -> moderate (even with clear code 0)
    cond, sev = interpret_sample_severity(0, 60.0, 0.0, 5.0, 10.0, 0.8)
    assert sev == "moderate"

    # Precipitation >= 0.25 in/h -> moderate (even with slight rain code 61)
    cond, sev = interpret_sample_severity(61, 50.0, 0.30, 10.0, 15.0, 5.0)
    assert sev == "moderate"

    # Gusts >= 30 mph -> moderate
    cond, sev = interpret_sample_severity(0, 60.0, 0.0, 15.0, 35.0, 10.0)
    assert sev == "moderate"

    # Gusts >= 45 mph -> severe
    cond, sev = interpret_sample_severity(0, 60.0, 0.0, 25.0, 50.0, 10.0)
    assert sev == "severe"

    # Temp <= 28 F with precipitation > 0 -> severe
    cond, sev = interpret_sample_severity(61, 26.0, 0.05, 5.0, 10.0, 6.0)
    assert sev == "severe"


def test_aggregate_route_risk():
    """Verify route risk aggregation from multiple samples."""
    s_none = WeatherSample(
        route_mile=0.0,
        lat=40.0,
        lon=-74.0,
        eta="2026-11-06T12:00:00Z",
        temperature_f=55.0,
        precipitation_in=0.0,
        wind_mph=5.0,
        gust_mph=10.0,
        visibility_mi=10.0,
        weather_code=0,
        condition="Clear sky",
        severity="none",
    )
    s_low = WeatherSample(
        route_mile=100.0,
        lat=41.0,
        lon=-76.0,
        eta="2026-11-06T14:00:00Z",
        temperature_f=50.0,
        precipitation_in=0.05,
        wind_mph=10.0,
        gust_mph=15.0,
        visibility_mi=8.0,
        weather_code=61,
        condition="Slight rain",
        severity="low",
    )
    s_mod = WeatherSample(
        route_mile=200.0,
        lat=41.5,
        lon=-78.0,
        eta="2026-11-06T16:00:00Z",
        temperature_f=45.0,
        precipitation_in=0.30,
        wind_mph=15.0,
        gust_mph=35.0,
        visibility_mi=4.0,
        weather_code=65,
        condition="Heavy rain",
        severity="moderate",
    )
    s_sev = WeatherSample(
        route_mile=300.0,
        lat=42.0,
        lon=-80.0,
        eta="2026-11-06T18:00:00Z",
        temperature_f=25.0,
        precipitation_in=0.15,
        wind_mph=25.0,
        gust_mph=50.0,
        visibility_mi=1.0,
        weather_code=75,
        condition="Heavy snow fall",
        severity="severe",
    )

    # All none -> none
    risk, summary = aggregate_route_risk([s_none])
    assert risk == "none"
    assert "No significant weather" in summary

    # Has low -> low
    risk, summary = aggregate_route_risk([s_none, s_low])
    assert risk == "low"
    assert "Slight rain" in summary

    # Single moderate with precip >= 0.1 -> moderate
    risk, summary = aggregate_route_risk([s_none, s_mod])
    assert risk == "moderate"
    assert "Heavy rain" in summary

    # Any severe -> severe
    risk, summary = aggregate_route_risk([s_none, s_low, s_mod, s_sev])
    assert risk == "severe"
    assert "Heavy snow fall" in summary

