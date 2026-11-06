import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  RouteIQApiError,
  formatErrorMessage,
  planTripApi,
} from "../shared/lib/api";
import type { PlanRequest, PlanResponse } from "../features/route-planner/types";

describe("API Client & Error Formatting", () => {
  describe("formatErrorMessage", () => {
    it("handles RouteIQApiError with known code", () => {
      const err = new RouteIQApiError(
        {
          code: "LOCATION_NOT_FOUND",
          message: "Could not geocode",
          details: {
            which: "start",
            query: "Atlantis",
          },
        },
        422,
      );
      const formatted = formatErrorMessage(err);
      expect(formatted).toContain("Location not found (start) \"Atlantis\"");
    });

    it("handles LOCATION_OUTSIDE_US error", () => {
      const err = new RouteIQApiError(
        { code: "LOCATION_OUTSIDE_US", message: "Outside US" },
        422,
      );
      expect(formatErrorMessage(err)).toBe(
        "Location is outside the contiguous United States. RouteIQ supports continental US locations only.",
      );
    });

    it("handles ROUTE_TOO_SHORT error", () => {
      const err = new RouteIQApiError(
        { code: "ROUTE_TOO_SHORT", message: "Too short" },
        422,
      );
      expect(formatErrorMessage(err)).toBe(
        "Start and destination must be at least 1 mile apart.",
      );
    });

    it("handles NO_FEASIBLE_FUEL_PLAN error", () => {
      const err = new RouteIQApiError(
        { code: "NO_FEASIBLE_FUEL_PLAN", message: "No plan" },
        422,
      );
      expect(formatErrorMessage(err)).toBe(
        "No feasible refueling plan found: distance between accessible stations exceeds the 500-mile vehicle range.",
      );
    });

    it("handles generic Error", () => {
      const err = new Error("Network timeout");
      expect(formatErrorMessage(err)).toBe("Network timeout");
    });

    it("handles unknown object error", () => {
      expect(formatErrorMessage("strange string")).toBe(
        "Unable to connect to RouteIQ API server. Please ensure the backend is running.",
      );
    });
  });

  describe("planTripApi", () => {
    beforeEach(() => {
      vi.stubGlobal("fetch", vi.fn());
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("returns parsed json on 200 response", async () => {
      const mockResponse: Partial<PlanResponse> = {
        request_id: "req_123",
        status: "ok",
        recommended_route_id: "r1",
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      } as Response);

      const request: PlanRequest = {
        start: { query: "New York, NY" },
        finish: { query: "Chicago, IL" },
      };

      const result = await planTripApi(request);
      expect(result.request_id).toBe("req_123");
      expect(result.status).toBe("ok");
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/routes/plan",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Content-Type": "application/json",
          }),
        }),
      );
    });

    it("throws RouteIQApiError on structured API error", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({
          error: {
            code: "LOCATION_NOT_FOUND",
            message: "Location not found",
            details: { which: "start", query: "UnknownCity" },
          },
        }),
      } as Response);

      const request: PlanRequest = {
        start: { query: "UnknownCity" },
        finish: { query: "Chicago, IL" },
      };

      await expect(planTripApi(request)).rejects.toThrow(RouteIQApiError);
    });
  });
});
