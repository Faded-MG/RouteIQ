import {
  formatCurrency,
  formatDuration,
  formatGallons,
  formatMiles,
  formatPricePerGal,
} from "../../shared/lib/format";
import type { DrivingRoute } from "../route-planner/types";
import "./FuelPlanPanel.css";

interface FuelPlanPanelProps {
  route: DrivingRoute | null;
  selectedStopSequence: number | null;
  onSelectStop: (sequence: number) => void;
}

export function FuelPlanPanel({
  route,
  selectedStopSequence,
  onSelectStop,
}: FuelPlanPanelProps) {
  if (!route) {
    return (
      <div className="fuel-plan-empty-card">
        <p className="fuel-plan-empty-text">
          Enter an origin and destination to calculate the optimal refueling plan.
        </p>
      </div>
    );
  }

  const totals = route.fuel_plan.totals;
  const stops = route.fuel_plan.stops || [];

  return (
    <div className="fuel-plan-card">
      <div className="plan-header">
        <span className="plan-title">Optimization Results</span>
        <span className="plan-badge">
          {route.is_recommended ? "Recommended Route" : `Alternative #${route.rank}`}
        </span>
      </div>

      <div className="metrics-summary-grid">
        <div className="metric-item">
          <span className="metric-value-primary">
            {formatCurrency(totals?.total_fuel_cost_usd)}
          </span>
          <span className="metric-label">Total Fuel Cost</span>
        </div>

        <div className="metric-item">
          <span className="metric-value">
            {formatMiles(route.summary.distance_miles)}
          </span>
          <span className="metric-label">Route Distance</span>
        </div>

        <div className="metric-item">
          <span className="metric-value">
            {totals?.num_stops ?? 0}
          </span>
          <span className="metric-label">Stops Required</span>
        </div>

        <div className="metric-item">
          <span className="metric-value">
            {formatDuration(route.summary.duration_minutes)}
          </span>
          <span className="metric-label">Est. Travel Time</span>
        </div>
      </div>

      <div className="plan-aux-summary">
        <span>
          Purchased: <strong>{formatGallons(totals?.fuel_purchased_gal)}</strong> @{" "}
          <strong>{formatPricePerGal(totals?.avg_price_per_gal)}</strong> avg
        </span>
        <span>
          Detour Distance: <strong>+{formatMiles(totals?.extra_detour_miles)}</strong>
        </span>
      </div>

      <div className="stops-section">
        <div className="stops-section-title">
          Refueling Schedule ({stops.length} {stops.length === 1 ? "Stop" : "Stops"})
        </div>

        <div className="stops-scroll-container">
          {stops.map((stop) => {
            const isSelected = stop.sequence === selectedStopSequence;
            return (
              <div
                key={stop.sequence}
                className={`stop-list-item ${isSelected ? "stop-list-item-selected" : ""}`}
                onClick={() => onSelectStop(stop.sequence)}
              >
                <div className="stop-badge-num">{stop.sequence}</div>
                <div className="stop-info-body">
                  <div className="stop-title-row">
                    <span className="stop-station-name">
                      <span>{stop.station.name}</span>
                      {stop.kind === "origin_fill" && (
                        <span className="stop-origin-tag">
                          Origin Fill
                        </span>
                      )}
                    </span>
                    <span className="stop-total-cost">
                      {formatCurrency(stop.cost_usd)}
                    </span>
                  </div>

                  <div className="stop-location-text">
                    {stop.station.address ? `${stop.station.address}, ` : ""}
                    {stop.station.city}, {stop.station.state}
                  </div>

                  <div className="stop-stats-row">
                    <span>
                      Mile: <strong>{formatMiles(stop.route_mile)}</strong>
                    </span>
                    <span>
                      Buy: <strong>{formatGallons(stop.gallons_bought)}</strong>
                    </span>
                    <span>
                      Rate: <strong>{formatPricePerGal(stop.price_per_gal)}</strong>
                    </span>
                    <span>
                      Tank After: <strong>{formatGallons(stop.fuel_after_gal)}</strong>
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
