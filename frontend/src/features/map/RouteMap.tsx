import { useEffect } from "react";
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import type { DrivingRoute, PlanResponse } from "../route-planner/types";
import {
  formatCurrency,
  formatGallons,
  formatMiles,
  formatPricePerGal,
} from "../../shared/lib/format";
import "./RouteMap.css";

interface RouteMapProps {
  planResponse: PlanResponse | null;
  activeRoute: DrivingRoute | null;
  selectedStopSequence: number | null;
  onSelectStop: (sequence: number) => void;
}

// Convert GeoJSON coordinates [longitude, latitude] to Leaflet [latitude, longitude]
function convertGeoJsonCoords(coordinates: [number, number][]): [number, number][] {
  return coordinates.map(([lon, lat]) => [lat, lon]);
}

// Component to dynamically fit map viewport to current route geometry
function MapBoundsController({
  activeRoute,
  stops,
}: {
  activeRoute: DrivingRoute | null;
  stops: Array<{ station: { lat: number; lon: number } }>;
}) {
  const map = useMap();

  useEffect(() => {
    if (!activeRoute?.geometry?.coordinates?.length) {
      // Default to Continental US view
      map.setView([39.8283, -98.5795], 4);
      return;
    }

    const points: [number, number][] = activeRoute.geometry.coordinates.map(
      ([lon, lat]) => [lat, lon],
    );

    // Also include fuel station coordinates in the bounding box
    for (const stop of stops) {
      points.push([stop.station.lat, stop.station.lon]);
    }

    if (points.length > 0) {
      const bounds = L.latLngBounds(points);
      map.fitBounds(bounds, {
        padding: [40, 40],
        maxZoom: 14,
        animate: true,
      });
    }
  }, [map, activeRoute, stops]);

  return null;
}

// Create custom DOM icon for Leaflet markers
function createPinIcon(label: string, className: string): L.DivIcon {
  return L.divIcon({
    className: "custom-div-icon",
    html: `<div class="${className}">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -14],
  });
}

export function RouteMap({
  planResponse,
  activeRoute,
  selectedStopSequence,
  onSelectStop,
}: RouteMapProps) {
  const startLoc = planResponse?.start;
  const finishLoc = planResponse?.finish;
  const stops = activeRoute?.fuel_plan?.stops || [];

  // Active route polyline points
  const activePolyline = activeRoute?.geometry
    ? convertGeoJsonCoords(activeRoute.geometry.coordinates)
    : [];

  return (
    <div className="map-viewport-container">
      <MapContainer
        center={[39.8283, -98.5795]}
        zoom={4}
        scrollWheelZoom={true}
        style={{ width: "100%", height: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />

        <MapBoundsController activeRoute={activeRoute} stops={stops} />

        {/* Alternative routes rendered with dashed/muted lines */}
        {planResponse?.routes
          ?.filter((r) => r.id !== activeRoute?.id)
          .map((altRoute) => {
            const coords = convertGeoJsonCoords(altRoute.geometry.coordinates);
            return (
              <Polyline
                key={altRoute.id}
                positions={coords}
                pathOptions={{
                  color: "#94a3b8",
                  weight: 4,
                  opacity: 0.5,
                  dashArray: "6, 8",
                }}
              />
            );
          })}

        {/* Active optimal route rendered with prominent solid line */}
        {activePolyline.length > 0 && (
          <Polyline
            positions={activePolyline}
            pathOptions={{
              color: "#38bdf8",
              weight: 6,
              opacity: 0.9,
            }}
          />
        )}

        {/* Start origin marker */}
        {startLoc && (
          <Marker
            position={[startLoc.lat, startLoc.lon]}
            icon={createPinIcon("A", "marker-pin-origin")}
          >
            <Popup>
              <div className="endpoint-popup-card">
                <div className="endpoint-popup-origin-title">Origin</div>
                <div className="endpoint-popup-label">{startLoc.label}</div>
              </div>
            </Popup>
          </Marker>
        )}

        {/* Finish destination marker */}
        {finishLoc && (
          <Marker
            position={[finishLoc.lat, finishLoc.lon]}
            icon={createPinIcon("B", "marker-pin-finish")}
          >
            <Popup>
              <div className="endpoint-popup-card">
                <div className="endpoint-popup-dest-title">Destination</div>
                <div className="endpoint-popup-label">{finishLoc.label}</div>
              </div>
            </Popup>
          </Marker>
        )}

        {/* Fuel stop markers */}
        {activeRoute?.fuel_plan?.stops?.map((stop) => {
          const isSelected = stop.sequence === selectedStopSequence;
          const pinClass = `marker-pin-stop ${isSelected ? "marker-pin-stop-active" : ""}`;
          return (
            <Marker
              key={stop.sequence}
              position={[stop.station.lat, stop.station.lon]}
              icon={createPinIcon(String(stop.sequence), pinClass)}
              eventHandlers={{
                click: () => onSelectStop(stop.sequence),
              }}
            >
              <Popup>
                <div className="stop-popup-card">
                  <div className="stop-popup-header">
                    <span className="stop-popup-title">{stop.station.name}</span>
                    <span className="stop-popup-seq">Stop #{stop.sequence}</span>
                  </div>

                  <div className="stop-popup-meta">
                    {stop.station.address ? `${stop.station.address}, ` : ""}
                    {stop.station.city}, {stop.station.state}
                  </div>

                  <div className="stop-popup-grid">
                    <div className="stop-popup-stat">
                      <span className="stop-popup-label">Purchase</span>
                      <span className="stop-popup-val">
                        {formatGallons(stop.gallons_bought)}
                      </span>
                    </div>
                    <div className="stop-popup-stat">
                      <span className="stop-popup-label">Fuel Price</span>
                      <span className="stop-popup-val">
                        {formatPricePerGal(stop.price_per_gal)}
                      </span>
                    </div>
                    <div className="stop-popup-stat">
                      <span className="stop-popup-label">Route Mile</span>
                      <span className="stop-popup-val">
                        {formatMiles(stop.route_mile)}
                      </span>
                    </div>
                    <div className="stop-popup-stat">
                      <span className="stop-popup-label">Detour</span>
                      <span className="stop-popup-val">
                        +{formatMiles(stop.detour_miles)}
                      </span>
                    </div>
                  </div>

                  <div className="stop-popup-cost">
                    Stop Cost: {formatCurrency(stop.cost_usd)}
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      <div className="map-attribution-pill">
        RouteIQ Engine &bull; OSRM &bull; Nominatim &bull; Open-Meteo
      </div>
    </div>
  );
}
