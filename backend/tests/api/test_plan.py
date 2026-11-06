"""API integration test for POST /api/v1/routes/plan.

Conforms to docs/PLAN.md T14 and docs/TESTING.md §6, §9.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.planner.serializers import PlanResponseSerializer

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def api_client():
    return APIClient()


def test_plan_endpoint_nyc_chicago_contract(api_client, respx_mock):
    """T14: Fixture request NYC->Chicago returns 200 matching API_SPEC schema.

    - total_fuel_cost_usd = sum of stop costs to the cent
    - cold external calls = 2 geocoding + 1 routing
    """
    # 1. Mock Nominatim geocoding
    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "New York, NY", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(
        200,
        json=[
            {
                "lat": "40.7127",
                "lon": "-74.0060",
                "display_name": "New York, New York, United States",
            }
        ],
    )

    respx_mock.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Chicago, IL", "countrycodes": "us", "limit": "1", "format": "jsonv2"},
    ).respond(
        200,
        json=[
            {
                "lat": "41.8756",
                "lon": "-87.6244",
                "display_name": "Chicago, Illinois, United States",
            }
        ],
    )

    # 2. Mock OSRM routing with fixture
    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        osrm_fixture = json.load(f)

    respx_mock.get(url__regex=r"https://router\.project-osrm\.org/route/v1/driving/.*").respond(
        200, json=osrm_fixture
    )

    # 3. Request trip plan
    payload = {
        "start": {"query": "New York, NY"},
        "finish": {"query": "Chicago, IL"},
        "options": {"start_fuel_gal": 0.0},
    }

    response = api_client.post(
        "/api/v1/routes/plan",
        data=payload,
        format="json",
        HTTP_X_REQUEST_ID="test-request-id-12345",
    )

    assert response.status_code == 200
    data = response.json()

    # 4. Schema validation using DRF PlanResponseSerializer
    serializer = PlanResponseSerializer(data=data)
    assert serializer.is_valid(), f"Schema validation errors: {serializer.errors}"

    # 5. Verify Request ID
    assert data["request_id"] == "test-request-id-12345"
    assert data["status"] == "ok"

    # 6. Verify Cold Call Budget
    assert data["meta"]["external_calls"]["geocoding"] == 2
    assert data["meta"]["external_calls"]["routing"] == 1
    assert data["meta"]["external_calls"]["weather"] == 0

    # 7. Verify Route and Stops
    assert len(data["routes"]) >= 1
    primary_route = data["routes"][0]
    fuel_plan = primary_route["fuel_plan"]
    assert fuel_plan["status"] == "ok"

    stops = fuel_plan["stops"]
    assert len(stops) >= 1
    assert stops[0]["kind"] == "origin_fill"

    # Verify stops ordered by route_mile
    route_miles = [s["route_mile"] for s in stops]
    assert route_miles == sorted(route_miles)

    # 8. Verify cost arithmetic to the exact cent
    total_cost_usd = fuel_plan["totals"]["total_fuel_cost_usd"]
    sum_stops_cost = sum(Decimal(str(s["cost_usd"])) for s in stops)
    assert Decimal(str(total_cost_usd)) == sum_stops_cost


def test_plan_with_coordinates_bypasses_geocoding(api_client, respx_mock):
    """Direct coordinates require zero geocoding calls."""
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
    assert data["meta"]["external_calls"]["routing"] == 1
    assert data["start"]["source"] == "coordinates"
    assert data["finish"]["source"] == "coordinates"


def test_plan_route_too_short_422(api_client):
    """Start and finish < 1 mile apart returns 422 ROUTE_TOO_SHORT."""
    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 40.7128, "lon": -74.0061},  # ~40 feet apart
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "ROUTE_TOO_SHORT"


def test_plan_validation_error_unknown_key_400(api_client):
    """Unknown root or nested keys rejected with 400 VALIDATION_ERROR."""
    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
        "unexpected_key": "not_allowed",
    }

    response = api_client.post("/api/v1/routes/plan", data=payload, format="json")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "unexpected_key" in data["error"]["details"]["fields"]


def test_example_response_in_spec_is_valid():
    """Parses the JSON block of API_SPEC §6 after replacing placeholder ellipsis.

    Conforms to docs/TESTING.md §6 requirement:
    'test_example_response_in_spec_is_valid (parses the JSON block of API_SPEC §6
    after replacing "…" placeholders using a documented transformation).'
    """
    spec_path = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "API_SPEC.md"
    content = spec_path.read_text()

    # Extract JSON between ```json and ``` under section 6
    section_match = re.search(
        r"## 6\. Complete example response.*?```json\s*(.*?)\s*```", content, re.DOTALL
    )
    assert section_match is not None, "Failed to locate section 6 JSON example in API_SPEC.md"
    raw_json = section_match.group(1)

    # Documented placeholder transformations
    transformed_json = (
        raw_json.replace('"…", ', "")
        .replace('"…"', "[-75.0, 41.0]")
        .replace(
            '"…omitted in this documentation example; same Stop schema…"',
            json.dumps(
                {
                    "sequence": 1,
                    "kind": "origin_fill",
                    "station": {
                        "id": 3101,
                        "opis_id": 68102,
                        "name": "SUNOCO",
                        "address": "ST 17",
                        "city": "Carlstadt",
                        "state": "NJ",
                        "lat": 40.8307,
                        "lon": -74.0910,
                        "position_precision": "place_centroid",
                    },
                    "route_mile": 0.0,
                    "offset_miles": 0.0,
                    "detour_miles": 0.0,
                    "arrival_fuel_gal": 0.0,
                    "gallons_bought": 4.70,
                    "price_per_gal": 3.1623,
                    "cost_usd": 14.86,
                    "fuel_after_gal": 4.70,
                    "eta_minutes_from_start": 0,
                }
            ),
        )
        .replace("9d2f…c41a", "9d2fc41a")
    )

    data = json.loads(transformed_json)
    serializer = PlanResponseSerializer(data=data)
    assert serializer.is_valid(), f"Schema validation failed: {serializer.errors}"
