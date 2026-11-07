import { lazy, Suspense } from "react";
import { RoutePlannerForm } from "../features/route-planner/RoutePlannerForm";
import { useRoutePlan } from "../features/route-planner/useRoutePlan";
import { FuelPlanPanel } from "../features/fuel-plan/FuelPlanPanel";
import { ComparisonTable } from "../features/route-comparison/ComparisonTable";
import { WeatherStrip } from "../features/weather/WeatherStrip";
import { ExplainabilityCard } from "../shared/ui/ExplainabilityCard";
import { strings } from "../shared/strings";
import "./App.css";

const TripMap = lazy(() =>
  import("../features/map/TripMap").then((module) => ({ default: module.TripMap })),
);

export function App() {
  const {
    planTrip,
    isLoading,
    errorMessage,
    planData,
    activeRoute,
    selectedRouteId,
    selectRoute,
    selectedStopSequence,
    selectStop,
  } = useRoutePlan();

  return (
    <div className="app-shell">
      {/* Top Application Header */}
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-brand">
            <div className="app-brand-logo" aria-hidden="true">
              R
            </div>
            <div className="app-brand-text">
              <div className="app-brand-title">
                <span>RouteIQ</span>
                <span className="app-brand-tag">v1.0</span>
              </div>
              <span className="app-brand-subtitle">
                Cost-Optimal Fuel Routing &bull; Spotter Assessment
              </span>
            </div>
          </div>

          <div className="app-header-status">
            <div className="app-status-pill">
              <span className="app-status-dot" aria-hidden="true" />
              <span>500 mi Range &bull; 10 MPG &bull; 0.01 Gal Exact DP</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Responsive Grid Layout */}
      <main className="app-main-layout">
        {/* Left Column: Form Controls & Numerical Intelligence */}
        <section className="app-controls-pane" aria-label="Route Planning Controls">
          <RoutePlannerForm
            onSubmit={planTrip}
            isLoading={isLoading}
            errorMessage={errorMessage}
          />

          <FuelPlanPanel
            route={activeRoute}
            selectedStopSequence={selectedStopSequence}
            onSelectStop={selectStop}
          />

          <WeatherStrip weather={activeRoute?.weather} />

          <ExplainabilityCard />
        </section>

        {/* Right Column: Interactive Map & Alternative Corridor Comparison */}
        <section className="app-visualization-pane" aria-label="Map and Route Alternatives">
          <Suspense fallback={<div className="map-loading" role="status">{strings.map.loading}</div>}>
            <TripMap
              planResponse={planData}
              activeRoute={activeRoute}
              selectedStopSequence={selectedStopSequence}
              onSelectStop={selectStop}
            />
          </Suspense>

          {planData?.comparison && planData.comparison.length > 0 && planData.recommendation && (
            <ComparisonTable
              comparison={planData.comparison}
              recommendation={planData.recommendation}
              selectedRouteId={selectedRouteId ?? planData.recommended_route_id}
              recommendedRouteId={planData.recommended_route_id}
              onSelectRoute={selectRoute}
            />
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <div className="app-footer-inner">
          <span className="app-footer-text">
            RouteIQ — Spotter Backend Django Engineer Assessment &bull; Production Full-Stack Build
          </span>
          <span className="app-footer-spec">
            POST /api/v1/plan/ &bull; OSRM &bull; Nominatim &bull; Open-Meteo
          </span>
        </div>
      </footer>
    </div>
  );
}
