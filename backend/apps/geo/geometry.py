"""Geospatial geometry primitives: Haversine, Polyline6, and Douglas-Peucker simplification.

Conforms to docs/ALGORITHM.md §4, docs/ARCHITECTURE.md §6.2, and docs/PLAN.md T07.
"""

import math

import numpy as np
import polyline

from apps.common.constants import (
    DISPLAY_GEOMETRY_MAX_POINTS,
    EARTH_RADIUS_MILES,
    SIMPLIFICATION_TOLERANCE_DISPLAY_MILES,
    SIMPLIFICATION_TOLERANCE_MATCHING_MILES,
)

MILES_PER_DEG_LAT = 69.0
MILES_PER_DEG_LON = 69.17


def haversine_distance_miles(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> float | np.ndarray:
    """Compute Great Circle distance in miles using the Haversine formula (R = 3958.7613 mi)."""
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)

    a = np.sin(delta_phi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_RADIUS_MILES * c


def decode_polyline6(encoded: str) -> np.ndarray:
    """Decode polyline6 string into float64[N, 2] array of [lat, lon]."""
    coords = polyline.decode(encoded, precision=6)
    if not coords:
        return np.empty((0, 2), dtype=np.float64)
    return np.array(coords, dtype=np.float64)


def encode_polyline6(coords: np.ndarray | list[tuple[float, float]]) -> str:
    """Encode [lat, lon] coordinates into polyline6 string."""
    return polyline.encode(coords, precision=6)


def cumulative_distances(coords: np.ndarray, target_total_miles: float | None = None) -> np.ndarray:
    """Compute cumulative distance along polyline vertices, optionally rescaled to OSRM distance."""
    n = len(coords)
    if n == 0:
        return np.empty(0, dtype=np.float64)
    if n == 1:
        return np.zeros(1, dtype=np.float64)

    lats = coords[:, 0]
    lons = coords[:, 1]
    step_distances = haversine_distance_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])

    cum = np.empty(n, dtype=np.float64)
    cum[0] = 0.0
    cum[1:] = np.cumsum(step_distances)

    if target_total_miles is not None and cum[-1] > 0.0:
        scale_factor = target_total_miles / cum[-1]
        cum *= scale_factor
        cum[-1] = target_total_miles

    return cum


def _point_to_segment_distance_equirectangular(
    p_lat: np.ndarray,
    p_lon: np.ndarray,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> np.ndarray:
    """Vectorized perpendicular distance from points P to line segment AB in miles."""
    mid_lat_rad = math.radians((a_lat + b_lat) / 2.0)
    cos_lat = math.cos(mid_lat_rad)

    # Convert to equirectangular miles with respect to A
    vx = (b_lon - a_lon) * cos_lat * MILES_PER_DEG_LON
    vy = (b_lat - a_lat) * MILES_PER_DEG_LAT
    v_len_sq = vx * vx + vy * vy

    wx = (p_lon - a_lon) * cos_lat * MILES_PER_DEG_LON
    wy = (p_lat - a_lat) * MILES_PER_DEG_LAT

    if v_len_sq <= 1e-12:
        return np.sqrt(wx * wx + wy * wy)

    t = (wx * vx + wy * vy) / v_len_sq
    t = np.clip(t, 0.0, 1.0)

    proj_x = t * vx
    proj_y = t * vy

    dx = wx - proj_x
    dy = wy - proj_y
    return np.sqrt(dx * dx + dy * dy)


def douglas_peucker_indices(coords: np.ndarray, tolerance_miles: float) -> np.ndarray:
    """Iterative Douglas-Peucker simplification returning sorted boolean mask of kept indices."""
    n = len(coords)
    if n <= 2:
        return np.ones(n, dtype=bool)

    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[n - 1] = True

    stack = [(0, n - 1)]
    lats = coords[:, 0]
    lons = coords[:, 1]

    while stack:
        start_idx, end_idx = stack.pop()
        if end_idx <= start_idx + 1:
            continue

        a_lat, a_lon = coords[start_idx]
        b_lat, b_lon = coords[end_idx]

        sub_lats = lats[start_idx + 1 : end_idx]
        sub_lons = lons[start_idx + 1 : end_idx]

        dists = _point_to_segment_distance_equirectangular(
            sub_lats, sub_lons, a_lat, a_lon, b_lat, b_lon
        )

        max_idx_in_sub = int(np.argmax(dists))
        max_dist = dists[max_idx_in_sub]

        if max_dist > tolerance_miles:
            split_idx = start_idx + 1 + max_idx_in_sub
            keep[split_idx] = True
            stack.append((start_idx, split_idx))
            stack.append((split_idx, end_idx))

    return keep


def douglas_peucker(coords: np.ndarray, tolerance_miles: float) -> np.ndarray:
    """Simplify polyline coordinates to a given tolerance in miles."""
    mask = douglas_peucker_indices(coords, tolerance_miles)
    return coords[mask]


def simplify_for_matching(
    coords: np.ndarray,
    tolerance_miles: float = SIMPLIFICATION_TOLERANCE_MATCHING_MILES,
) -> tuple[np.ndarray, np.ndarray]:
    """Simplify route for station corridor matching. Returns (simplified_coords, kept_indices)."""
    mask = douglas_peucker_indices(coords, tolerance_miles)
    kept_indices = np.flatnonzero(mask)
    return coords[mask], kept_indices


def simplify_for_display(
    coords: np.ndarray,
    initial_tolerance: float = SIMPLIFICATION_TOLERANCE_DISPLAY_MILES,
    max_points: int = DISPLAY_GEOMETRY_MAX_POINTS,
) -> np.ndarray:
    """Simplify route for frontend GeoJSON rendering, capped at max_points vertices."""
    n = len(coords)
    if n <= max_points:
        return douglas_peucker(coords, initial_tolerance)

    tol = initial_tolerance
    simplified = douglas_peucker(coords, tol)

    # If still above max_points, iteratively increase tolerance until under cap
    while len(simplified) > max_points and tol < 10.0:
        tol *= 1.5
        simplified = douglas_peucker(coords, tol)

    return simplified
