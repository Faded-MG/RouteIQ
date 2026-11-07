import type { PlanRequest, PlanResponse } from "./types";

export type PlannerView = "form" | "loading" | "revealing" | "results" | "error";

export interface PlannerState {
  view: PlannerView;
  request: PlanRequest | null;
  lastError: {
    code?: string;
    message?: string;
  } | null;
}

export type PlannerAction =
  | { type: "SUBMIT"; request: PlanRequest }
  | { type: "RESPONSE"; response: PlanResponse }
  | { type: "ERROR"; code?: string; message?: string }
  | { type: "CANCEL" }
  | { type: "RETRY" }
  | { type: "EDIT" }
  | { type: "RESET" };

export const initialPlannerState: PlannerState = {
  view: "form",
  request: null,
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
        lastError: null,
      };
    case "RESPONSE": {
      const prefersReducedMotion =
        typeof window !== "undefined" &&
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      return {
        ...state,
        view: prefersReducedMotion ? "results" : "revealing",
        request: state.request,
        lastError: null,
      };
    }
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
        lastError: null,
      };
    case "RESET":
      return initialPlannerState;
    default:
      return state;
  }
}
