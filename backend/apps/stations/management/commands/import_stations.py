"""Django management command to import and geocode fuel stations from OPIS CSV.

Conforms to docs/ARCHITECTURE.md §5.1.
Idempotent and uses stdlib csv (no pandas).
"""

import csv
import hashlib
import logging
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.stations.models import ImportRun, Station
from apps.stations.normalization import normalize_city

logger = logging.getLogger(__name__)

US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}


def compute_sha256(file_path: Path) -> str:
    """Compute sha256 checksum of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Import and geocode fuel station prices from CSV into the database."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--csv",
            type=str,
            default="data/fuel-prices-for-be-assessment.csv",
            help="Path to OPIS fuel prices CSV file.",
        )
        parser.add_argument(
            "--places",
            type=str,
            default="backend/apps/stations/data/us_places.csv",
            help="Path to US places gazetteer CSV file.",
        )
        parser.add_argument(
            "--overrides",
            type=str,
            default="backend/apps/stations/data/geocode_overrides.csv",
            help="Path to geocode overrides CSV file.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        csv_path = Path(options["csv"]).resolve()
        places_path = Path(options["places"]).resolve()
        overrides_path = Path(options["overrides"]).resolve()

        if not csv_path.exists():
            raise CommandError(f"Fuel price CSV file not found: {csv_path}")

        sha256_hash = compute_sha256(csv_path)
        self.stdout.write(f"Reading {csv_path} (SHA256: {sha256_hash})")

        # 1. Load places gazetteer and overrides
        places: dict[tuple[str, str], tuple[float, float, str]] = {}

        if places_path.is_file():
            with open(places_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row["city_norm"], row["state"].strip().upper())
                    lat = float(row["lat"])
                    lon = float(row["lon"])
                    places[key] = (lat, lon, "place_centroid")
            self.stdout.write(f"Loaded {len(places)} places from gazetteer.")

        if overrides_path.is_file():
            override_count = 0
            with open(overrides_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row["city_norm"], row["state"].strip().upper())
                    lat = float(row["lat"])
                    lon = float(row["lon"])
                    places[key] = (lat, lon, "nominatim")
                    override_count += 1
            self.stdout.write(f"Loaded {override_count} geocode overrides.")

        # 2. Read and filter fuel prices CSV
        rows_read = 0
        rows_us = 0
        by_opis_id: dict[int, list[dict[str, Any]]] = {}

        with open(csv_path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows_read += 1
                state = row.get("State", "").strip().upper()
                if state not in US_STATES:
                    continue

                raw_price = row.get("Retail Price", "").strip()
                try:
                    price = float(raw_price)
                    if price <= 0 or price > 20:
                        continue
                except ValueError:
                    continue

                raw_opis_id = row.get("OPIS Truckstop ID", "").strip()
                try:
                    opis_id = int(raw_opis_id)
                except ValueError:
                    continue

                rows_us += 1
                row["_parsed_price"] = price
                row["_parsed_opis_id"] = opis_id
                row["_state_clean"] = state
                by_opis_id.setdefault(opis_id, []).append(row)

        self.stdout.write(
            f"Read {rows_read} rows; valid US rows: {rows_us}; unique stations: {len(by_opis_id)}"
        )

        # 3. Aggregate duplicates and match coordinates
        stations_to_save: list[Station] = []
        unlocated_count = 0

        for opis_id, row_list in by_opis_id.items():
            first = row_list[0]
            city = first.get("City", "").strip()
            state = first["_state_clean"]
            address = first.get("Address", "").strip()
            rack_id_val = first.get("Rack ID", "").strip()
            try:
                rack_id = int(rack_id_val)
            except ValueError:
                rack_id = 0

            # Name: most frequent, tie-broken alphabetically
            name_counts = Counter(r.get("Truckstop Name", "").strip() for r in row_list)
            best_name = sorted(name_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

            # Price aggregation: median, min, max, count
            prices = [r["_parsed_price"] for r in row_list]
            med_price = round(Decimal(str(median(prices))), 4)
            min_price = round(Decimal(str(min(prices))), 4)
            max_price = round(Decimal(str(max(prices))), 4)
            price_rows = len(prices)

            # Location lookup
            city_norm = normalize_city(city)
            coord_info = places.get((city_norm, state))
            if not coord_info:
                unlocated_count += 1
                logger.warning(
                    "Unlocated station: opis_id=%d, city='%s', state='%s'",
                    opis_id,
                    city,
                    state,
                )
                continue

            lat, lon, precision = coord_info
            if not (24.0 <= lat <= 50.0 and -125.0 <= lon <= -66.0):
                unlocated_count += 1
                logger.warning(
                    "Station coordinates out of contiguous US bbox: opis_id=%d, lat=%f, lon=%f",
                    opis_id,
                    lat,
                    lon,
                )
                continue

            stations_to_save.append(
                Station(
                    opis_id=opis_id,
                    name=best_name,
                    address=address,
                    city=city,
                    state=state,
                    lat=lat,
                    lon=lon,
                    geocode_precision=precision,
                    price_usd=med_price,
                    price_min_usd=min_price,
                    price_max_usd=max_price,
                    price_rows=price_rows,
                    rack_id=rack_id,
                )
            )

        # 4. Atomic database persistence
        with transaction.atomic():
            Station.objects.bulk_create(
                stations_to_save,
                update_conflicts=True,
                unique_fields=["opis_id"],
                update_fields=[
                    "name",
                    "address",
                    "city",
                    "state",
                    "lat",
                    "lon",
                    "geocode_precision",
                    "price_usd",
                    "price_min_usd",
                    "price_max_usd",
                    "price_rows",
                    "rack_id",
                ],
            )
            ImportRun.objects.create(
                source_file=str(csv_path.name),
                sha256=sha256_hash,
                rows_read=rows_read,
                rows_us=rows_us,
                stations_loaded=len(stations_to_save),
                unlocated=unlocated_count,
            )

        count = len(stations_to_save)
        msg = f"Successfully imported {count} stations ({unlocated_count} unlocated)."
        self.stdout.write(self.style.SUCCESS(msg))
