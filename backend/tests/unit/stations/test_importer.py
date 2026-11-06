"""Unit tests for import_stations management command."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.stations.models import ImportRun, Station


@pytest.fixture
def mini_fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "fixtures"


@pytest.mark.django_db
def test_import_from_mini_fixture(mini_fixtures_dir: Path):
    csv_file = str(mini_fixtures_dir / "stations_mini.csv")
    places_file = str(mini_fixtures_dir / "places_mini.csv")

    call_command("import_stations", csv=csv_file, places=places_file, overrides="")

    # 1. Canadian rows (201, 202, 203) rejected
    assert not Station.objects.filter(opis_id__in=[201, 202, 203]).exists()

    # 2. Bad price rows rejected:
    # 301: 0.00, 302: -2.50, 303: 20.0001, 304: 99.99, 305: N/A, 306: empty
    assert not Station.objects.filter(opis_id__in=[301, 302, 303, 304, 305, 306]).exists()

    # 3. Unlocated cities (401: Atlantis FL, 402: Shangri-La CA) rejected
    assert not Station.objects.filter(opis_id__in=[401, 402]).exists()

    # 4. Duplicate aggregation on opis_id 101:
    # 3 rows: 3.2590, 3.2990, 3.2790 -> median 3.2790
    station_101 = Station.objects.get(opis_id=101)
    assert station_101.price_usd == Decimal("3.2790")
    assert station_101.price_min_usd == Decimal("3.2590")
    assert station_101.price_max_usd == Decimal("3.2990")
    assert station_101.price_rows == 3
    assert station_101.name == "Pilot Travel Center"  # tie-breaker / most frequent

    # 5. Check ImportRun stats
    run = ImportRun.objects.latest("finished_at")
    assert run.rows_read > 40
    assert run.stations_loaded > 20
    assert run.unlocated == 2  # Atlantis and Shangri-La


@pytest.mark.django_db
def test_import_idempotency(mini_fixtures_dir: Path):
    csv_file = str(mini_fixtures_dir / "stations_mini.csv")
    places_file = str(mini_fixtures_dir / "places_mini.csv")

    # Run first time
    call_command("import_stations", csv=csv_file, places=places_file, overrides="")
    count_first = Station.objects.count()

    # Run second time
    call_command("import_stations", csv=csv_file, places=places_file, overrides="")
    count_second = Station.objects.count()

    assert count_first == count_second
    assert ImportRun.objects.count() >= 2


def test_missing_csv_file_raises_command_error():
    with pytest.raises(CommandError):
        call_command("import_stations", csv="non_existent_file.csv")
