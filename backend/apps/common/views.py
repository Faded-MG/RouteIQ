"""Common and health views."""

from django.db import connection
from django.http import HttpRequest
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_live_view(request: HttpRequest) -> Response:
    """Liveness check endpoint. Does not touch database or external services."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready_view(request: HttpRequest) -> Response:
    """Readiness check endpoint conforming to API_SPEC §5."""
    checks = {}
    db_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row and row[0] == 1:
                db_ok = True
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    station_count = 0
    if db_ok:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'apps_stations_station'"
                )
                table_exists = cursor.fetchone() is not None
                if table_exists:
                    cursor.execute("SELECT count(*) FROM apps_stations_station")
                    station_count = cursor.fetchone()[0]

            if station_count > 0:
                checks["stations"] = {"status": "ok", "count": station_count}
            else:
                checks["stations"] = {"status": "empty", "count": 0}
        except Exception as exc:
            checks["stations"] = {"status": "error", "error": str(exc)}
    else:
        checks["stations"] = {"status": "unknown"}

    is_ready = db_ok and station_count > 0
    resp_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    resp_data = {
        "status": "ok" if is_ready else "unavailable",
        "checks": checks,
    }
    return Response(resp_data, status=resp_status)
