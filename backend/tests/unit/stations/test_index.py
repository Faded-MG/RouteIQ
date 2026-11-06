"""Unit tests for StationIndex lazy singleton and in-memory cache."""

from decimal import Decimal

import numpy as np
import pytest

from apps.common.errors import ApiError, ApiErrorCode
from apps.stations.index import get_station_index, reset_station_index
from apps.stations.models import ImportRun, Station


@pytest.fixture(autouse=True)
def clean_index():
    reset_station_index()
    yield
    reset_station_index()


@pytest.mark.django_db
def test_raises_when_fuel_data_not_loaded():
    Station.objects.all().delete()
    ImportRun.objects.all().delete()

    with pytest.raises(ApiError) as exc_info:
        get_station_index()

    assert exc_info.value.code == ApiErrorCode.FUEL_DATA_NOT_LOADED
    assert exc_info.value.status_code == 503


@pytest.mark.django_db
def test_lazy_load_and_zero_queries(django_assert_num_queries):
    # Setup test stations
    ImportRun.objects.create(
        source_file="test.csv",
        sha256="hash1",
        rows_read=2,
        rows_us=2,
        stations_loaded=2,
        unlocated=0,
    )
    Station.objects.create(
        opis_id=1,
        name="Station A",
        address="100 Main",
        city="Des Moines",
        state="IA",
        lat=41.5,
        lon=-93.6,
        price_usd=Decimal("3.2000"),
        price_min_usd=Decimal("3.2000"),
        price_max_usd=Decimal("3.2000"),
        rack_id=1,
    )
    Station.objects.create(
        opis_id=2,
        name="Station B",
        address="200 Main",
        city="Omaha",
        state="NE",
        lat=41.2,
        lon=-95.9,
        price_usd=Decimal("3.4000"),
        price_min_usd=Decimal("3.4000"),
        price_max_usd=Decimal("3.4000"),
        rack_id=2,
    )

    # First read loads into memory
    index = get_station_index()
    assert len(index) == 2
    assert index.data_version == "hash1"

    # Second read: exactly 0 DB queries
    with django_assert_num_queries(0):
        cached_index = get_station_index()

    assert cached_index is index
    assert index.id.flags.c_contiguous
    assert index.lat.flags.c_contiguous
    assert index.lon.flags.c_contiguous
    assert index.price.flags.c_contiguous
    assert index.id.dtype == np.int64
    assert index.price.dtype == np.float64


@pytest.mark.django_db
def test_reload_on_import_run_version_change():
    ImportRun.objects.create(
        source_file="v1.csv",
        sha256="v1_sha",
        rows_read=1,
        rows_us=1,
        stations_loaded=1,
        unlocated=0,
    )
    Station.objects.create(
        opis_id=1,
        name="Station 1",
        address="100",
        city="A",
        state="IA",
        lat=41.5,
        lon=-93.6,
        price_usd=Decimal("3.1000"),
        price_min_usd=Decimal("3.1000"),
        price_max_usd=Decimal("3.1000"),
        rack_id=1,
    )

    index1 = get_station_index()
    assert index1.data_version == "v1_sha"
    assert len(index1) == 1

    # Add second station and newer ImportRun
    Station.objects.create(
        opis_id=2,
        name="Station 2",
        address="200",
        city="B",
        state="IA",
        lat=41.6,
        lon=-93.5,
        price_usd=Decimal("3.3000"),
        price_min_usd=Decimal("3.3000"),
        price_max_usd=Decimal("3.3000"),
        rack_id=1,
    )
    ImportRun.objects.create(
        source_file="v2.csv",
        sha256="v2_sha",
        rows_read=2,
        rows_us=2,
        stations_loaded=2,
        unlocated=0,
    )

    index2 = get_station_index()
    assert index2.data_version == "v2_sha"
    assert len(index2) == 2
    assert index2.state_medians["IA"] == 3.2  # median of 3.1 and 3.3
    assert index2.national_median == 3.2
