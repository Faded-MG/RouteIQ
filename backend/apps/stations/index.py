"""In-memory StationIndex holding contiguous numpy arrays for fast geospatial filtering.

Conforms to docs/ARCHITECTURE.md §6.1, §6.3 and docs/PLAN.md T06.
"""

import threading
from dataclasses import dataclass

import numpy as np
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.common.errors import ApiError, ApiErrorCode
from apps.stations.models import ImportRun, Station


@dataclass(frozen=True)
class StationIndex:
    """Thread-safe in-memory structure holding station arrays and state medians."""

    id: np.ndarray  # int64 [N] (station primary key)
    opis_id: np.ndarray  # int64 [N] (OPIS truckstop identifier)
    lat: np.ndarray  # float64 [N]
    lon: np.ndarray  # float64 [N]
    price: np.ndarray  # float64 [N]
    state_medians: dict[str, float]
    national_median: float
    data_version: str

    def __len__(self) -> int:
        return len(self.id)


class _StationIndexManager:
    _lock: threading.Lock = threading.Lock()
    _instance: StationIndex | None = None
    _version: str | None = None
    _is_dirty: bool = False

    @classmethod
    def mark_dirty(cls) -> None:
        with cls._lock:
            cls._is_dirty = True
            cls._instance = None

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None
            cls._version = None
            cls._is_dirty = True

    @classmethod
    def get_index(cls, force_reload: bool = False) -> StationIndex:
        with cls._lock:
            if cls._instance is not None and not force_reload and not cls._is_dirty:
                return cls._instance

            latest_run = ImportRun.objects.order_by("-finished_at").first()
            if not latest_run or latest_run.stations_loaded == 0:
                cls._instance = None
                raise ApiError(
                    code=ApiErrorCode.FUEL_DATA_NOT_LOADED,
                    message="Fuel station data has not been loaded into the database.",
                    status_code=503,
                )

            current_version = latest_run.sha256
            if cls._instance is not None and not force_reload and cls._version == current_version:
                cls._is_dirty = False
                return cls._instance

            # Load from database into contiguous numpy arrays
            stations = Station.objects.all().values_list(
                "id", "opis_id", "lat", "lon", "price_usd", "state"
            )
            data = list(stations)
            if not data:
                cls._instance = None
                raise ApiError(
                    code=ApiErrorCode.FUEL_DATA_NOT_LOADED,
                    message="Fuel station data has not been loaded into the database.",
                    status_code=503,
                )

            n = len(data)
            station_ids = np.empty(n, dtype=np.int64)
            opis_ids = np.empty(n, dtype=np.int64)
            lat = np.empty(n, dtype=np.float64)
            lon = np.empty(n, dtype=np.float64)
            price = np.empty(n, dtype=np.float64)

            state_prices: dict[str, list[float]] = {}
            for i, (pk, o_id, st_lat, st_lon, price_usd, state) in enumerate(data):
                station_ids[i] = pk
                opis_ids[i] = o_id
                lat[i] = st_lat
                lon[i] = st_lon
                p = float(price_usd)
                price[i] = p
                state_prices.setdefault(state, []).append(p)

            state_medians = {st: float(np.median(prices)) for st, prices in state_prices.items()}
            national_median = float(np.median(price))

            cls._instance = StationIndex(
                id=station_ids,
                opis_id=opis_ids,
                lat=lat,
                lon=lon,
                price=price,
                state_medians=state_medians,
                national_median=national_median,
                data_version=current_version,
            )
            cls._version = current_version
            cls._is_dirty = False
            return cls._instance


@receiver(post_save, sender=ImportRun)
def on_import_run_saved(sender, instance, **kwargs) -> None:
    """Invalidate StationIndex when a new ImportRun is committed."""
    _StationIndexManager.mark_dirty()


def get_station_index(force_reload: bool = False) -> StationIndex:
    """Return the global StationIndex lazy singleton."""
    return _StationIndexManager.get_index(force_reload=force_reload)


def reset_station_index() -> None:
    """Reset the global StationIndex singleton."""
    _StationIndexManager.reset()
