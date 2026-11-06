import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FuelPlanPanel } from "../features/fuel-plan/FuelPlanPanel";
import type { DrivingRoute } from "../features/route-planner/types";

describe("FuelPlanPanel Component", () => {
  it("renders empty state when route is null", () => {
    render(
      <FuelPlanPanel
        route={null}
        selectedStopSequence={null}
        onSelectStop={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/Enter an origin and destination to calculate the optimal refueling plan/i),
    ).toBeInTheDocument();
  });

  it("renders metrics and stop schedule when route is provided", async () => {
    const user = userEvent.setup();
    const handleSelectStop = vi.fn();

    const mockRoute: DrivingRoute = {
      id: "r1",
      rank: 1,
      is_recommended: true,
      summary: {
        distance_miles: 789.2,
        duration_minutes: 740,
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [-74.006, 40.7128],
          [-87.6298, 41.8781],
        ],
      },
      fuel_plan: {
        status: "ok",
        origin_price_source: "nearest_station",
        stops: [
          {
            sequence: 1,
            kind: "origin_fill",
            station: {
              id: 101,
              opis_id: 101,
              name: "Pilot Travel Center #412",
              address: "123 Highway St",
              city: "Allentown",
              state: "PA",
              lat: 40.6,
              lon: -75.47,
              position_precision: "place_centroid",
            },
            route_mile: 0.0,
            offset_miles: 0.5,
            detour_miles: 1.0,
            arrival_fuel_gal: 0.0,
            gallons_bought: 50.0,
            price_per_gal: 3.299,
            cost_usd: 164.95,
            fuel_after_gal: 50.0,
            eta_minutes_from_start: 0,
          },
          {
            sequence: 2,
            kind: "en_route",
            station: {
              id: 202,
              opis_id: 202,
              name: "Love's Travel Stop #512",
              address: "456 Turnpike Rd",
              city: "Youngstown",
              state: "OH",
              lat: 41.1,
              lon: -80.65,
              position_precision: "place_centroid",
            },
            route_mile: 380.0,
            offset_miles: 1.2,
            detour_miles: 2.4,
            arrival_fuel_gal: 12.0,
            gallons_bought: 38.0,
            price_per_gal: 3.199,
            cost_usd: 121.56,
            fuel_after_gal: 50.0,
            eta_minutes_from_start: 360,
          },
        ],
        totals: {
          total_fuel_cost_usd: 286.51,
          fuel_consumed_gal: 78.92,
          fuel_purchased_gal: 88.0,
          leftover_gal: 9.08,
          avg_price_per_gal: 3.256,
          cost_per_mile_usd: 0.363,
          num_stops: 2,
          extra_detour_miles: 3.4,
        },
      },
      weather: {
        status: "ok",
        risk_level: "none",
        summary: "Clear weather",
        samples: [],
      },
    };

    render(
      <FuelPlanPanel
        route={mockRoute}
        selectedStopSequence={null}
        onSelectStop={handleSelectStop}
      />,
    );

    // Verify key metrics
    expect(screen.getByText("$286.51")).toBeInTheDocument();
    expect(screen.getByText("789.2 mi")).toBeInTheDocument();
    expect(screen.getByText("Stops Required")).toBeInTheDocument();
    expect(screen.getByText("12h 20m")).toBeInTheDocument();

    // Verify stops rendered
    expect(screen.getByText("Pilot Travel Center #412")).toBeInTheDocument();
    expect(screen.getByText("Origin Fill")).toBeInTheDocument();
    expect(screen.getByText("Love's Travel Stop #512")).toBeInTheDocument();

    // Click second stop
    const stop2 = screen.getByText("Love's Travel Stop #512");
    await user.click(stop2);
    expect(handleSelectStop).toHaveBeenCalledWith(2);
  });
});
