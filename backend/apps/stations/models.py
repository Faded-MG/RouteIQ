"""Station and ImportRun database models.

Conforms to docs/ARCHITECTURE.md §5.
"""

from django.db import models


class Station(models.Model):
    """Refueling station with geographic coordinates and OPIS fuel price data."""

    id = models.BigAutoField(primary_key=True)
    opis_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    lat = models.FloatField()
    lon = models.FloatField()
    geocode_precision = models.CharField(max_length=32, default="place_centroid")
    price_usd = models.DecimalField(max_digits=7, decimal_places=4)
    price_min_usd = models.DecimalField(max_digits=7, decimal_places=4)
    price_max_usd = models.DecimalField(max_digits=7, decimal_places=4)
    price_rows = models.IntegerField(default=1)
    rack_id = models.IntegerField()
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stations_station"
        indexes = [
            models.Index(fields=["state"], name="station_state_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_usd__gt=0, price_usd__lte=20),
                name="station_price_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(lat__gte=24.0, lat__lte=50.0, lon__gte=-125.0, lon__lte=-66.0),
                name="station_coords_us_bbox",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) - ${self.price_usd}/gal"


class ImportRun(models.Model):
    """Metadata recorded for each run of import_stations."""

    id = models.BigAutoField(primary_key=True)
    source_file = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64)
    rows_read = models.IntegerField()
    rows_us = models.IntegerField()
    stations_loaded = models.IntegerField()
    unlocated = models.IntegerField()
    finished_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stations_importrun"

    def __str__(self) -> str:
        return f"ImportRun {self.sha256[:8]} ({self.finished_at}): {self.stations_loaded} loaded"
