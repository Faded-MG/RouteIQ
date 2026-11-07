import { useMutation } from "@tanstack/react-query";
import { useMemo, useReducer, useState } from "react";
import { formatErrorMessage, planTripApi, RouteIQApiError } from "../../shared/lib/api";
import {
  initialPlannerState,
  plannerFlowReducer,
} from "./usePlannerFlow";
import type { DrivingRoute, PlanRequest, PlanResponse } from "./types";

export function useRoutePlan() {
  const [planData, setPlanData] = useState<PlanResponse | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [selectedStopSequence, setSelectedStopSequence] = useState<number | null>(null);
  const [plannerState, dispatch] = useReducer(plannerFlowReducer, initialPlannerState);

  const mutation = useMutation({
    mutationFn: (request: PlanRequest) => planTripApi(request),
    onSuccess: (data) => {
      setPlanData(data);
      setSelectedRouteId(data.recommended_route_id);
      setSelectedStopSequence(null);
      const reducedMotion =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      dispatch({ type: "RESPONSE", response: data, reducedMotion });
    },
    onError: (error) => {
      const apiError = error instanceof RouteIQApiError ? error : null;
      dispatch({
        type: "ERROR",
        code: apiError?.code,
        message: formatErrorMessage(error),
      });
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
    if (!mutation.error) return plannerState.lastError?.message ?? null;
    return formatErrorMessage(mutation.error);
  }, [mutation.error, plannerState.lastError?.message]);

  const planTrip = (request: PlanRequest) => {
    dispatch({ type: "SUBMIT", request });
    mutation.mutate(request);
  };

  return {
    planTrip,
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
    plannerState,
    reset: () => {
      mutation.reset();
      dispatch({ type: "RESET" });
      setPlanData(null);
      setSelectedRouteId(null);
      setSelectedStopSequence(null);
    },
    cancel: () => {
      mutation.reset();
      dispatch({ type: "CANCEL" });
      setPlanData(null);
      setSelectedRouteId(null);
      setSelectedStopSequence(null);
    },
    retry: () => {
      const request = plannerState.request;
      if (!request) {
        dispatch({ type: "EDIT" });
        return;
      }
      dispatch({ type: "RETRY" });
      mutation.mutate(request);
    },
  };
}
