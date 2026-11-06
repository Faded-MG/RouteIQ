import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ComparisonTable } from "../features/route-comparison/ComparisonTable";
import type {
  ComparisonRow,
  RecommendationInfo,
} from "../features/route-planner/types";

describe("ComparisonTable Component", () => {
  const mockRecommendation: RecommendationInfo = {
    reason: "lowest_cost",
    considered: 2,
    discarded: [],
  };

  const mockComparison: ComparisonRow[] = [
    {
      route_id: "r1",
      distance_miles: 789.2,
      duration_minutes: 740,
      total_fuel_cost_usd: 286.51,
      num_stops: 2,
      avg_price_per_gal: 3.256,
      weather_risk: "low",
      cost_delta_vs_recommended_usd: 0.0,
      duration_delta_minutes: 0,
    },
    {
      route_id: "r2",
      distance_miles: 820.5,
      duration_minutes: 770,
      total_fuel_cost_usd: 298.12,
      num_stops: 2,
      avg_price_per_gal: 3.312,
      weather_risk: "moderate",
      cost_delta_vs_recommended_usd: 11.61,
      duration_delta_minutes: 30,
    },
  ];

  it("returns null if comparison list is empty", () => {
    const { container } = render(
      <ComparisonTable
        comparison={[]}
        recommendation={mockRecommendation}
        selectedRouteId="r1"
        recommendedRouteId="r1"
        onSelectRoute={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders routes, deltas, and recommendation explanation", async () => {
    const user = userEvent.setup();
    const handleSelectRoute = vi.fn();

    render(
      <ComparisonTable
        comparison={mockComparison}
        recommendation={mockRecommendation}
        selectedRouteId="r1"
        recommendedRouteId="r1"
        onSelectRoute={handleSelectRoute}
      />,
    );

    expect(screen.getByText(/Route Alternatives \(2\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Selected route strictly minimizes total fuel expenditure across all reachable station corridors/i,
      ),
    ).toBeInTheDocument();

    expect(screen.getByText("R1")).toBeInTheDocument();
    expect(screen.getByText("Best")).toBeInTheDocument();
    expect(screen.getByText("$286.51")).toBeInTheDocument();

    expect(screen.getByText("R2")).toBeInTheDocument();
    expect(screen.getByText("+$11.61")).toBeInTheDocument();

    // Click on R2 row
    await user.click(screen.getByText("R2"));
    expect(handleSelectRoute).toHaveBeenCalledWith("r2");
  });
});
