"""Test Station and ImportRun models and DB constraints."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.stations.models import ImportRun, Station


@pytest.mark.django_db
def test_create_valid_station():
    station = Station.objects.create(
        opis_id=1001,
        name="Test Travel Plaza",
        address="123 Highway 1",
        city="Des Moines",
        state="IA",
        lat=41.5868,
        lon=-93.6250,
        geocode_precision="place_centroid",
        price_usd=Decimal("3.4590"),
        price_min_usd=Decimal("3.4000"),
        price_max_usd=Decimal("3.5000"),
        price_rows=3,
        rack_id=42,
    )
    assert station.pk is not None
    assert str(station) == "Test Travel Plaza (Des Moines, IA) - $3.4590/gal"


@pytest.mark.django_db
def test_duplicate_opis_id_raises_integrity_error():
    Station.objects.create(
        opis_id=2001,
        name="Station One",
        address="100 Main St",
        city="Dallas",
        state="TX",
        lat=32.7767,
        lon=-96.7970,
        price_usd=Decimal("3.1000"),
        price_min_usd=Decimal("3.1000"),
        price_max_usd=Decimal("3.1000"),
        rack_id=10,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Station.objects.create(
                opis_id=2001,
                name="Station Duplicate",
                address="200 Main St",
                city="Dallas",
                state="TX",
                lat=32.7767,
                lon=-96.7970,
                price_usd=Decimal("3.2000"),
                price_min_usd=Decimal("3.2000"),
                price_max_usd=Decimal("3.2000"),
                rack_id=11,
            )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid_price",
    [Decimal("0.0000"), Decimal("-1.5000"), Decimal("20.0001"), Decimal("25.0000")],
)
def test_price_check_constraint(invalid_price):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Station.objects.create(
                opis_id=3001,
                name="Bad Price Station",
                address="100 Main St",
                city="Dallas",
                state="TX",
                lat=32.7767,
                lon=-96.7970,
                price_usd=invalid_price,
                price_min_usd=invalid_price,
                price_max_usd=invalid_price,
                rack_id=10,
            )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lat,lon",
    [
        (23.9, -96.0),  # lat below 24
        (50.1, -96.0),  # lat above 50
        (35.0, -125.1),  # lon west of -125
        (35.0, -65.9),  # lon east of -66
    ],
)
def test_us_bbox_check_constraint(lat, lon):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Station.objects.create(
                opis_id=4001,
                name="Out of bounds Station",
                address="100 Boundary Rd",
                city="Nowhere",
                state="TX",
                lat=lat,
                lon=lon,
                price_usd=Decimal("3.1500"),
                price_min_usd=Decimal("3.1500"),
                price_max_usd=Decimal("3.1500"),
                rack_id=10,
            )


@pytest.mark.django_db
def test_create_import_run():
    run = ImportRun.objects.create(
        source_file="data/fuel-prices-for-be-assessment.csv",
        sha256="c704371f141ded9c54df6c32d488a0ba2ceb589f88c936c967daa5330e0cd241",
        rows_read=8152,
        rows_us=8100,
        stations_loaded=6626,
        unlocated=40,
    )
    assert run.pk is not None
    assert "ImportRun c704371f" in str(run)
