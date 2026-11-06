#!/usr/bin/env python3
"""One-time recording script for test fixtures from OSRM and Nominatim.

Respects provider throttling policies: <= 1 req/s, descriptive User-Agent.
"""

import time
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures"
USER_AGENT = "FuelRoute-FixtureRecorder/1.0 (https://github.com/example/fuelroute)"


def fetch_and_save(url: str, params: dict, output_file: Path) -> None:
    if output_file.exists():
        print(f"File {output_file.name} already exists. Skipping.")
        return
    print(f"Fetching {url} -> {output_file.name}...")
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        output_file.write_text(resp.text)
    print(f"Saved {output_file.name} ({len(resp.text)} bytes).")
    time.sleep(1.5)  # Throttle per provider policy


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. OSRM LA to NYC
    la_nyc_url = "https://router.project-osrm.org/route/v1/driving/-118.2437,34.0522;-74.0060,40.7127"
    la_nyc_params = {
        "overview": "full",
        "geometries": "polyline6",
        "alternatives": "false",
        "steps": "false",
    }
    fetch_and_save(la_nyc_url, la_nyc_params, FIXTURES_DIR / "osrm_la_nyc.json")


if __name__ == "__main__":
    main()
