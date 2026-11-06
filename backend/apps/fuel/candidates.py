"""Station corridor search, route projection, and dominance pruning.

Conforms to docs/ALGORITHM.md §4 and §8.
"""

import math

import numpy as np

from apps.common.constants import (
    CIRCUITY_FACTOR,
    MAX_CANDIDATES,
    STATION_CORRIDOR_MILES,
)
from apps.fuel.types import CandidateStation, StationSpatialIndex

MILES_PER_DEG_LAT = 69.0
MILES_PER_DEG_LON = 69.17
DEFAULT_CHUNK_SIZE_PAIRS = 2_000_000


def prune_dominated_candidates(
    candidates: list[CandidateStation],
    window_miles: float = 0.5,
    max_candidates: int = MAX_CANDIDATES,
) -> list[CandidateStation]:
    """Prune dominated stations within window_miles along the route if count exceeds max_candidates.

    Station j is dominated by k if abs(route_mile_j - route_mile_k) <= window_miles,
    price_k <= price_j, and detour_miles_k <= detour_miles_j.
    """
    if len(candidates) <= max_candidates:
        return candidates

    # Sort primarily by route_mile
    sorted_cands = sorted(candidates, key=lambda c: (c.route_mile, c.price, c.station_id))
    kept: list[CandidateStation] = []

    for j, cand_j in enumerate(sorted_cands):
        is_dominated = False
        # Look backwards in window
        for k in range(len(kept) - 1, -1, -1):
            cand_k = kept[k]
            if cand_j.route_mile - cand_k.route_mile > window_miles:
                break
            if cand_k.price <= cand_j.price and cand_k.detour_miles <= cand_j.detour_miles:
                is_dominated = True
                break

        if not is_dominated:
            # Look forwards in window within sorted_cands
            for k in range(j + 1, len(sorted_cands)):
                cand_k = sorted_cands[k]
                if cand_k.route_mile - cand_j.route_mile > window_miles:
                    break
                if cand_k.price <= cand_j.price and cand_k.detour_miles <= cand_j.detour_miles:
                    is_dominated = True
                    break

        if not is_dominated:
            kept.append(cand_j)

    return kept


def find_candidate_stations(
    route_coords: np.ndarray,
    route_cum_miles: np.ndarray,
    station_index: StationSpatialIndex,
    chunk_size_pairs: int = DEFAULT_CHUNK_SIZE_PAIRS,
    apply_prefilter: bool = True,
) -> list[CandidateStation]:
    """Find and project all stations within STATION_CORRIDOR_MILES of the route."""
    num_verts = len(route_coords)
    if num_verts < 2 or len(station_index) == 0:
        return []

    num_segs = num_verts - 1
    a_lats = route_coords[:-1, 0]  # shape [M]
    a_lons = route_coords[:-1, 1]  # shape [M]
    b_lats = route_coords[1:, 0]  # shape [M]
    b_lons = route_coords[1:, 1]  # shape [M]

    seg_cum_start = route_cum_miles[:-1]  # shape [M]
    seg_lengths = route_cum_miles[1:] - route_cum_miles[:-1]  # shape [M]

    # 1. Bounding box prefilter
    if apply_prefilter:
        min_lat = float(np.min(route_coords[:, 0]))
        max_lat = float(np.max(route_coords[:, 0]))
        min_lon = float(np.min(route_coords[:, 1]))
        max_lon = float(np.max(route_coords[:, 1]))

        lat_pad = STATION_CORRIDOR_MILES / MILES_PER_DEG_LAT
        mid_lat = (min_lat + max_lat) / 2.0
        cos_mid_lat = max(math.cos(math.radians(mid_lat)), 0.1)
        lon_pad = STATION_CORRIDOR_MILES / (MILES_PER_DEG_LON * cos_mid_lat)

        mask = (
            (station_index.lat >= min_lat - lat_pad)
            & (station_index.lat <= max_lat + lat_pad)
            & (station_index.lon >= min_lon - lon_pad)
            & (station_index.lon <= max_lon + lon_pad)
        )
        cand_indices = np.flatnonzero(mask)
    else:
        cand_indices = np.arange(len(station_index))

    if len(cand_indices) == 0:
        return []

    # Precompute route segment deltas
    seg_d_lons_miles = (b_lons - a_lons) * MILES_PER_DEG_LON
    vy = (b_lats - a_lats) * MILES_PER_DEG_LAT  # [M]
    vy_sq = vy * vy  # [M]

    # 2. Chunking over candidate stations
    batch_size = max(1, chunk_size_pairs // num_segs)
    candidates: list[CandidateStation] = []

    for start_idx in range(0, len(cand_indices), batch_size):
        batch_cand_idx = cand_indices[start_idx : start_idx + batch_size]
        B = len(batch_cand_idx)

        s_lat = station_index.lat[batch_cand_idx].reshape(B, 1)
        s_lon = station_index.lon[batch_cand_idx].reshape(B, 1)

        # Vectorized equirectangular projection centered on station's latitude
        cos_lat0 = np.cos(np.radians(s_lat))  # [B, 1]

        vx = seg_d_lons_miles * cos_lat0  # [B, M]
        v_len_sq = vx * vx + vy_sq  # [B, M]

        wx = (s_lon - a_lons) * cos_lat0 * MILES_PER_DEG_LON  # [B, M]
        wy = (s_lat - a_lats) * MILES_PER_DEG_LAT  # [B, M]

        c1 = wx * vx + wy * vy
        t = np.where(v_len_sq > 1e-12, c1 / np.maximum(v_len_sq, 1e-12), 0.0)
        t = np.clip(t, 0.0, 1.0)  # [B, M]

        proj_x = t * vx
        proj_y = t * vy

        dx = wx - proj_x
        dy = wy - proj_y
        dist_sq = dx * dx + dy * dy  # [B, M]

        min_dist_sq = np.min(dist_sq, axis=1)  # [B]
        in_corridor = np.flatnonzero(
            min_dist_sq <= (STATION_CORRIDOR_MILES * STATION_CORRIDOR_MILES)
        )

        for i in in_corridor:
            min_d = math.sqrt(float(min_dist_sq[i]))
            station_dists = np.sqrt(dist_sq[i])  # [M]
            # Loop-back handling: earliest approach within 1 mile of minimum offset
            loopback_mask = station_dists <= (min_d + 1.0)
            qualifying_segs = np.flatnonzero(loopback_mask)

            t_segs = t[i, qualifying_segs]
            mile_markers = seg_cum_start[qualifying_segs] + t_segs * seg_lengths[qualifying_segs]
            earliest_mile = float(np.min(mile_markers))

            detour = 2.0 * CIRCUITY_FACTOR * min_d
            orig_idx = batch_cand_idx[i]

            candidates.append(
                CandidateStation(
                    station_id=int(station_index.id[orig_idx]),
                    opis_id=int(station_index.opis_id[orig_idx]),
                    route_mile=round(earliest_mile, 4),
                    offset_miles=round(min_d, 4),
                    detour_miles=round(detour, 4),
                    price=float(station_index.price[orig_idx]),
                    lat=float(station_index.lat[orig_idx]),
                    lon=float(station_index.lon[orig_idx]),
                )
            )

    # 3. Dominance pruning if candidates exceed MAX_CANDIDATES
    if len(candidates) > MAX_CANDIDATES:
        candidates = prune_dominated_candidates(candidates)

    # 4. Sort output by (route_mile, price, station_id)
    candidates.sort(key=lambda c: (c.route_mile, c.price, c.station_id))
    return candidates
