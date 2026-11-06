import {
  formatCurrency,
  formatDuration,
  formatMiles,
} from "../../shared/lib/format";
import type { ComparisonRow, RecommendationInfo } from "../route-planner/types";
import "./ComparisonTable.css";

interface ComparisonTableProps {
  comparison: ComparisonRow[];
  recommendation: RecommendationInfo;
  selectedRouteId: string;
  recommendedRouteId: string;
  onSelectRoute: (routeId: string) => void;
}

export function ComparisonTable({
  comparison,
  recommendation,
  selectedRouteId,
  recommendedRouteId,
  onSelectRoute,
}: ComparisonTableProps) {
  if (!comparison || comparison.length === 0) return null;

  const reasonExplanation = (() => {
    switch (recommendation.reason) {
      case "lowest_cost_avoiding_severe_weather":
        return "Selected route is cost-optimal while avoiding severe weather alerts detected on alternative corridors.";
      case "lowest_cost_within_duration_limit":
        return "Selected route achieves minimum fuel cost within 125% of the fastest feasible duration.";
      case "only_feasible_route":
        return "Only route with reachable refueling stations under the 500-mile vehicle range constraint.";
      case "lowest_cost":
      default:
        return "Selected route strictly minimizes total fuel expenditure across all reachable station corridors.";
    }
  })();

  return (
    <div className="comparison-card">
      <div className="comparison-header">
        <span className="comparison-title">Route Alternatives ({comparison.length})</span>
        <span className="comparison-count">
          Considered: {recommendation.considered}
        </span>
      </div>

      <div className="recommendation-banner">
        <svg
          className="recommendation-icon"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div>
          <strong className="recommendation-label">Recommendation Decision: </strong>
          <span>{reasonExplanation}</span>
        </div>
      </div>

      <div className="table-responsive-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th className="table-th">Route</th>
              <th className="table-th">Fuel Cost</th>
              <th className="table-th">Cost Delta</th>
              <th className="table-th">Distance</th>
              <th className="table-th">Travel Time</th>
              <th className="table-th">Stops</th>
              <th className="table-th">Weather</th>
            </tr>
          </thead>
          <tbody>
            {comparison.map((row) => {
              const isSelected = row.route_id === selectedRouteId;
              const isRecommended = row.route_id === recommendedRouteId;
              const isInfeasible = row.total_fuel_cost_usd === null;

              return (
                <tr
                  key={row.route_id}
                  className={`table-tr ${isSelected ? "table-tr-active" : ""}`}
                  onClick={() => onSelectRoute(row.route_id)}
                >
                  <td className="table-td">
                    <div className="table-route-id-cell">
                      <span className="table-route-name">{row.route_id.toUpperCase()}</span>
                      {isRecommended && (
                        <span className="table-badge-best">
                          Best
                        </span>
                      )}
                    </div>
                  </td>

                  <td className="table-td-cost">
                    {isInfeasible ? (
                      <span className="table-cost-infeasible">Infeasible</span>
                    ) : (
                      formatCurrency(row.total_fuel_cost_usd)
                    )}
                  </td>

                  <td className="table-td">
                    {isInfeasible ? (
                      "—"
                    ) : row.cost_delta_vs_recommended_usd === 0 ? (
                      <span className="table-delta-zero">$0.00</span>
                    ) : (
                      <span className="table-delta-positive">
                        +{formatCurrency(row.cost_delta_vs_recommended_usd)}
                      </span>
                    )}
                  </td>

                  <td className="table-td">{formatMiles(row.distance_miles)}</td>

                  <td className="table-td">
                    {formatDuration(row.duration_minutes)}
                    {row.duration_delta_minutes !== 0 && (
                      <span className="table-duration-delta">
                        ({row.duration_delta_minutes > 0 ? "+" : ""}
                        {row.duration_delta_minutes}m)
                      </span>
                    )}
                  </td>

                  <td className="table-td">{row.num_stops}</td>

                  <td className="table-td">
                    {row.weather_risk ? (
                      <span
                        className={`weather-tag ${
                          row.weather_risk === "severe"
                            ? "weather-tag-severe"
                            : row.weather_risk === "moderate"
                              ? "weather-tag-moderate"
                              : "weather-tag-low"
                        }`}
                      >
                        {row.weather_risk}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
