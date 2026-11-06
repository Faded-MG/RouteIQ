"""API tests for weather integration and failure degradation.

Conforms to docs/PLAN.md T17 and docs/TESTING.md §9 AT-10:
"AT-10 | Open-Meteo times out | 200, weather.status='unavailable', plan unchanged, plan not cached."
"""

import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.planner.serializers import PlanResponseSerializer

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def api_client():
    return APIClient()


def test_plan_with_weather_success(api_client, respx_mock):
    """POST /routes/plan with include_weather=true returns weather samples and status=ok."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    mock_hourly = {
        "time": ["2026-11-06T12:00", "2026-11-06T13:00", "2026-11-06T14:00"],
        "temperature_2m": [60.0, 58.0, 55.0],
        "precipitation": [0.0, 0.0, 0.0],
        "weather_code": [0, 1, 2],
        "wind_speed_10m": [8.0, 10.0, 12.0],
        "wind_gusts_10m": [15.0, 18.0, 22.0],
        "visibility": [16000.0, 16000.0, 16000.0],
    }
    respx_mock.get(url__regex=r"https://api\.open-meteo\.com/v1/forecast.*").respond(
        200, json=[{"hourly": mock_hourly}] * 30
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"include_weather": True, "alternatives": True},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    # Verify schema
    serializer = PlanResponseSerializer(data=data)
    assert serializer.is_valid(), f"Schema error: {serializer.errors}"

    assert data["meta"]["external_calls"]["weather"] == 1
    assert len(data["routes"]) >= 1

    primary = data["routes"][0]
    assert primary["weather"]["status"] in ("ok", "partial")
    assert primary["weather"]["risk_level"] in ("none", "low", "moderate", "severe")
    assert len(primary["weather"]["samples"]) > 0


def test_AT10_weather_timeout_degrades_gracefully(api_client, respx_mock):
    """AT-10: Open-Meteo timeout returns 200 with weather.status='unavailable'."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    # Weather upstream times out
    respx_mock.get(url__regex=r"https://api\.open-meteo\.com/v1/forecast.*").mock(
        side_effect=Exception("Connection timed out after 3.0s")
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"include_weather": True},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    # Request succeeds, fuel plan intact
    primary = data["routes"][0]
    assert primary["fuel_plan"]["status"] == "ok"
    assert len(primary["fuel_plan"]["stops"]) >= 2
    assert primary["fuel_plan"]["totals"]["total_fuel_cost_usd"] > 0

    # Weather is marked unavailable
    assert primary["weather"]["status"] == "unavailable"
    assert primary["weather"]["risk_level"] is None
    assert primary["weather"]["samples"] == []


def test_plan_with_weather_disabled(api_client, respx_mock):
    """When include_weather=false, weather is disabled and zero weather calls are made."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"include_weather": False},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["external_calls"]["weather"] == 0
    assert data["meta"]["cache"]["weather"] == "disabled"
    assert data["routes"][0]["weather"]["status"] == "disabled"
