"""API tests for multi-route alternatives and route selection.

Conforms to docs/PLAN.md T16, docs/ALGORITHM.md §10, and docs/TESTING.md §9 AT-13.
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


def test_alternatives_three_routes_synthetic_fixture(api_client, respx_mock):
    """T16: With 3-route synthetic fixture, all 3 routes are evaluated independently.

    - Recommended route obeys ALGORITHM §10
    - Rank 1 is recommended
    - Comparison table has 3 rows with proper cost and duration deltas
    - Response schema validated via PlanResponseSerializer
    """
    with open(FIXTURES_DIR / "osrm_three_routes_synthetic.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"alternatives": True},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    # Validate response schema
    serializer = PlanResponseSerializer(data=data)
    assert serializer.is_valid(), f"Schema validation failed: {serializer.errors}"

    assert len(data["routes"]) == 3
    assert len(data["comparison"]) == 3
    assert data["recommendation"]["considered"] == 3

    # Recommended route must be rank 1
    rec_id = data["recommended_route_id"]
    rec_route = data["routes"][0]
    assert rec_route["id"] == rec_id
    assert rec_route["rank"] == 1
    assert rec_route["is_recommended"] is True

    # Other routes must have rank > 1 and is_recommended=False
    for r in data["routes"][1:]:
        assert r["rank"] > 1
        assert r["is_recommended"] is False

    # Comparison deltas
    rec_comp = data["comparison"][0]
    assert rec_comp["route_id"] == rec_id
    assert rec_comp["cost_delta_vs_recommended_usd"] == 0.00
    assert rec_comp["duration_delta_minutes"] == 0

    for comp in data["comparison"][1:]:
        if comp["total_fuel_cost_usd"] is not None:
            expected_cost_delta = round(
                comp["total_fuel_cost_usd"] - rec_comp["total_fuel_cost_usd"], 2
            )
            assert comp["cost_delta_vs_recommended_usd"] == expected_cost_delta


def test_alternatives_disabled_returns_single_route(api_client, respx_mock):
    """When options.alternatives is False, only primary route is returned."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"alternatives": False},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    assert len(data["routes"]) == 1
    assert len(data["comparison"]) == 1
    assert data["recommendation"]["considered"] == 1
    assert data["recommendation"]["reason"] == "lowest_cost"


def test_AT13_severe_weather_avoidance(api_client, respx_mock, monkeypatch):
    """AT-13: Severe route not recommended if another feasible route exists.

    When Route 1 is cheaper but severe weather is present, Route 2 (non-severe)
    is recommended with reason="lowest_cost_avoiding_severe_weather".
    """
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    # Inject weather override into plan_trip
    from apps.planner import views as planner_views

    orig_plan_trip = planner_views.plan_trip

    def mocked_plan_trip(*args, **kwargs):
        # r1 has severe weather, r2 is clear
        kwargs["weather_overrides"] = {
            "r1": {"status": "ok", "risk_level": "severe", "summary": "Blizzard", "samples": []},
            "r2": {"status": "ok", "risk_level": "none", "summary": "Clear", "samples": []},
        }
        return orig_plan_trip(*args, **kwargs)

    monkeypatch.setattr(planner_views, "plan_trip", mocked_plan_trip)

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"alternatives": True, "include_weather": True},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    # Route 2 must be recommended over Route 1
    assert data["recommended_route_id"] == "r2"
    assert data["recommendation"]["reason"] == "lowest_cost_avoiding_severe_weather"
    assert data["recommendation"]["discarded"] == [{"route_id": "r1", "why": "severe_weather"}]
    assert data["routes"][0]["id"] == "r2"
    assert data["routes"][0]["is_recommended"] is True
    assert data["routes"][1]["id"] == "r1"
    assert data["routes"][1]["is_recommended"] is False


def test_alternatives_with_infeasible_route_returned(api_client, respx_mock, monkeypatch):
    """Infeasible alternative is still returned with fuel_plan.status='infeasible'."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    from apps.planner import services as planner_services

    orig_optimize = planner_services.optimize
    call_count = 0

    from apps.fuel.types import InfeasibleResult

    def mocked_optimize(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Make 2nd route infeasible
            return InfeasibleResult(
                status="infeasible",
                largest_gap={"from_mile": 200.0, "to_mile": 750.0, "gap_miles": 550.0},
            )
        return orig_optimize(*args, **kwargs)

    monkeypatch.setattr(planner_services, "optimize", mocked_optimize)

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "options": {"alternatives": True},
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    serializer = PlanResponseSerializer(data=data)
    assert serializer.is_valid(), f"Schema validation failed: {serializer.errors}"

    assert data["recommended_route_id"] == "r1"
    assert data["recommendation"]["reason"] == "only_feasible_route"
    assert data["recommendation"]["discarded"] == [{"route_id": "r2", "why": "infeasible"}]

    r2_route = [r for r in data["routes"] if r["id"] == "r2"][0]
    assert r2_route["fuel_plan"]["status"] == "infeasible"
    assert r2_route["fuel_plan"]["infeasible"]["gap_miles"] == 550.0
    assert r2_route["is_recommended"] is False

    r2_comp = [c for c in data["comparison"] if c["route_id"] == "r2"][0]
    assert r2_comp["total_fuel_cost_usd"] is None
    assert r2_comp["cost_delta_vs_recommended_usd"] is None
    assert r2_comp["num_stops"] == 0
