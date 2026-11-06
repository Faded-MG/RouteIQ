"""Cache models for geocoding and route responses.

Conforms to docs/ARCHITECTURE.md §5.
"""

from django.db import models


class GeocodeCache(models.Model):
    """Normalized query geocoding cache."""

    id = models.BigAutoField(primary_key=True)
    query_norm = models.CharField(max_length=255, unique=True, db_index=True)
    label = models.CharField(max_length=255, blank=True, default="")
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    provider = models.CharField(max_length=64, default="nominatim")
    raw = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "geo_geocodecache"

    def __str__(self) -> str:
        return f"{self.query_norm} -> ({self.lat}, {self.lon}) [{self.provider}]"


class RouteCache(models.Model):
    """OSRM route response cache keyed by sha256 of rounded coordinates and parameters."""

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=64, unique=True, db_index=True)
    raw_response = models.JSONField()
    provider = models.CharField(max_length=64, default="osrm")
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "geo_routecache"

    def __str__(self) -> str:
        return f"RouteCache {self.key[:8]} [{self.provider}]"
