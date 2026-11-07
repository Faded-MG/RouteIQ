import { useEffect, useRef, useState } from "react";
import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
} from "maplibre-gl";
import type {
  GeoJSONSource,
  LngLatBoundsLike,
  Map as MapLibreMapInstance,
} from "maplibre-gl";
import type { DrivingRoute, FuelStop, PlanResponse } from "../route-planner/types";
import { formatCurrency, formatGallons, formatPricePerGal } from "../../shared/lib/format";
import { strings } from "../../shared/strings";
import { readTheme } from "./readTheme";
import "./TripMap.css";

interface TripMapProps {
  planResponse: PlanResponse | null;
  activeRoute: DrivingRoute | null;
  selectedStopSequence: number | null;
  onSelectStop: (sequence: number) => void;
  routeProgress?: Record<string, number>;
  reducedMotion?: boolean;
}

interface CameraPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

const DEFAULT_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const ROUTE_SOURCE_PREFIX = "route-";

function routeSourceId(routeId: string): string {
  return `${ROUTE_SOURCE_PREFIX}${routeId}`;
}

function routeCasingId(routeId: string): string {
  return `${routeSourceId(routeId)}-casing`;
}

function routeLineId(routeId: string): string {
  return `${routeSourceId(routeId)}-line`;
}

function featureForRoute(route: DrivingRoute, progress: number) {
  const coordinates = route.geometry.coordinates;
  const visibleCount =
    progress >= 1 ? coordinates.length : Math.max(2, Math.ceil(coordinates.length * progress));
  return {
    type: "Feature" as const,
    properties: { routeId: route.id },
    geometry: {
      type: "LineString" as const,
      coordinates: coordinates.slice(0, visibleCount),
    },
  };
}

function routeColor(route: DrivingRoute): string {
  const index = Math.max(0, Math.min(2, route.rank - 1));
  return readTheme().routeColors[index];
}

export function getCameraPadding(): CameraPadding {
  const mobile =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 767px)").matches;
  if (mobile) {
    const sheet = document.querySelector<HTMLElement>(".route-planner-panel");
    const sheetHeight = sheet?.getBoundingClientRect().height || 120;
    return { top: 24, right: 24, bottom: sheetHeight + 16, left: 24 };
  }

  const panel = document.querySelector<HTMLElement>(".app-controls-pane");
  const panelWidth = panel?.getBoundingClientRect().width || 380;
  return { top: 24, right: 24, bottom: 24, left: panelWidth + 32 };
}

function canUseWebGL(): boolean {
  const canvas = document.createElement("canvas");
  try {
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function stopPopup(stop: FuelStop): HTMLElement {
  const content = document.createElement("div");
  content.className = "map-stop-popup";

  const name = document.createElement("strong");
  name.textContent = stop.station.name;
  const location = document.createElement("span");
  location.textContent = `${stop.station.city}, ${stop.station.state}`;
  const price = document.createElement("span");
  price.textContent = `${strings.map.fuelPrice}: ${formatPricePerGal(stop.price_per_gal)}`;
  const gallons = document.createElement("span");
  gallons.textContent = `${strings.map.gallons}: ${formatGallons(stop.gallons_bought)}`;
  const cost = document.createElement("span");
  cost.textContent = `${strings.map.cost}: ${formatCurrency(stop.cost_usd)}`;

  content.append(name, location, price, gallons, cost);
  return content;
}

function markerElement(label: string, markerType: string, description: string): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `map-marker map-marker--${markerType}`;
  element.textContent = label;
  element.setAttribute("aria-label", description);
  return element;
}

function routeBounds(route: DrivingRoute, response: PlanResponse): LngLatBoundsLike | null {
  const points: [number, number][] = [
    ...route.geometry.coordinates,
    [response.start.lon, response.start.lat],
    [response.finish.lon, response.finish.lat],
    ...route.fuel_plan.stops.map(
      (stop): [number, number] => [stop.station.lon, stop.station.lat],
    ),
  ];
  if (points.length === 0) return null;

  let minLon = points[0][0];
  let minLat = points[0][1];
  let maxLon = points[0][0];
  let maxLat = points[0][1];
  for (const [lon, lat] of points.slice(1)) {
    minLon = Math.min(minLon, lon);
    minLat = Math.min(minLat, lat);
    maxLon = Math.max(maxLon, lon);
    maxLat = Math.max(maxLat, lat);
  }
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ];
}

