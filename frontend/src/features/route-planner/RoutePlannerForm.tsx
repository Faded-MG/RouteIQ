import { type FormEvent, useState } from "react";
import type { PlanRequest } from "./types";
import "./RoutePlannerForm.css";

interface RoutePlannerFormProps {
  onSubmit: (request: PlanRequest) => void;
  isLoading: boolean;
  errorMessage: string | null;
}

export function RoutePlannerForm({
  onSubmit,
  isLoading,
  errorMessage,
}: RoutePlannerFormProps) {
  const [startQuery, setStartQuery] = useState("New York, NY");
  const [finishQuery, setFinishQuery] = useState("Chicago, IL");
  const [startFuelGal, setStartFuelGal] = useState("0");
  const [includeWeather, setIncludeWeather] = useState(true);
  const [allowAlternatives, setAllowAlternatives] = useState(true);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!startQuery.trim() || !finishQuery.trim() || isLoading) return;

    const request: PlanRequest = {
      start: { query: startQuery.trim() },
      finish: { query: finishQuery.trim() },
      options: {
        start_fuel_gal: Number.parseFloat(startFuelGal) || 0.0,
        include_weather: includeWeather,
        alternatives: allowAlternatives,
      },
    };

    onSubmit(request);
  };

  const applyPreset = (start: string, finish: string) => {
    setStartQuery(start);
    setFinishQuery(finish);
  };

  return (
    <div className="planner-form-card">
      <div className="planner-header">
        <div className="planner-title">
          <span>Route Parameters</span>
          <span className="badge-spec">500 mi &bull; 10 MPG</span>
        </div>
        <p className="planner-subtitle">
          Dynamic programming optimizer finds minimal fuel dollar expenditure over the 500-mile vehicle range.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="planner-form">
        <div className="form-group">
          <label htmlFor="start-input" className="form-label">
            <span className="label-dot-start" aria-hidden="true" />
            <span>Origin (US City or Address)</span>
          </label>
          <input
            id="start-input"
            type="text"
            required
            className="form-input"
            placeholder="e.g. New York, NY"
            value={startQuery}
            onChange={(e) => setStartQuery(e.target.value)}
            disabled={isLoading}
            autoComplete="off"
            aria-describedby="start-hint"
          />
          <span id="start-hint" className="form-hint">
            Continental US location (geocoded via Nominatim)
          </span>
        </div>

        <div className="form-group">
          <label htmlFor="finish-input" className="form-label">
            <span className="label-dot-finish" aria-hidden="true" />
            <span>Destination (US City or Address)</span>
          </label>
          <input
            id="finish-input"
            type="text"
            required
            className="form-input"
            placeholder="e.g. Chicago, IL"
            value={finishQuery}
            onChange={(e) => setFinishQuery(e.target.value)}
            disabled={isLoading}
            autoComplete="off"
            aria-describedby="finish-hint"
          />
          <span id="finish-hint" className="form-hint">
            Must be at least 1 mile from origin
          </span>
        </div>

        <div className="form-row-two-col">
          <div className="form-group">
            <label htmlFor="fuel-input" className="form-label">
              Initial Fuel (Gal)
            </label>
            <input
              id="fuel-input"
              type="number"
              min="0"
              max="50"
              step="0.5"
              className="form-input"
              value={startFuelGal}
              onChange={(e) => setStartFuelGal(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="form-options-column">
            <label className="form-checkbox-label">
              <input
                type="checkbox"
                checked={allowAlternatives}
                onChange={(e) => setAllowAlternatives(e.target.checked)}
                disabled={isLoading}
                className="form-checkbox-input"
              />
              <span>Route Alternatives</span>
            </label>
            <label className="form-checkbox-label">
              <input
                type="checkbox"
                checked={includeWeather}
                onChange={(e) => setIncludeWeather(e.target.checked)}
                disabled={isLoading}
                className="form-checkbox-input"
              />
              <span>Live Weather Risk</span>
            </label>
          </div>
        </div>

        {errorMessage && (
          <div className="form-error-banner" role="alert">
            <svg
              className="form-error-icon"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <span>{errorMessage}</span>
          </div>
        )}

        <button
          type="submit"
          className="form-submit-btn"
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <svg
                className="form-spinner-icon"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Optimizing Fuel Stops...</span>
            </>
          ) : (
            <span>Calculate Optimal Route</span>
          )}
        </button>

        <div className="preset-pills">
          <span className="preset-label">Presets:</span>
          <button
            type="button"
            className="preset-btn"
            onClick={() => applyPreset("New York, NY", "Chicago, IL")}
            disabled={isLoading}
          >
            NYC &rarr; Chicago
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={() => applyPreset("Los Angeles, CA", "New York, NY")}
            disabled={isLoading}
          >
            Coast to Coast (LA &rarr; NYC)
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={() => applyPreset("Philadelphia, PA", "New York, NY")}
            disabled={isLoading}
          >
            Short Trip (PHL &rarr; NYC)
          </button>
        </div>
      </form>
    </div>
  );
}
