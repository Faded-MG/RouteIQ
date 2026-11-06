"""Planner API view.

Conforms to docs/API_SPEC.md §4.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.errors import ApiError, ApiErrorCode
from apps.planner.serializers import PlanRequestSerializer
from apps.planner.services import plan_trip

MAX_BODY_BYTES = 4096


class PlanView(APIView):
    """POST /api/v1/routes/plan."""

    def post(self, request, *args, **kwargs):
        # 1. Enforce max body size
        content_length = request.META.get("CONTENT_LENGTH")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    raise ApiError(
                        code=ApiErrorCode.VALIDATION_ERROR,
                        message="Request body exceeds 4 KB maximum limit.",
                        status_code=400,
                    )
            except ValueError:
                pass

        # 2. Validate input schema
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        start_data = validated_data["start"]
        finish_data = validated_data["finish"]
        options_data = validated_data.get("options", {})

        # 3. Plan trip
        plan_response = plan_trip(
            start_data=start_data,
            finish_data=finish_data,
            options_data=options_data,
        )

        # 4. Attach request_id from middleware
        req_id = getattr(request, "request_id", None)
        if req_id:
            plan_response["request_id"] = req_id

        return Response(plan_response, status=status.HTTP_200_OK)
