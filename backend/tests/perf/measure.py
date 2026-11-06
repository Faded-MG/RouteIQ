"""Performance measurement benchmark script.

Conforms to docs/TESTING.md §8.
Measures candidate matching latency, DP optimization latency, end-to-end request latency,
and peak memory consumption.
"""

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

# Ensure Django settings are configured before importing Django models/index
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
import django

django.setup()

import numpy as np  # noqa: E402
import polyline  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.fuel.candidates import find_candidate_stations  # noqa: E402
from apps.fuel.optimizer import OptimizerConfig, build_fuel_nodes, optimize  # noqa: E402
from apps.geo.geometry import cumulative_distances, simplify_for_matching  # noqa: E402
from apps.stations.index import get_station_index  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def benchmark_candidate_matching(runs: int = 30) -> float:
    """Benchmark candidate matching on coast-to-coast route (osrm_la_nyc.json)."""
    with open(FIXTURES_DIR / "osrm_la_nyc.json") as f:
        data = json.load(f)

    geometry_str = data["routes"][0]["geometry"]
    raw_coords = polyline.decode(geometry_str, 6)
    coords_np = np.array(raw_coords, dtype=np.float64)

    simplified, _ = simplify_for_matching(coords_np)
    cum_miles = cumulative_distances(simplified)
    st_index = get_station_index()

    durations = []
    # Warmup
    find_candidate_stations(simplified, cum_miles, st_index)

    for _ in range(runs):
        t0 = time.perf_counter()
        cands = find_candidate_stations(simplified, cum_miles, st_index)
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1000.0)

    p50 = statistics.median(durations)
    p95 = sorted(durations)[int(0.95 * len(durations))]
    print(
        f"Candidate Matching (LA->NYC, {len(cands)} candidates): "
        f"p50={p50:.2f}ms, p95={p95:.2f}ms (Budget: <= 150ms)"
    )
    return p95


def benchmark_optimizer(runs: int = 30) -> float:
    """Benchmark DP optimization on coast-to-coast candidates."""
    with open(FIXTURES_DIR / "osrm_la_nyc.json") as f:
        data = json.load(f)

    raw_coords = polyline.decode(data["routes"][0]["geometry"], 6)
    coords_np = np.array(raw_coords, dtype=np.float64)
    simplified, _ = simplify_for_matching(coords_np)
    cum_miles = cumulative_distances(simplified)
    st_index = get_station_index()

    cands = find_candidate_stations(simplified, cum_miles, st_index)
    dest_mile = cum_miles[-1]
    cfg = OptimizerConfig(fuel_unit_gal=0.01)

    nodes = build_fuel_nodes(cands, dest_mile=dest_mile, origin_price=3.50, cfg=cfg)

    durations = []
    # Warmup
    optimize(nodes, dest_mile=dest_mile, cfg=cfg, start_fuel_gal=0.0)

    for _ in range(runs):
        t0 = time.perf_counter()
        optimize(nodes, dest_mile=dest_mile, cfg=cfg, start_fuel_gal=0.0)
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1000.0)

    p50 = statistics.median(durations)
    p95 = sorted(durations)[int(0.95 * len(durations))]
    print(
        f"DP Optimizer (LA->NYC, {len(nodes)} nodes, fuel_unit=0.01): "
        f"p50={p50:.2f}ms, p95={p95:.2f}ms (Budget: <= 150ms)"
    )
    return p95


def benchmark_memory_and_e2e() -> None:
    """Measure peak memory and end-to-end compute time."""
    tracemalloc.start()

    with open(FIXTURES_DIR / "osrm_nyc_chicago.json") as f:
        nyc_chi_fixture = json.load(f)

    from unittest.mock import patch

    client = APIClient()
    payload = {
        "start": {"lat": 40.7127, "lon": -74.0060},
        "finish": {"lat": 41.8756, "lon": -87.6244},
    }

    durations = []
    with patch("apps.geo.routing.OSRMRoutingProvider.get_routes_raw", return_value=nyc_chi_fixture):
        # Warmup
        client.post("/api/v1/routes/plan", data=payload, format="json")

        for _ in range(30):
            t0 = time.perf_counter()
            resp = client.post("/api/v1/routes/plan", data=payload, format="json")
            t1 = time.perf_counter()
            assert resp.status_code == 200
            durations.append((t1 - t0) * 1000.0)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    p50 = statistics.median(durations)
    p95 = sorted(durations)[int(0.95 * len(durations))]
    print(
        f"E2E Compute (Mocked upstream, 30 requests): "
        f"p50={p50:.2f}ms, p95={p95:.2f}ms (Budget: p50 <= 400ms, p95 <= 700ms)"
    )
    print(f"Peak Memory: {peak_mb:.2f} MB (Budget: <= 150 MB)")


def main():
    print("=== FuelRoute Performance Benchmark (TESTING.md §8) ===")
    benchmark_candidate_matching()
    benchmark_optimizer()
    benchmark_memory_and_e2e()
    print("=======================================================")


if __name__ == "__main__":
    main()
