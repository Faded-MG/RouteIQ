/**
 * TypeScript domain types mirroring docs/API_SPEC.md exactly.
 */

export interface LocationInput {
  query?: string;
  lat?: number;
  lon?: number;
}

export interface PlanOptionsInput {
  start_fuel_gal?: number;
  departure_time?: string;
  include_weather?: boolean;
  alternatives?: boolean;
}

export interface PlanRequest {
  start: LocationInput;
  finish: LocationInput;
  options?: PlanOptionsInput;
}

export interface ResolvedLocation {
  label: string;
  lat: number;
  lon: number;
  source: "geocoded" | "coordinates";
  cached: boolean;
}

export interface StationInfo {
  id: number;
  opis_id: number;
  name: string;
  address: string;
  city: string;
  state: string;
  lat: number;
  lon: number;
  position_precision: string;
}

export interface FuelStop {
  sequence: number;
  kind: "origin_fill" | "en_route";
  station: StationInfo;
  route_mile: number;
  offset_miles: number;
  detour_miles: number;
  arrival_fuel_gal: number;
  gallons_bought: number;
  price_per_gal: number;
  cost_usd: number;
  fuel_after_gal: number;
  eta_minutes_from_start: number;
}

export interface PlanTotals {
  total_fuel_cost_usd: number;
  fuel_consumed_gal: number;
  fuel_purchased_gal: number;
  leftover_gal: number;
  avg_price_per_gal: number;
  cost_per_mile_usd: number;
  num_stops: number;
  extra_detour_miles: number;
}

export interface InfeasibleGap {
  from_mile: number;
  to_mile: number;
  gap_miles: number;
}

export interface FuelPlan {
  status: "ok" | "no_refuel_needed" | "infeasible";
  origin_price_source: string | null;
  stops: FuelStop[];
  totals: PlanTotals | null;
  infeasible?: InfeasibleGap;
}

export interface WeatherSample {
  route_mile: number;
  lat: number;
  lon: number;
  eta: string;
  temperature_f: number | null;
  precipitation_in: number | null;
  wind_mph: number | null;
  gust_mph: number | null;
  visibility_mi: number | null;
  weather_code: number | null;
  condition: string;
  severity: "none" | "low" | "moderate" | "severe";
}

export interface RouteWeather {
  status: "ok" | "partial" | "unavailable" | "disabled";
  risk_level: "none" | "low" | "moderate" | "severe" | null;
  summary: string | null;
  samples: WeatherSample[];
}

export interface RouteSummary {
  distance_miles: number;
  duration_minutes: number;
}

export interface RouteGeometry {
  type: "LineString";
  coordinates: [number, number][]; // [lon, lat]
}

export interface DrivingRoute {
  id: string;
  route_id?: string;
  rank: number;
  is_recommended: boolean;
  summary: RouteSummary;
  geometry: RouteGeometry;
  fuel_plan: FuelPlan;
  weather: RouteWeather;
}

export interface ComparisonRow {
  route_id: string;
  distance_miles: number;
  duration_minutes: number;
  total_fuel_cost_usd: number | null;
  num_stops: number;
  avg_price_per_gal: number | null;
  weather_risk: string | null;
  cost_delta_vs_recommended_usd: number | null;
  duration_delta_minutes: number;
}

export interface RecommendationInfo {
  reason:
    | "lowest_cost"
    | "only_feasible_route"
    | "lowest_cost_avoiding_severe_weather"
    | "lowest_cost_within_duration_limit";
  considered: number;
  discarded: { route_id: string; why: string }[];
}

export interface PlanAssumptions {
  mpg: number;
  max_range_miles: number;
  tank_capacity_gal: number;
  start_fuel_gal: number;
  reserve_gal: number;
  station_corridor_miles: number;
  circuity_factor: number;
  fuel_unit_gal: number;
  leftover_fuel_value_usd: number;
}

export interface PlanMeta {
  external_calls: {
    geocoding: number;
    routing: number;
    weather: number;
  };
  cache: {
    plan: string;
    geocode: string[];
    route: string;
    weather: string;
  };
  timings_ms: {
    total: number;
    geocode: number;
    routing: number;
    matching: number;
    optimization: number;
    weather: number;
  };
  data: {
    station_count: number;
    stations_data_version: string;
    station_position_precision: string;
    price_aggregation: string;
  };
  attribution: string[];
}

export interface PlanResponse {
  request_id: string;
  status: "ok";
  assumptions: PlanAssumptions;
  start: ResolvedLocation;
  finish: ResolvedLocation;
  recommended_route_id: string;
  recommendation: RecommendationInfo;
  routes: DrivingRoute[];
  comparison: ComparisonRow[];
  meta: PlanMeta;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
  error: ApiErrorDetail;
}
