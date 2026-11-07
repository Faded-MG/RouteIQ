import { useMemo, useReducer } from "react";
import type { PlanRequest } from "./types";
import { RoutePlannerForm } from "./RoutePlannerForm";
import { initialPlannerState, plannerFlowReducer } from "./usePlannerFlow";

interface RoutePlannerPanelProps {
  onSubmit: (request: PlanRequest) => void;
  isLoading: boolean;
  errorMessage: string | null;
}

export function RoutePlannerPanel({
  onSubmit,
  isLoading,
  errorMessage,
}: RoutePlannerPanelProps) {
  const [plannerState, dispatch] = useReducer(plannerFlowReducer, initialPlannerState);

  const currentMessage = useMemo(
    () => errorMessage ?? plannerState.lastError?.message ?? null,
    [errorMessage, plannerState.lastError?.message],
  );

  const handleSubmit = (request: PlanRequest) => {
    dispatch({ type: "SUBMIT", request });
    onSubmit(request);
  };

  const handleRetry = () => {
    const lastRequest = plannerState.request;
    if (!lastRequest) {
      dispatch({ type: "EDIT" });
      return;
    }
    dispatch({ type: "RETRY" });
    onSubmit(lastRequest);
  };

  const handleEdit = () => {
    dispatch({ type: "EDIT" });
  };

  return (
    <div className="route-planner-panel">
      {plannerState.view === "form" || plannerState.view === "loading" || plannerState.view === "error" ? (
        <RoutePlannerForm
          onSubmit={handleSubmit}
          isLoading={isLoading || plannerState.view === "loading"}
          errorMessage={currentMessage}
        />
      ) : (
        <div className="route-planner-panel__fallback" aria-live="polite">
          <p>Planner flow is ready.</p>
          <button type="button" onClick={handleEdit}>Edit</button>
          <button type="button" onClick={handleRetry}>Retry</button>
        </div>
      )}
    </div>
  );
}
