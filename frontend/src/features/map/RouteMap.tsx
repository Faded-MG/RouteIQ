import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap } from "maplibre-gl";
import type { DrivingRoute, PlanResponse } from "../route-planner/types";
import "./RouteMap.css";

interface RouteMapProps {
  planResponse: PlanResponse | null;
  activeRoute: DrivingRoute | null;
  selectedStopSequence: number | null;
  onSelectStop: (sequence: number) => void;
}

const DEFAULT_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

export function RouteMap({
  planResponse,
  activeRoute,
  selectedStopSequence,
}: RouteMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const [styleUnavailable, setStyleUnavailable] = useState(false);

  useEffect(() => {
    if (!mapContainer.current) return;

    const map = new MapLibreMap({
      container: mapContainer.current,
      style: import.meta.env.VITE_MAP_STYLE_URL || DEFAULT_STYLE_URL,
      center: [-98.5795, 39.8283],
      zoom: 3.2,
    });

    const handleError = () => setStyleUnavailable(true);
    map.on("error", handleError);

    return () => {
      map.off("error", handleError);
      map.remove();
    };
  }, []);

  return (
    <div
      className="map-viewport-container"
      data-route-count={planResponse?.routes.length ?? 0}
      data-active-route={activeRoute?.id ?? ""}
      data-selected-stop={selectedStopSequence ?? ""}
    >
      <div className="map-canvas" ref={mapContainer} aria-label="Route map" />
      {styleUnavailable && (
        <div className="map-style-error" role="status">
          Basemap unavailable. Route planning remains available.
        </div>
      )}
    </div>
  );
}
