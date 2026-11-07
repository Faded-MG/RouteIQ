import { describe, expect, it, vi } from "vitest";
import {
  initialPlannerState,
  plannerFlowReducer,
} from "../features/route-planner/usePlannerFlow";

describe("usePlannerFlow reducer", () => {
  it("moves from form to loading to revealing to results", () => {
    const request = {
      start: { query: "New York, NY" },
      finish: { query: "Chicago, IL" },
      options: { include_weather: true, alternatives: true, start_fuel_gal: 0 },
    };

    const submitted = plannerFlowReducer(initialPlannerState, {
      type: "SUBMIT",
      request,
    });

    expect(submitted.view).toBe("loading");

    const revealed = plannerFlowReducer(submitted, {
      type: "RESPONSE",
      response: {
        request_id: "req-1",
        status: "ok",
        assumptions: {
          mpg: 10,
          max_range_miles: 500,
          tank_capacity_gal: 50,
          start_fuel_gal: 0,
          reserve_gal: 0,
          station_corridor_miles: 10,
          circuity_factor: 1.3,
          fuel_unit_gal: 0.01,
          leftover_fuel_value_usd: 0,
        },
        start: { label: "New York, NY", lat: 40.7128, lon: -74.006, source: "geocoded", cached: false },
        finish: { label: "Chicago, IL", lat: 41.8781, lon: -87.6298, source: "geocoded", cached: false },
        recommended_route_id: "r1",
        recommendation: {
          reason: "lowest_cost",
          considered: 1,
          discarded: [],
        },
        routes: [],
        comparison: [],
        meta: {
          external_calls: { geocoding: 0, routing: 0, weather: 0 },
          cache: { plan: "miss", geocode: ["miss"], route: "miss", weather: "n/a" },
          timings_ms: { total: 0, geocode: 0, routing: 0, matching: 0, optimization: 0, weather: 0 },
          data: {
            station_count: 0,
            stations_data_version: "v1",
            station_position_precision: "place_centroid",
            price_aggregation: "median",
          },
          attribution: ["OpenStreetMap"],
        },
      },
    });

    expect(revealed.view).toBe("revealing");

    const results = plannerFlowReducer(revealed, { type: "EDIT" });
    expect(results.view).toBe("form");
  });

  it("handles error and cancel states", () => {
    const state = plannerFlowReducer(initialPlannerState, {
      type: "ERROR",
      code: "LOCATION_NOT_FOUND",
      message: "Start city not found",
    });

    expect(state.view).toBe("error");
    expect(state.lastError?.code).toBe("LOCATION_NOT_FOUND");

    const cancelled = plannerFlowReducer(state, { type: "CANCEL" });
    expect(cancelled.view).toBe("form");
  });

  it("uses reduced-motion shortcut when the user prefers less animation", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const state = plannerFlowReducer(
      { ...initialPlannerState, view: "loading" },
      { type: "RESPONSE", response: {} as never },
    );
    expect(state.view).toBe("results");
    vi.unstubAllGlobals();
  });
});
