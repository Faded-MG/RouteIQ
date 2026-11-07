import type { PlanRequest, PlanResponse } from "./types";

export type PlannerView = "form" | "loading" | "revealing" | "results" | "error";

export interface PlannerState {
  view: PlannerView;
  request: PlanRequest | null;
  response: PlanResponse | null;
  lastError: {
    code?: string;
    message?: string;
  } | null;
}

export type PlannerAction =
  | { type: "SUBMIT"; request: PlanRequest }
  | { type: "RESPONSE"; response: PlanResponse; reducedMotion: boolean }
  | { type: "ERROR"; code?: string; message?: string }
  | { type: "REVEAL_COMPLETE" }
  | { type: "SKIP_REVEAL" }
  | { type: "CANCEL" }
  | { type: "RETRY" }
  | { type: "EDIT" }
  | { type: "RESET" };

export const initialPlannerState: PlannerState = {
  view: "form",
  request: null,
  response: null,
  lastError: null,
};

export function plannerFlowReducer(
  state: PlannerState,
  action: PlannerAction,
): PlannerState {
  switch (action.type) {
    case "SUBMIT":
      return {
        ...state,
        view: "loading",
        request: action.request,
        response: null,
        lastError: null,
      };
    case "RESPONSE":
      return {
        ...state,
        view: action.reducedMotion ? "results" : "revealing",
        response: action.response,
        lastError: null,
      };
    case "REVEAL_COMPLETE":
    case "SKIP_REVEAL":
      return state.view === "revealing" ? { ...state, view: "results" } : state;
    case "ERROR":
      return {
        ...state,
        view: "error",
        lastError: {
          code: action.code,
          message: action.message,
        },
      };
    case "CANCEL":
      return initialPlannerState;
    case "RETRY":
      return {
        ...state,
        view: "loading",
      };
    case "EDIT":
      return {
        ...state,
        view: "form",
        response: null,
        lastError: null,
      };
    case "RESET":
      return initialPlannerState;
    default:
      return state;
  }
}
