import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { formatErrorMessage, planTripApi } from "../../shared/lib/api";
import type { DrivingRoute, PlanRequest, PlanResponse } from "./types";

export function useRoutePlan() {
  const [planData, setPlanData] = useState<PlanResponse | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [selectedStopSequence, setSelectedStopSequence] = useState<number | null>(null);

  const mutation = useMutation({
    mutationFn: (request: PlanRequest) => planTripApi(request),
    onSuccess: (data) => {
      setPlanData(data);
      setSelectedRouteId(data.recommended_route_id);
      setSelectedStopSequence(null);
    },
  });

  const activeRoute: DrivingRoute | null = useMemo(() => {
    if (!planData || !planData.routes || planData.routes.length === 0) return null;
    if (selectedRouteId) {
      const found = planData.routes.find((r) => r.id === selectedRouteId);
      if (found) return found;
    }
    return planData.routes[0];
  }, [planData, selectedRouteId]);

  const errorMessage = useMemo(() => {
    if (!mutation.error) return null;
    return formatErrorMessage(mutation.error);
  }, [mutation.error]);

  return {
    planTrip: mutation.mutate,
    isLoading: mutation.isPending,
    isSuccess: mutation.isSuccess,
    error: mutation.error,
    errorMessage,
    planData,
    activeRoute,
    selectedRouteId: selectedRouteId || planData?.recommended_route_id || null,
    selectRoute: (routeId: string) => {
      setSelectedRouteId(routeId);
      setSelectedStopSequence(null);
    },
    selectedStopSequence,
    selectStop: setSelectedStopSequence,
    reset: () => {
      mutation.reset();
      setPlanData(null);
      setSelectedRouteId(null);
      setSelectedStopSequence(null);
    },
  };
}

