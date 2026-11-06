"""Shared fixtures for API tests."""

from pathlib import Path

import pytest

from apps.stations.index import get_station_index
from apps.stations.management.commands.import_stations import Command as ImportCommand
from apps.stations.models import Station


@pytest.fixture(autouse=True)
def setup_station_data(db):
    """Ensure database has the full station dataset loaded for API testing."""
    if Station.objects.count() < 1000:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        st_data_dir = repo_root / "backend" / "apps" / "stations" / "data"
        csv_file = repo_root / "data" / "fuel-prices-for-be-assessment.csv"
        places_file = st_data_dir / "us_places.csv"
        overrides_file = st_data_dir / "geocode_overrides.csv"
        cmd = ImportCommand()
        cmd.handle(
            csv=str(csv_file),
            places=str(places_file),
            overrides=str(overrides_file),
        )
    get_station_index(force_reload=True)
