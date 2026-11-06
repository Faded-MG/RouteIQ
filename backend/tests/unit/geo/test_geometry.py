"""Unit tests for apps/geo/geometry.py.

Conforms to docs/TESTING.md §4.
"""

import numpy as np
import pytest

from apps.geo.geometry import (
    cumulative_distances,
    decode_polyline6,
    douglas_peucker,
    encode_polyline6,
    haversine_distance_miles,
    simplify_for_display,
    simplify_for_matching,
)

# Reference Great Circle spherical haversine distances in statute miles (R = 3958.7613 mi)
KNOWN_CITY_PAIRS = [
    # NYC (40.7128, -74.0060) to LA (34.0522, -118.2437)
    (40.7128, -74.0060, 34.0522, -118.2437, 2445.56),
    # NYC (40.7128, -74.0060) to Chicago (41.8781, -87.6298)
    (40.7128, -74.0060, 41.8781, -87.6298, 711.03),
    # SF (37.7749, -122.4194) to Seattle (47.6062, -122.3321)
    (37.7749, -122.4194, 47.6062, -122.3321, 679.29),
    # Miami (25.7617, -80.1918) to Seattle (47.6062, -122.3321)
    (25.7617, -80.1918, 47.6062, -122.3321, 2731.61),
    # Dallas (32.7767, -96.7970) to Denver (39.7392, -104.9903)
    (32.7767, -96.7970, 39.7392, -104.9903, 662.57),
]


@pytest.mark.parametrize("lat1,lon1,lat2,lon2,expected_miles", KNOWN_CITY_PAIRS)
def test_haversine_known_city_pairs(lat1, lon1, lat2, lon2, expected_miles):
    dist = haversine_distance_miles(lat1, lon1, lat2, lon2)
    relative_error = abs(dist - expected_miles) / expected_miles
    assert relative_error <= 0.002, (
        f"Haversine {dist:.2f} deviates by {relative_error * 100:.3f}% from {expected_miles}"
    )


def test_polyline6_encode_decode_round_trip():
    original = np.array(
        [
            [40.712775, -74.005973],
            [41.586835, -93.624959],
            [37.774929, -122.419416],
        ],
        dtype=np.float64,
    )
    encoded = encode_polyline6(original)
    decoded = decode_polyline6(encoded)

    assert len(decoded) == len(original)
    np.testing.assert_allclose(decoded, original, atol=1e-5)


def test_cumulative_distances_and_rescaling():
    coords = np.array(
        [
            [40.0, -80.0],
            [40.5, -80.0],
            [41.0, -80.0],
        ],
        dtype=np.float64,
    )
    # Target scale to exactly 100.0 miles
    cum = cumulative_distances(coords, target_total_miles=100.0)

    assert len(cum) == 3
    assert cum[0] == 0.0
    assert cum[-1] == 100.0
    assert cum[1] == pytest.approx(50.0, rel=1e-3)


def test_douglas_peucker_collinear_points():
    # 5 collinear points along latitude 40.0
    coords = np.array(
        [
            [40.0, -80.0],
            [40.0, -80.1],
            [40.0, -80.2],
            [40.0, -80.3],
            [40.0, -80.4],
        ],
        dtype=np.float64,
    )
    simplified = douglas_peucker(coords, tolerance_miles=0.05)
    # Collinear points within tolerance should simplify to just start and end
    assert len(simplified) == 2
    np.testing.assert_allclose(simplified[0], coords[0])
    np.testing.assert_allclose(simplified[1], coords[-1])


def test_simplify_for_matching():
    coords = np.array(
        [
            [40.0, -80.0],
            [40.0, -80.1],
            [40.5, -80.2],  # Deviation > 0.05 mi
            [40.0, -80.3],
            [40.0, -80.4],
        ],
        dtype=np.float64,
    )
    simplified, kept_indices = simplify_for_matching(coords, tolerance_miles=0.05)
    assert len(simplified) >= 3
    assert 0 in kept_indices
    assert (len(coords) - 1) in kept_indices
    assert len(simplified) == len(kept_indices)


def test_simplify_for_display_cap_2000():
    # Generate zigzag line with 3,000 points
    t = np.linspace(0, 10, 3000)
    lats = 35.0 + t * 0.1
    lons = -100.0 + np.sin(t * 100) * 0.01
    coords = np.column_stack([lats, lons])

    display_coords = simplify_for_display(coords, initial_tolerance=0.001, max_points=2000)
    assert len(display_coords) <= 2000
    assert len(display_coords) >= 2


def test_degenerate_edge_cases():
    # Empty
    empty = np.empty((0, 2), dtype=np.float64)
    assert len(cumulative_distances(empty)) == 0
    assert len(douglas_peucker(empty, 0.1)) == 0

    # Single point
    single = np.array([[40.0, -80.0]], dtype=np.float64)
    assert len(cumulative_distances(single)) == 1
    assert len(douglas_peucker(single, 0.1)) == 1

    # Identical points
    identical = np.array([[40.0, -80.0], [40.0, -80.0]], dtype=np.float64)
    cum = cumulative_distances(identical)
    assert cum[-1] == 0.0
    assert len(douglas_peucker(identical, 0.1)) == 2
