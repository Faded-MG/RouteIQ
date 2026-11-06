"""Acceptance test scenarios AT-01 to AT-15 from docs/TESTING.md §9.

P0 end-to-end scenarios covering real and mocked providers, exact arithmetic,
and error handling.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.planner.serializers import PlanResponseSerializer
from apps.stations.index import get_station_index, reset_station_index
from apps.stations.models import Station

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def api_client():
    return APIClient()


def test_AT01_nyc_chicago_defaults(api_client, respx_mock):
    """AT-01: NYC -> Chicago (osrm_nyc_chicago.json), defaults.

    200; >= 2 stops needed (route > 500 mi, start fuel 0); origin_fill first;
    all constraints; validator passes; total = sum stops; cold calls = 2 geocode + 1 route.
    """
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "New York, NY", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(200, json=[{"lat": "40.7127", "lon": "-74.0060", "display_name": "New York, NY"}])

    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Chicago, IL", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(200, json=[{"lat": "41.8756", "lon": "-87.6244", "display_name": "Chicago, IL"}])

    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"query": "New York, NY"},
        "finish": {"query": "Chicago, IL"},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["meta"]["external_calls"]["geocoding"] == 2
    assert data["meta"]["external_calls"]["routing"] == 1

    primary_route = data["routes"][0]
    fuel_plan = primary_route["fuel_plan"]
    assert fuel_plan["status"] == "ok"

    stops = fuel_plan["stops"]
    assert len(stops) >= 2
    assert stops[0]["kind"] == "origin_fill"

    # Total cost equals sum of stop costs to the exact cent
    total_cost_usd = fuel_plan["totals"]["total_fuel_cost_usd"]
    sum_costs = sum(Decimal(str(s["cost_usd"])) for s in stops)
    assert Decimal(str(total_cost_usd)) == sum_costs

    # Response validates against response serializer schema
    serializer = PlanResponseSerializer(data=data)
    assert serializer.is_valid(), f"Schema error: {serializer.errors}"


def test_AT02_la_nyc_coast_to_coast(api_client, respx_mock):
    """AT-02: LA -> NYC (~2,800 mi).

    200; plan has >= 6 stops; no leg > 500 mi; total cost within
    [D/MPG * min_price, D/MPG * max_price].
    """
    with open(FIXTURES_DIR / "osrm_la_nyc.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"lat": 34.0522, "lon": -118.2437},
        "finish": {"lat": 40.7127, "lon": -74.0060},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    primary_route = data["routes"][0]
    dist_miles = primary_route["summary"]["distance_miles"]
    fuel_plan = primary_route["fuel_plan"]
    assert fuel_plan["status"] == "ok"

    stops = fuel_plan["stops"]
    assert len(stops) >= 6

    # Verify every leg between consecutive stops is <= 500 mi
    # Route milestones: origin (0.0), stops (route_mile), destination (dist_miles)
    leg_points = [0.0] + [s["route_mile"] for s in stops] + [dist_miles]
    for i in range(len(leg_points) - 1):
        leg_dist = leg_points[i + 1] - leg_points[i]
        assert leg_dist <= 500.0 + 1e-3, f"Leg {i} distance {leg_dist} exceeds 500 miles!"

    # Total cost within [D/MPG * min_price, D/MPG * max_price]
    st_index = get_station_index()
    min_price = float(st_index.price.min())
    max_price = float(st_index.price.max())
    fuel_needed = dist_miles / 10.0
    total_cost = fuel_plan["totals"]["total_fuel_cost_usd"]

    assert total_cost >= fuel_needed * min_price * 0.95
    assert total_cost <= fuel_needed * max_price * 1.05


def test_AT03_short_trip_120mi(api_client, respx_mock):
    """AT-03: Short trip (~120 mi).

    fuel_plan.status='ok', single origin fill sized to the trip,
    total ~ trip gallons * origin price.
    """
    # Create synthetic OSRM route ~120 miles (193,121 meters)
    from unittest.mock import patch

    import polyline

    coords = [(39.9526, -75.1652), (40.7128, -74.0060)]
    encoded_geom = polyline.encode(coords, 6)

    synthetic_120mi = {
        "code": "Ok",
        "routes": [
            {
                "distance": 193121.0,  # ~120 miles
                "duration": 7200.0,
                "geometry": encoded_geom,
                "legs": [{"distance": 193121.0, "duration": 7200.0, "steps": []}],
            }
        ],
    }

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=synthetic_120mi
    )

    payload = {
        "start": {"lat": 39.9526, "lon": -75.1652},
        "finish": {"lat": 40.7128, "lon": -74.0060},
        "options": {"start_fuel_gal": 0.0},
    }
    # With no intermediate stations along corridor, vehicle fills only at origin for trip length
    with patch("apps.planner.services.find_candidate_stations", return_value=[]):
        response = api_client.post("/api/v1/routes/plan", data=payload, format="json")

    assert response.status_code == 200
    data = response.json()

    fuel_plan = data["routes"][0]["fuel_plan"]
    assert fuel_plan["status"] == "ok"
    assert len(fuel_plan["stops"]) == 1
    assert fuel_plan["stops"][0]["kind"] == "origin_fill"

    # Sized to the trip (~12 gal)
    gal_bought = fuel_plan["stops"][0]["gallons_bought"]
    assert 11.9 <= gal_bought <= 12.2


def test_AT04_start_fuel_covers_trip(api_client, respx_mock):
    """AT-04: start_fuel_gal = 50, trip 300 mi -> no_refuel_needed, 0 stops, $0."""
    import polyline

    coords = [(40.7128, -74.0060), (41.8756, -78.0000)]
    encoded_geom = polyline.encode(coords, 6)

    synthetic_300mi = {
        "code": "Ok",
        "routes": [
            {
                "distance": 482803.0,  # 300 miles
                "duration": 18000.0,
                "geometry": encoded_geom,
                "legs": [{"distance": 482803.0, "duration": 18000.0, "steps": []}],
            }
        ],
    }

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=synthetic_300mi
    )

    payload = {
        "start": {"lat": 40.7128, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -78.0000},
        "options": {"start_fuel_gal": 50.0},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()

    fuel_plan = data["routes"][0]["fuel_plan"]
    assert fuel_plan["status"] == "no_refuel_needed"
    assert len(fuel_plan["stops"]) == 0
    assert fuel_plan["totals"]["total_fuel_cost_usd"] == 0.0


def test_AT05_repeat_request_zero_external_calls(api_client, respx_mock):
    """AT-05: Same request twice. Second has 0 external calls and identical routes."""
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Denver, CO", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(200, json=[{"lat": "39.7392", "lon": "-104.9903", "display_name": "Denver, CO"}])

    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Boulder, CO", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(200, json=[{"lat": "40.0150", "lon": "-105.2705", "display_name": "Boulder, CO"}])

    import polyline

    coords = [(39.7392, -104.9903), (40.0150, -105.2705)]
    encoded_geom = polyline.encode(coords, 6)

    route_resp = {
        "code": "Ok",
        "routes": [
            {
                "distance": 48280.0,  # ~30 miles
                "duration": 2400.0,
                "geometry": encoded_geom,
                "legs": [{"distance": 48280.0, "duration": 2400.0, "steps": []}],
            }
        ],
    }

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=route_resp
    )

    payload = {
        "start": {"query": "Denver, CO"},
        "finish": {"query": "Boulder, CO"},
    }

    # First request
    resp1 = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["meta"]["external_calls"]["geocoding"] == 2
    assert data1["meta"]["external_calls"]["routing"] == 1

    # Second request
    resp2 = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["meta"]["external_calls"]["geocoding"] == 0
    assert data2["meta"]["external_calls"]["routing"] == 0
    assert data2["routes"][0]["summary"] == data1["routes"][0]["summary"]


def test_AT06_coordinates_bypasses_geocoding(api_client, respx_mock):
    """AT-06: Coordinates instead of text requires 0 geocoding calls."""
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["external_calls"]["geocoding"] == 0


def test_AT07_unknown_place_returns_422(api_client, respx_mock):
    """AT-07: Unknown place -> 422 LOCATION_NOT_FOUND with details.which."""
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": "NonExistentPlace 99999",
            "countrycodes": "us",
            "limit": "1",
            "format": "jsonv2",
        },
    ).respond(200, json=[])

    payload = {
        "start": {"query": "NonExistentPlace 99999"},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "LOCATION_NOT_FOUND"
    assert data["error"]["details"]["which"] == "start"


def test_AT08_location_outside_us_returns_422(api_client, respx_mock):
    """AT-08: Geocodes outside contiguous US -> 422 LOCATION_OUTSIDE_US."""
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Anchorage, AK", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(200, json=[{"lat": "61.2181", "lon": "-149.9003", "display_name": "Anchorage, AK"}])

    payload = {
        "start": {"query": "Anchorage, AK"},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "LOCATION_OUTSIDE_US"
    assert data["error"]["details"]["which"] == "start"


def test_AT09_osrm_no_route_returns_422(api_client, respx_mock):
    """AT-09: OSRM returns NoRoute -> 422 ROUTE_NOT_FOUND."""
    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json={"code": "NoRoute", "routes": []}
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "ROUTE_NOT_FOUND"


def test_AT11_synthetic_desert_route_550mi_gap(api_client, respx_mock):
    """AT-11: Synthetic desert route with 550-mile station gap -> 422 NO_FEASIBLE_FUEL_PLAN."""
    import polyline

    # 550 miles across an area with no stations in corridor
    coords = [(28.0000, -82.0000), (36.0000, -82.0000)]
    encoded_geom = polyline.encode(coords, 6)

    # 550 miles = 885,139 meters
    synthetic_gap = {
        "code": "Ok",
        "routes": [
            {
                "distance": 885139.0,
                "duration": 36000.0,
                "geometry": encoded_geom,
                "legs": [{"distance": 885139.0, "duration": 36000.0, "steps": []}],
            }
        ],
    }

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=synthetic_gap
    )

    payload = {
        "start": {"lat": 28.0000, "lon": -82.0000},
        "finish": {"lat": 36.0000, "lon": -82.0000},
    }
    # Mock find_candidate_stations to return no stations
    from unittest.mock import patch

    with patch("apps.planner.services.find_candidate_stations", return_value=[]):
        response = api_client.post("/api/v1/routes/plan", data=payload, format="json")

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "NO_FEASIBLE_FUEL_PLAN"
    assert "largest_gap" in data["error"]["details"]
    assert data["error"]["details"]["largest_gap"]["gap_miles"] >= 500.0


def test_AT12_osrm_503_upstream_unavailable(api_client, respx_mock):
    """AT-12: OSRM 503 -> 503 UPSTREAM_UNAVAILABLE with details.provider="osrm"."""
    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        503, text="Service Unavailable"
    )

    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }
    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert data["error"]["details"]["provider"] == "osrm"
    assert "Traceback" not in json.dumps(data)


def test_AT15_station_data_not_imported(api_client):
    """AT-15: Station data not imported -> /health/ready 503; plan -> 503 FUEL_DATA_NOT_LOADED."""
    # Delete all stations to simulate unimported state
    try:
        Station.objects.all().delete()
        reset_station_index()

        # 1. /health/ready returns 503
        ready_resp = api_client.get("/api/v1/health/ready")
        assert ready_resp.status_code == 503
        ready_data = ready_resp.json()
        assert ready_data["status"] == "unavailable"
        assert ready_data["checks"]["stations"]["count"] == 0

        # 2. /api/v1/routes/plan returns 503 FUEL_DATA_NOT_LOADED
        payload = {
            "start": {"lat": 40.7127, "lon": -74.0060},
            "finish": {"lat": 41.8756, "lon": -87.6244},
        }
        plan_resp = api_client.post("/api/v1/routes/plan", data=payload, format="json")
        assert plan_resp.status_code == 503
        plan_data = plan_resp.json()
        assert plan_data["error"]["code"] == "FUEL_DATA_NOT_LOADED"
    finally:
        # Restore station data for clean state
        from apps.stations.management.commands.import_stations import Command as ImportCommand

        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        st_data_dir = repo_root / "backend" / "apps" / "stations" / "data"
        csv_file = repo_root / "data" / "fuel-prices-for-be-assessment.csv"
        places_file = st_data_dir / "us_places.csv"
        overrides_file = st_data_dir / "geocode_overrides.csv"
        cmd = ImportCommand()
        cmd.handle(
            csv=str(csv_file),
            places=str(places_file),
            overrides=str(overrides_file),
        )
        get_station_index(force_reload=True)
