import { formatMiles } from "../../shared/lib/format";
import type { RouteWeather } from "../route-planner/types";
import "./WeatherStrip.css";

interface WeatherStripProps {
  weather: RouteWeather | null | undefined;
}

export function WeatherStrip({ weather }: WeatherStripProps) {
  if (!weather || weather.status === "disabled") {
    return (
      <div className="weather-card">
        <div className="weather-header">
          <span className="weather-title">Route Weather Intelligence</span>
          <span className="weather-status-badge weather-badge-neutral">
            Disabled
          </span>
        </div>
        <p className="weather-disabled-text">
          Weather forecasting disabled in request options.
        </p>
      </div>
    );
  }

  if (weather.status === "unavailable") {
    return (
      <div className="weather-card">
        <div className="weather-header">
          <span className="weather-title">Route Weather Intelligence</span>
          <span className="weather-status-badge weather-badge-neutral">
            Unavailable
          </span>
        </div>
        <p className="weather-unavailable-text">
          Open-Meteo weather data was temporarily unreachable. The optimal fuel plan is completely unaffected.
        </p>
      </div>
    );
  }

  const riskBadgeClass = (() => {
    switch (weather.risk_level) {
      case "severe":
        return "weather-badge-severe";
      case "moderate":
        return "weather-badge-moderate";
      case "low":
        return "weather-badge-low";
      case "none":
      default:
        return "weather-badge-none";
    }
  })();

  return (
    <div className="weather-card">
      <div className="weather-header">
        <span className="weather-title">
          <span>Route Weather Intelligence</span>
        </span>
        <span className={`weather-status-badge ${riskBadgeClass}`}>
          {weather.risk_level ? `${weather.risk_level} Risk` : "Clear"}
        </span>
      </div>

      {weather.summary && (
        <div className="weather-summary-text">
          {weather.summary}
        </div>
      )}

      {weather.samples && weather.samples.length > 0 && (
        <div className="weather-samples-track">
          {weather.samples.map((sample, idx) => {
            const timeStr = sample.eta.length >= 16 ? sample.eta.substring(11, 16) : sample.eta;
            return (
              <div key={idx} className="weather-sample-node">
                <div className="weather-sample-header">
                  <span className="weather-sample-mile">
                    {formatMiles(sample.route_mile)}
                  </span>
                  <span>{timeStr}Z</span>
                </div>

                <div className="weather-sample-condition">
                  {sample.condition}
                </div>

                <div className="weather-sample-footer">
                  <span>{sample.temperature_f != null ? `${sample.temperature_f}°F` : "—"}</span>
                  <span>{sample.wind_mph != null ? `${sample.wind_mph} mph` : "—"}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