export function TripMap({
  planResponse,
  activeRoute,
  selectedStopSequence,
  onSelectStop,
  routeProgress,
  reducedMotion = false,
}: TripMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMapInstance | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const stopMarkerElementsRef = useRef(
    new Map<HTMLButtonElement, { routeId: string; sequence: number }>(),
  );
  const fallbackStyleAppliedRef = useRef(false);
  const attributionRef = useRef<AttributionControl | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [styleRevision, setStyleRevision] = useState(0);
  const [webglAvailable, setWebglAvailable] = useState(true);
  const [styleUnavailable, setStyleUnavailable] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!canUseWebGL()) {
      setWebglAvailable(false);
      return;
    }

    const map = new MapLibreMap({
      container: containerRef.current,
      style: import.meta.env.VITE_MAP_STYLE_URL || DEFAULT_STYLE_URL,
      center: [-98.5795, 39.8283],
      zoom: 3.2,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false, showZoom: true }), "top-right");

    const handleLoad = () => setMapReady(true);
    const handleStyleLoad = () => {
      setMapReady(true);
      setStyleRevision((revision) => revision + 1);
    };
    const handleError = () => {
      setStyleUnavailable(true);
      if (fallbackStyleAppliedRef.current) return;
      fallbackStyleAppliedRef.current = true;
      setMapReady(false);
      map.setStyle({
        version: 8,
        sources: {},
        layers: [
          {
            id: "route-map-background",
            type: "background",
            paint: { "background-color": readTheme().backgroundColor },
          },
        ],
      });
    };
    const resizeMap = () => map.resize();
    map.on("load", handleLoad);
    map.on("style.load", handleStyleLoad);
    map.on("error", handleError);
    window.addEventListener("resize", resizeMap);
    window.addEventListener("transitionend", resizeMap);

    return () => {
      window.removeEventListener("resize", resizeMap);
      window.removeEventListener("transitionend", resizeMap);
      map.off("load", handleLoad);
      map.off("style.load", handleStyleLoad);
      map.off("error", handleError);
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      stopMarkerElementsRef.current.clear();
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !planResponse) return;

    const theme = readTheme();
    for (const route of planResponse.routes) {
      const sourceId = routeSourceId(route.id);
      const existingSource = map.getSource(sourceId);
      const routeFeature = featureForRoute(route, routeProgress?.[route.id] ?? 1);
      if (!existingSource) {
        map.addSource(sourceId, {
          type: "geojson",
          data: routeFeature,
        });
        map.addLayer({
          id: routeCasingId(route.id),
          type: "line",
          source: sourceId,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": theme.surfaceColor,
            "line-width": 9,
            "line-opacity": 0.9,
          },
        });
        map.addLayer({
          id: routeLineId(route.id),
          type: "line",
          source: sourceId,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": routeColor(route),
            "line-width": 4,
            "line-opacity": 0.45,
          },
        });
      } else if (existingSource.type === "geojson") {
        (existingSource as GeoJSONSource).setData(routeFeature);
      }
    }
  }, [mapReady, planResponse, routeProgress, styleRevision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !planResponse) return;
    const selectedId = activeRoute?.id ?? planResponse.recommended_route_id;
    for (const route of planResponse.routes) {
      const selected = route.id === selectedId;
      map.setPaintProperty(routeCasingId(route.id), "line-width", selected ? 9 : 6);
      map.setPaintProperty(routeLineId(route.id), "line-color", routeColor(route));
      map.setPaintProperty(routeLineId(route.id), "line-width", selected ? 6 : 4);
      map.setPaintProperty(routeLineId(route.id), "line-opacity", selected ? 1 : 0.45);
    }
    const selectedRoute = planResponse.routes.find((route) => route.id === selectedId);
    if (selectedRoute) {
      map.moveLayer(routeCasingId(selectedRoute.id));
      map.moveLayer(routeLineId(selectedRoute.id));
    }
  }, [activeRoute?.id, mapReady, planResponse, styleRevision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (attributionRef.current) {
      map.removeControl(attributionRef.current);
    }
    attributionRef.current = new AttributionControl({
      compact: true,
      customAttribution: planResponse?.meta.attribution ?? [],
    });
    map.addControl(attributionRef.current, "bottom-right");
  }, [mapReady, planResponse?.meta.attribution, styleRevision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !planResponse || !activeRoute) return;

    const bounds = routeBounds(activeRoute, planResponse);
    if (bounds) {
      map.fitBounds(bounds, {
        padding: getCameraPadding(),
        duration: reducedMotion ? 0 : 800,
        maxZoom: 12,
      });
    }
  }, [activeRoute, mapReady, planResponse, reducedMotion, styleRevision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !planResponse) return;

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    const { start, finish } = planResponse;
    markersRef.current.push(
      new Marker({ element: markerElement("A", "start", `Start: ${start.label}`) })
        .setLngLat([start.lon, start.lat])
        .addTo(map),
      new Marker({ element: markerElement("B", "finish", `Finish: ${finish.label}`) })
        .setLngLat([finish.lon, finish.lat])
        .addTo(map),
    );

    for (const route of planResponse.routes) {
      for (const stop of route.fuel_plan.stops) {
        const element = markerElement(
          String(stop.sequence),
          "stop",
          `${strings.map.stop} ${stop.sequence}: ${stop.station.name}`,
        );
        element.dataset.routeId = route.id;
        element.dataset.stopSequence = String(stop.sequence);
        element.style.display = route.id === activeRoute?.id ? "" : "none";
        const marker = new Marker({ element })
          .setLngLat([stop.station.lon, stop.station.lat])
          .setPopup(new Popup({ closeButton: true, closeOnClick: true }).setDOMContent(stopPopup(stop)))
          .addTo(map);
        element.addEventListener("click", () => onSelectStop(stop.sequence));
        markersRef.current.push(marker);
        stopMarkerElementsRef.current.set(element, {
          routeId: route.id,
          sequence: stop.sequence,
        });
      }
    }
  }, [mapReady, onSelectStop, planResponse, styleRevision]);

  useEffect(() => {
    const activeRouteId = activeRoute?.id;
    for (const [element, marker] of stopMarkerElementsRef.current) {
      const { routeId, sequence } = marker;
      element.style.display = routeId === activeRouteId ? "" : "none";
      element.classList.toggle(
        "map-marker--selected",
        routeId === activeRouteId && sequence === selectedStopSequence,
      );
    }
  }, [activeRoute?.id, selectedStopSequence]);

  if (!webglAvailable) {
    return (
      <div className="trip-map__fallback" role="status">
        {strings.map.unavailable}
      </div>
    );
  }

  return (
    <div className="trip-map">
      <div className="trip-map__canvas" ref={containerRef} aria-label="Route map" />
      {styleUnavailable && (
        <div className="trip-map__notice" role="status">
          {strings.map.basemapUnavailable}
        </div>
      )}
    </div>
  );
}
