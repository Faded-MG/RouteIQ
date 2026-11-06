"""Common and health views."""

from django.http import HttpRequest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_live_view(request: HttpRequest) -> Response:
    """Liveness check endpoint. Does not touch database or external services."""
    return Response({"status": "ok"})
