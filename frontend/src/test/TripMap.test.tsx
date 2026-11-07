import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DrivingRoute, PlanResponse } from "../features/route-planner/types";
import {
  maplibreMockState,
  resetMapLibreMocks,
} from "./mocks/maplibre-gl";
import { TripMap } from "../features/map/TripMap";

function makeRoute(id: string, rank: number, coordinates: [number, number][]): DrivingRoute {
  return {
    id,
    rank,
    is_recommended: rank === 1,
    summary: { distance_miles: 790, duration_minutes: 740 },
    geometry: { type: "LineString", coordinates },
    fuel_plan: {
      status: "ok",
      origin_price_source: "nearest_station",
      stops: [
        {
          sequence: 1,
          kind: "en_route",
          station: {
            id: rank,
            opis_id: rank,
            name: `Station ${rank}`,
            address: "Main St",
            city: "Cleveland",
            state: "OH",
            lat: 41.5,
            lon: -81.6,
            position_precision: "place_centroid",
          },
          route_mile: 300,
          offset_miles: 1,
          detour_miles: 2,
          arrival_fuel_gal: 10,
          gallons_bought: 20,
          price_per_gal: 3.25,
          cost_usd: 65,
          fuel_after_gal: 30,
          eta_minutes_from_start: 300,
        },
      ],
      totals: {
        total_fuel_cost_usd: 65,
        fuel_consumed_gal: 50,
        fuel_purchased_gal: 20,
        leftover_gal: 0,
        avg_price_per_gal: 3.25,
        cost_per_mile_usd: 0.08,
        num_stops: 1,
        extra_detour_miles: 2,
      },
    },
    weather: {
      status: "disabled",
      risk_level: null,
      summary: null,
      samples: [],
    },
  };
}

const routeA = makeRoute("r1", 1, [
  [-74.006, 40.7128],
  [-81.6, 41.5],
  [-87.6298, 41.8781],
]);
const routeB = makeRoute("r2", 2, [
  [-73.9, 40.8],
  [-82, 41.6],
  [-87.5, 41.9],
]);

const response: PlanResponse = {
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
  start: {
    label: "New York, NY",
    lat: 40.7128,
    lon: -74.006,
    source: "geocoded",
    cached: false,
  },
  finish: {
    label: "Chicago, IL",
    lat: 41.8781,
    lon: -87.6298,
    source: "geocoded",
    cached: false,
  },
  recommended_route_id: "r1",
  recommendation: { reason: "lowest_cost", considered: 2, discarded: [] },
  routes: [routeA, routeB],
  comparison: [],
  meta: {
    external_calls: { geocoding: 0, routing: 0, weather: 0 },
    cache: { plan: "miss", geocode: [], route: "miss", weather: "n/a" },
    timings_ms: { total: 0, geocode: 0, routing: 0, matching: 0, optimization: 0, weather: 0 },
    data: {
      station_count: 1,
      stations_data_version: "v1",
      station_position_precision: "place_centroid",
      price_aggregation: "median",
    },
    attribution: ["OpenStreetMap contributors"],
  },
};

function setThemeTokens(): void {
  const tokens: Record<string, string> = {
    "--color-bg": "#f3f4f6",
    "--color-route-a": "#2563eb",
    "--color-route-b": "#0f766e",
    "--color-route-c": "#c2410c",
    "--color-route-muted": "#9ca3af",
    "--color-text": "#111827",
    "--color-surface": "#ffffff",
    "--color-accent": "#2563eb",
  };
  for (const [name, value] of Object.entries(tokens)) {
    document.documentElement.style.setProperty(name, value);
  }
}

const selectStop = vi.fn();

function renderMap(activeRoute: DrivingRoute | null = routeA) {
  return render(
    <TripMap
      planResponse={response}
      activeRoute={activeRoute}
      selectedStopSequence={null}
      onSelectStop={selectStop}
    />,
  );
}

describe("TripMap", () => {
  beforeEach(() => {
    resetMapLibreMocks();
    selectStop.mockClear();
    setThemeTokens();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as WebGLRenderingContext,
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    document.documentElement.removeAttribute("style");
  });

  it("adds one stable GeoJSON source and two layers for each route", async () => {
    const view = renderMap();
    const map = maplibreMockState.maps[0];

    await waitFor(() => expect(map.addSource).toHaveBeenCalledTimes(2));
    expect(map.addLayer).toHaveBeenCalledTimes(4);
    expect(map.sources.get("route-r1")?.data).toMatchObject({
      geometry: {
        type: "LineString",
        coordinates: routeA.geometry.coordinates,
      },
    });
    expect(maplibreMockState.markers).toHaveLength(4);

    const sourceCalls = map.addSource.mock.calls.length;
    const layerCalls = map.addLayer.mock.calls.length;
    const sourceLookupCalls = map.getSource.mock.calls.length;
    view.rerender(
      <TripMap
        planResponse={response}
        activeRoute={routeB}
        selectedStopSequence={null}
        onSelectStop={selectStop}
      />,
    );

    await waitFor(() => expect(map.moveLayer).toHaveBeenCalledWith("route-r2-line"));
    expect(map.addSource).toHaveBeenCalledTimes(sourceCalls);
    expect(map.addLayer).toHaveBeenCalledTimes(layerCalls);
    expect(map.getSource).toHaveBeenCalledTimes(sourceLookupCalls);
    expect(map.setPaintProperty).toHaveBeenCalled();
  });

  it("uses native [longitude, latitude] coordinates and includes panel padding", async () => {
    renderMap();
    const map = maplibreMockState.maps[0];

    await waitFor(() => expect(map.fitBounds).toHaveBeenCalled());
    expect(map.sources.get("route-r1")?.data).toMatchObject({
      geometry: {
        coordinates: [
          [-74.006, 40.7128],
          [-81.6, 41.5],
          [-87.6298, 41.8781],
        ],
      },
    });
    expect(map.fitBounds.mock.calls[0][1]).toMatchObject({
      padding: { left: 412 },
      maxZoom: 12,
    });
  });

  it("renders a WebGL fallback when neither WebGL context is available", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

    renderMap();

    expect(screen.getByRole("status")).toHaveTextContent("This map needs WebGL.");
    expect(maplibreMockState.maps).toHaveLength(0);
  });

  it("shows a basemap notice when MapLibre reports a load error", async () => {
    renderMap();
    const map = maplibreMockState.maps[0];
    act(() => map.emit("error"));

    expect(await screen.findByText("Basemap unavailable.")).toBeInTheDocument();
    await waitFor(() => expect(map.setStyle).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(map.addSource).toHaveBeenCalledTimes(4));
    expect(map.layers).toHaveLength(4);
  });
});
