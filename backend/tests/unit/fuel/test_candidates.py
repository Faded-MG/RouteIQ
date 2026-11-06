"""Unit tests for station corridor search and candidate projection."""

import numpy as np
import pytest

from apps.fuel.candidates import find_candidate_stations, prune_dominated_candidates
from apps.fuel.types import CandidateStation
from apps.stations.index import StationIndex


@pytest.fixture
def dummy_station_index() -> StationIndex:
    # Set of stations at known coordinates
    # Station 1: exactly on route at mile ~34.5 (lat 40.5, lon -80.0)
    # Station 2: 5 miles east (lon -79.9) -> offset ~5.3 mi -> within 10 mi corridor
    # Station 3: 20 miles east (lon -79.6) -> offset ~21 mi -> outside 10 mi corridor
    # Station 4: Far away in Texas (lat 30.0, lon -95.0) -> outside bbox
    ids = np.array([1, 2, 3, 4], dtype=np.int64)
    opis_ids = np.array([101, 102, 103, 104], dtype=np.int64)
    lats = np.array([40.5, 40.5, 40.5, 30.0], dtype=np.float64)
    lons = np.array([-80.0, -79.9, -79.6, -95.0], dtype=np.float64)
    prices = np.array([3.20, 3.10, 2.90, 3.00], dtype=np.float64)

    return StationIndex(
        id=ids,
        opis_id=opis_ids,
        lat=lats,
        lon=lons,
        price=prices,
        state_medians={"PA": 3.15},
        national_median=3.15,
        data_version="dummy_hash",
    )


def test_straight_line_route_projections(dummy_station_index: StationIndex):
    # Route straight north from 40.0, -80.0 to 41.0, -80.0 (~69 miles)
    route_coords = np.array([[40.0, -80.0], [41.0, -80.0]], dtype=np.float64)
    route_cum = np.array([0.0, 69.0], dtype=np.float64)

    cands = find_candidate_stations(route_coords, route_cum, dummy_station_index)

    # Station 1 (on route) and Station 2 (5 mi off) are included.
    # Station 3 (20 mi off) and Station 4 (Texas) are excluded.
    cand_ids = [c.station_id for c in cands]
    assert 1 in cand_ids
    assert 2 in cand_ids
    assert 3 not in cand_ids
    assert 4 not in cand_ids

    # Check station 1 route mile and offset
    c1 = next(c for c in cands if c.station_id == 1)
    assert c1.offset_miles == pytest.approx(0.0, abs=0.1)
    assert c1.route_mile == pytest.approx(34.5, abs=0.5)
    assert c1.detour_miles == pytest.approx(0.0, abs=0.1)

    # Check station 2 offset (~5.3 miles) and detour (2 * 1.3 * offset)
    c2 = next(c for c in cands if c.station_id == 2)
    assert c2.offset_miles > 4.5 and c2.offset_miles < 6.0
    assert c2.detour_miles == pytest.approx(2.0 * 1.3 * c2.offset_miles, rel=1e-3)


def test_bbox_prefilter_equivalence(dummy_station_index: StationIndex):
    route_coords = np.array([[40.0, -80.0], [41.0, -80.0]], dtype=np.float64)
    route_cum = np.array([0.0, 69.0], dtype=np.float64)

    with_prefilter = find_candidate_stations(
        route_coords, route_cum, dummy_station_index, apply_prefilter=True
    )
    without_prefilter = find_candidate_stations(
        route_coords, route_cum, dummy_station_index, apply_prefilter=False
    )

    assert len(with_prefilter) == len(without_prefilter)
    for c1, c2 in zip(with_prefilter, without_prefilter, strict=True):
        assert c1.station_id == c2.station_id
        assert c1.route_mile == c2.route_mile
        assert c1.offset_miles == c2.offset_miles


def test_chunking_boundary_invariance(dummy_station_index: StationIndex):
    route_coords = np.array([[40.0, -80.0], [41.0, -80.0]], dtype=np.float64)
    route_cum = np.array([0.0, 69.0], dtype=np.float64)

    # Chunk size 1 vs default chunk size
    chunk_1 = find_candidate_stations(
        route_coords, route_cum, dummy_station_index, chunk_size_pairs=1
    )
    chunk_default = find_candidate_stations(
        route_coords, route_cum, dummy_station_index, chunk_size_pairs=2_000_000
    )

    assert len(chunk_1) == len(chunk_default)
    for c1, c2 in zip(chunk_1, chunk_default, strict=True):
        assert c1.station_id == c2.station_id
        assert c1.route_mile == c2.route_mile
        assert c1.detour_miles == c2.detour_miles


def test_dominance_pruning():
    # Station A: mile 100.0, price 3.10, detour 1.0 (Dominant)
    # Station B: mile 100.2, price 3.30, detour 2.0 (Dominated by A)
    # Station C: mile 100.3, price 3.00, detour 3.0 (Cheaper price, not dominated)
    cands = [
        CandidateStation(1, 101, 100.0, 0.5, 1.0, 3.10, 40.0, -80.0),
        CandidateStation(2, 102, 100.2, 1.0, 2.0, 3.30, 40.0, -80.0),
        CandidateStation(3, 103, 100.3, 1.5, 3.0, 3.00, 40.0, -80.0),
    ]

    pruned = prune_dominated_candidates(cands, window_miles=0.5, max_candidates=2)
    pruned_ids = [c.station_id for c in pruned]

    assert 1 in pruned_ids
    # Station 2 pruned because 1 has lower price & lower detour within 0.5 mi
    assert 2 not in pruned_ids
    assert 3 in pruned_ids  # Station 3 kept because lower price
