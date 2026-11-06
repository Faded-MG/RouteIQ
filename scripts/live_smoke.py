#!/usr/bin/env python3
"""Live smoke test against real Nominatim and OSRM providers.

Conforms to docs/PLAN.md T15 and docs/TESTING.md §8.
Executes a single live trip planning request using the real network,
verifying that cold external calls <= 3 and saving output to docs/live-smoke.json.
"""

import json
import os
import sys
import time
from pathlib import Path

# Ensure backend is on sys.path and DJANGO_SETTINGS_MODULE is dev or prod
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("APP_CONTACT", "https://github.com/example/fuelroute")

import django

django.setup()

from rest_framework.test import APIClient

DOCS_DIR = REPO_ROOT / "docs"


def run_live_smoke():
    print("=== FuelRoute Live Smoke Test (Real Providers) ===")
    app_contact = os.environ.get("APP_CONTACT", "")
    print(f"Using APP_CONTACT User-Agent: {app_contact}")

    client = APIClient()

    # Query with real places: New York, NY to Chicago, IL
    payload = {
        "start": {"query": "New York, NY"},
        "finish": {"query": "Chicago, IL"},
        "options": {"start_fuel_gal": 0.0},
    }

    print(
        "Sending live trip planning request (cold run: real Nominatim + real OSRM)..."
    )
    t0 = time.perf_counter()
    response = client.post("/api/v1/routes/plan", data=payload, format="json")
    elapsed_sec = time.perf_counter() - t0

    print(f"HTTP Status: {response.status_code} in {elapsed_sec:.2f}s")
    assert response.status_code == 200, (
        f"Live smoke failed with {response.status_code}: {response.content}"
    )

    data = response.json()
    assert data["status"] == "ok"

    primary_route = data["routes"][0]
    fuel_plan = primary_route["fuel_plan"]
    totals = fuel_plan["totals"]
    ext_calls = data["meta"]["external_calls"]

    print("\n--- Route Summary ---")
    print(f"Distance: {primary_route['summary']['distance_miles']} miles")
    print(f"Duration: {primary_route['summary']['duration_minutes']} minutes")
    print(f"Stops: {len(fuel_plan['stops'])} stops")
    print(f"Fuel Purchased: {totals['fuel_purchased_gal']} gal")
    print(f"Total Cost: ${totals['total_fuel_cost_usd']:.2f}")
    print(f"Average Price: ${totals['avg_price_per_gal']:.4f}/gal")
    print(f"External Calls: {ext_calls}")

    # Verify cold call budget
    assert ext_calls["geocoding"] <= 2
    assert ext_calls["routing"] <= 1

    # Save output to docs/live-smoke.json
    output_path = DOCS_DIR / "live-smoke.json"
    output_path.write_text(json.dumps(data, indent=2))
    print(
        f"\nSaved live smoke response to {output_path.relative_to(REPO_ROOT)} ({output_path.stat().st_size} bytes)."
    )
    print("==================================================")


if __name__ == "__main__":
    run_live_smoke()
