import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RoutePlannerForm } from "../features/route-planner/RoutePlannerForm";

describe("RoutePlannerForm Component", () => {
  it("renders with default values and inputs", () => {
    render(
      <RoutePlannerForm
        onSubmit={vi.fn()}
        isLoading={false}
        errorMessage={null}
      />,
    );

    expect(screen.getByLabelText(/Origin/i)).toHaveValue("New York, NY");
    expect(screen.getByLabelText(/Destination/i)).toHaveValue("Chicago, IL");
    expect(screen.getByLabelText(/Initial Fuel/i)).toHaveValue(0);
    expect(screen.getByRole("button", { name: /Calculate Optimal Route/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /NYC → Chicago/i })).toBeInTheDocument();
  });

  it("submits form data when Calculate button is clicked", async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();

    render(
      <RoutePlannerForm
        onSubmit={handleSubmit}
        isLoading={false}
        errorMessage={null}
      />,
    );

    const submitBtn = screen.getByRole("button", { name: /Calculate Optimal Route/i });
    await user.click(submitBtn);

    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith({
      start: { query: "New York, NY" },
      finish: { query: "Chicago, IL" },
      options: {
        start_fuel_gal: 0,
        include_weather: true,
        alternatives: true,
      },
    });
  });

  it("applies preset destination when clicked", async () => {
    const user = userEvent.setup();

    render(
      <RoutePlannerForm
        onSubmit={vi.fn()}
        isLoading={false}
        errorMessage={null}
      />,
    );

    const coastToCoastBtn = screen.getByRole("button", {
      name: /Coast to Coast/i,
    });
    await user.click(coastToCoastBtn);

    expect(screen.getByLabelText(/Origin/i)).toHaveValue("Los Angeles, CA");
    expect(screen.getByLabelText(/Destination/i)).toHaveValue("New York, NY");
  });

  it("displays error banner when errorMessage is provided", () => {
    render(
      <RoutePlannerForm
        onSubmit={vi.fn()}
        isLoading={false}
        errorMessage="Could not find continental US location for start: Atlantis"
      />,
    );

    expect(
      screen.getByText(/Could not find continental US location for start: Atlantis/i),
    ).toBeInTheDocument();
  });

  it("disables inputs and shows loading state when isLoading is true", () => {
    render(
      <RoutePlannerForm
        onSubmit={vi.fn()}
        isLoading={true}
        errorMessage={null}
      />,
    );

    expect(screen.getByRole("button", { name: /Optimizing Fuel Stops/i })).toBeDisabled();
    expect(screen.getByLabelText(/Origin/i)).toBeDisabled();
    expect(screen.getByLabelText(/Destination/i)).toBeDisabled();
  });
});
