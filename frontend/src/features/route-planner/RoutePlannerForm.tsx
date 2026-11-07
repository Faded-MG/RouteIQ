import { type FormEvent, useState } from "react";
import type { PlanRequest } from "./types";
import "./RoutePlannerForm.css";

interface RoutePlannerFormProps {
  onSubmit: (request: PlanRequest) => void;
  isLoading: boolean;
  errorMessage: string | null;
}

interface FormErrors {
  start?: string;
  finish?: string;
  startFuelGal?: string;
}

const EXAMPLE_ROUTES = [
  { start: "New York, NY", finish: "Chicago, IL", label: "NYC → Chicago" },
  { start: "Los Angeles, CA", finish: "New York, NY", label: "Coast to Coast (LA → NYC)" },
  { start: "Philadelphia, PA", finish: "New York, NY", label: "Short Trip (PHL → NYC)" },
] as const;

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
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});

  const validate = () => {
    const nextErrors: FormErrors = {};
    const trimmedStart = startQuery.trim();
    const trimmedFinish = finishQuery.trim();

    if (trimmedStart.length < 3 || trimmedStart.length > 200) {
      nextErrors.start = "Start must be 3–200 characters.";
    }

    if (trimmedFinish.length < 3 || trimmedFinish.length > 200) {
      nextErrors.finish = "Finish must be 3–200 characters.";
    }

    const fuelValue = Number.parseFloat(startFuelGal);
    if (Number.isNaN(fuelValue) || fuelValue < 0 || fuelValue > 50) {
      nextErrors.startFuelGal = "Starting fuel must be between 0 and 50 gallons.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    if (!validate()) {
      return;
    }

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
    setErrors({});
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

      <form onSubmit={handleSubmit} className="planner-form" noValidate>
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
            onChange={(e) => {
              setStartQuery(e.target.value);
              if (errors.start) {
                setErrors((current) => ({ ...current, start: undefined }));
              }
            }}
            disabled={isLoading}
            autoComplete="off"
            aria-describedby="start-hint"
            aria-invalid={Boolean(errors.start)}
          />
          <span id="start-hint" className="form-hint">
            Continental US location (geocoded via Nominatim)
          </span>
          {errors.start && <span className="form-error-text">{errors.start}</span>}
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
            onChange={(e) => {
              setFinishQuery(e.target.value);
              if (errors.finish) {
                setErrors((current) => ({ ...current, finish: undefined }));
              }
            }}
            disabled={isLoading}
            autoComplete="off"
            aria-describedby="finish-hint"
            aria-invalid={Boolean(errors.finish)}
          />
          <span id="finish-hint" className="form-hint">
            Must be at least 1 mile from origin
          </span>
          {errors.finish && <span className="form-error-text">{errors.finish}</span>}
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
              onChange={(e) => {
                setStartFuelGal(e.target.value);
                if (errors.startFuelGal) {
                  setErrors((current) => ({ ...current, startFuelGal: undefined }));
                }
              }}
              disabled={isLoading}
              aria-invalid={Boolean(errors.startFuelGal)}
            />
            {errors.startFuelGal && (
              <span className="form-error-text">{errors.startFuelGal}</span>
            )}
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

        <div className="advanced-controls">
          <button
            type="button"
            className="advanced-toggle"
            onClick={() => setShowAdvanced((value) => !value)}
            disabled={isLoading}
          >
            {showAdvanced ? "Hide advanced" : "Advanced"}
          </button>
        </div>

        {showAdvanced && (
          <div className="advanced-panel">
            <label htmlFor="starting-fuel-advanced" className="form-label">
              Starting fuel (gal)
            </label>
            <input
              id="starting-fuel-advanced"
              type="number"
              className="form-input"
              min="0"
              max="50"
              step="0.5"
              value={startFuelGal}
              onChange={(e) => setStartFuelGal(e.target.value)}
              disabled={isLoading}
            />
          </div>
        )}

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
          {EXAMPLE_ROUTES.map((route) => (
            <button
              type="button"
              key={route.label}
              className="preset-btn"
              onClick={() => applyPreset(route.start, route.finish)}
              disabled={isLoading}
            >
              {route.label}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
