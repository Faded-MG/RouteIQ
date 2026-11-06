# API_SPEC.md — FuelRoute API v1

Base path: `/api/v1`. JSON only (`Content-Type: application/json`). No authentication in P0–P2. All timestamps ISO-8601 UTC. Units: miles, gallons, USD, °F, mph, inches. Every response carries `X-Request-ID`.

## 1. Endpoints

| Priority | Method | Path | Purpose |
|---|---|---|---|
| P0 | POST | `/routes/plan` | Plan route(s) and fuel stops, return cost. |
| P1 | GET | `/health/live` | Process liveness (no dependencies). |
| P1 | GET | `/health/ready` | DB reachable, station data loaded. |
| P1 | GET | `/config` | Assumptions (MPG, range, tank, corridor) for the UI. |
| P2 | GET | `/stations` | Paginated stations (debug/map layer). |

`POST` is used for planning because the body is structured and the result is computed (not a cacheable GET resource).

## 2. Status codes

| Code | When |
|---|---|
| 200 | Plan computed (even when weather is unavailable). |
| 400 | Malformed JSON or field validation failure (`VALIDATION_ERROR`). |
| 404 | Unknown path. |
| 405 | Wrong method. |
| 415 | Non-JSON content type. |
| 422 | Request is well-formed but cannot be satisfied: `LOCATION_NOT_FOUND`, `LOCATION_OUTSIDE_US`, `ROUTE_TOO_SHORT`, `ROUTE_NOT_FOUND`, `NO_FEASIBLE_FUEL_PLAN`. |
| 429 | Inbound throttle exceeded (`RATE_LIMITED`); `Retry-After` header. |
| 500 | Bug or failed internal validation (`INTERNAL_ERROR`). |
| 502 | Upstream returned an invalid response (`UPSTREAM_BAD_RESPONSE`). |
| 503 | Upstream unavailable/rate-limited or station data missing (`UPSTREAM_UNAVAILABLE`, `FUEL_DATA_NOT_LOADED`). |
| 504 | Upstream timeout (`UPSTREAM_TIMEOUT`). |

## 3. Error envelope (all non-2xx)

```json
{
  "error": {
    "code": "NO_FEASIBLE_FUEL_PLAN",
    "message": "No refueling plan keeps the vehicle within a 500-mile range on this route.",
    "details": { "largest_gap": { "from_mile": 300.0, "to_mile": 850.0, "gap_miles": 550.0 } },
    "request_id": "7c1f0f0e-9e7a-4a73-9f1c-2f0b1d7d2c11"
  }
}
```

`details` is always an object (may be empty). For `VALIDATION_ERROR`, `details.fields` maps field path → list of messages:
`{"fields": {"start.lat": ["Must be between 24.0 and 49.5."]}}`.

| Code | HTTP | Retryable | Notes |
|---|---|---|---|
| `VALIDATION_ERROR` | 400 | no | |
| `LOCATION_NOT_FOUND` | 422 | no | `details.which = "start"|"finish"`, `details.query`. |
| `LOCATION_OUTSIDE_US` | 422 | no | Geocoded result is outside the contiguous-US bounding box. |
| `ROUTE_TOO_SHORT` | 422 | no | Straight-line distance < 1 mile. |
| `ROUTE_NOT_FOUND` | 422 | no | OSRM `NoRoute` (e.g. no drivable connection). |
| `NO_FEASIBLE_FUEL_PLAN` | 422 | no | Returned only if **every** candidate route is infeasible. |
| `RATE_LIMITED` | 429 | yes | |
| `UPSTREAM_UNAVAILABLE` | 503 | yes | `details.provider`. |
| `UPSTREAM_TIMEOUT` | 504 | yes | `details.provider`. |
| `UPSTREAM_BAD_RESPONSE` | 502 | yes | |
| `FUEL_DATA_NOT_LOADED` | 503 | no | `import_stations` has not been run. |
| `INTERNAL_ERROR` | 500 | no | Includes optimizer self-validation failure. |

## 4. `POST /api/v1/routes/plan`

### 4.1 Request schema

```json
{
  "start":  { "query": "New York, NY" },
  "finish": { "query": "Chicago, IL" },
  "options": {
    "include_weather": true,
    "alternatives": true,
    "start_fuel_gal": 0,
    "departure_time": "2026-11-06T12:00:00Z"
  }
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `start`, `finish` | object | yes | Exactly one form: `{"query": str}` **or** `{"lat": number, "lon": number}`. Both or neither → `VALIDATION_ERROR`. |
| `…query` | string | | 3–200 chars after trimming; control characters rejected. |
| `…lat`, `…lon` | number | | `24.0 ≤ lat ≤ 49.5`, `-125.0 ≤ lon ≤ -66.5` (contiguous US). Out of range → 400 for raw coordinates; geocoded points outside → 422 `LOCATION_OUTSIDE_US`. |
| `options` | object | no | Unknown keys rejected. |
| `options.include_weather` | boolean | no | default `true` (P1 build); in P0-only builds the key is accepted and ignored with `weather.status="disabled"`. |
| `options.alternatives` | boolean | no | default `true`. `false` → request a single route. |
| `options.start_fuel_gal` | number | no | `0 ≤ x ≤ 50`, default 0 (ALGORITHM §2). |
| `options.departure_time` | string | no | ISO-8601 with timezone, between now−1h and now+14d; default now. |
| (root) | | | Unknown keys rejected; start and finish must differ by ≥ 1 mile straight-line after geocoding (`ROUTE_TOO_SHORT`). Max body 4 KB. |

### 4.2 Response schema (200)

```
PlanResponse {
  request_id: string
  status: "ok"
  assumptions: { mpg:number, max_range_miles:number, tank_capacity_gal:number, start_fuel_gal:number,
                 reserve_gal:number, station_corridor_miles:number, circuity_factor:number,
                 fuel_unit_gal:number, leftover_fuel_value_usd:0 }
  start:  Location      // {label, lat, lon, source: "geocoded"|"coordinates", cached: boolean}
  finish: Location
  recommended_route_id: string
  recommendation: { reason: "lowest_cost" | "only_feasible_route" | "lowest_cost_avoiding_severe_weather"
                            | "lowest_cost_within_duration_limit", considered: int, discarded: [{route_id, why}] }
  routes: Route[]       // 1–3, ordered by rank (recommended first)
  comparison: ComparisonRow[]
  meta: {
    external_calls: { geocoding:int, routing:int, weather:int },
    cache: { plan:"hit"|"miss", geocode:["hit"|"miss"], route:"hit"|"miss", weather:"hit"|"miss"|"partial"|"n/a" },
    timings_ms: { total, geocode, routing, matching, optimization, weather },
    data: { station_count:int, stations_data_version:string, station_position_precision:"place_centroid",
            price_aggregation:"median" },
    attribution: [string]  // OSRM / OpenStreetMap contributors / Open-Meteo
  }
}

Route {
  id: string                       // "r1","r2","r3"
  rank: int                        // 1 = recommended
  is_recommended: boolean
  summary: { distance_miles:number, duration_minutes:number }
  geometry: { type:"LineString", coordinates:[[lon,lat],…] }   // display-simplified, ≤ 2000 points
  fuel_plan: FuelPlan
  weather: Weather
}

FuelPlan {
  status: "ok" | "no_refuel_needed" | "infeasible"
  origin_price_source: "nearest_station"|"state_median"|"national_median"|null
  stops: Stop[]                    // ordered by route_mile; [] unless status "ok"
  totals: { total_fuel_cost_usd:number, fuel_consumed_gal:number, fuel_purchased_gal:number,
            leftover_gal:number, avg_price_per_gal:number, cost_per_mile_usd:number,
            num_stops:int, extra_detour_miles:number }
  infeasible?: { from_mile:number, to_mile:number, gap_miles:number }   // only when status "infeasible"
}

Stop {
  sequence: int                    // 1-based
  kind: "origin_fill" | "en_route"
  station: { id:int, opis_id:int, name:string, address:string, city:string, state:string,
             lat:number, lon:number, position_precision:"place_centroid" }
  route_mile: number               // distance from start where the station projects onto the route
  offset_miles: number             // perpendicular distance to route
  detour_miles: number             // round trip, 2 × circuity × offset
  arrival_fuel_gal: number         // on arrival at the station (after half-detour)
  gallons_bought: number
  price_per_gal: number            // 4 dp display; cost uses the unrounded price
  cost_usd: number                 // 2 dp
  fuel_after_gal: number           // in tank when back on route (after return half-detour)
  eta_minutes_from_start: number
}

Weather {
  status: "ok" | "partial" | "unavailable" | "disabled"
  risk_level: "none"|"low"|"moderate"|"severe"|null
  summary: string|null
  samples: [{ route_mile, lat, lon, eta, temperature_f, precipitation_in, wind_mph, gust_mph,
              visibility_mi, weather_code, condition, severity }]
}

ComparisonRow { route_id, distance_miles, duration_minutes, total_fuel_cost_usd, num_stops,
                avg_price_per_gal, weather_risk, cost_delta_vs_recommended_usd, duration_delta_minutes }
```

Rounding: money 2 dp; gallons 2 dp; miles 1 dp (2 dp for `offset_miles`/`detour_miles`); prices 4 dp. `totals.total_fuel_cost_usd` equals the sum of `stops[].cost_usd` **to the cent** (tests assert this).

When some routes are infeasible but at least one is feasible, infeasible routes are still returned (`fuel_plan.status = "infeasible"`, `is_recommended = false`) so the UI can show why.

### 4.3 Example request (cURL)

```bash
curl -sS -X POST http://localhost:8000/api/v1/routes/plan \
  -H 'Content-Type: application/json' \
  -d '{"start":{"query":"New York, NY"},"finish":{"query":"Chicago, IL"},"options":{"include_weather":true,"alternatives":true}}'
```

### 4.4 Example error responses
* Unknown place: `422 LOCATION_NOT_FOUND` with `details {"which":"finish","query":"Zzzzville"}`.
* Bad input: `400 VALIDATION_ERROR` with `details.fields {"options.start_fuel_gal":["Must be between 0 and 50."]}`.
* Upstream down: `503 UPSTREAM_UNAVAILABLE` with `details {"provider":"osrm"}`.

## 5. Other endpoints

**`GET /health/live` → 200** `{"status":"ok"}`.
**`GET /health/ready` → 200/503** `{"status":"ok","checks":{"database":"ok","stations":{"status":"ok","count":6626}}}`; 503 if the DB is unreachable or the station count is 0.
**`GET /config` → 200** `{"mpg":10,"max_range_miles":500,"tank_capacity_gal":50,"station_corridor_miles":10,"station_count":6626,"attribution":[…]}`.
**`GET /stations` (P2)** — query: `state` (2 letters), `page` (≥1), `page_size` (1–100, default 50). Response: DRF page-number pagination `{"count":…,"next":…,"previous":…,"results":[{id,opis_id,name,city,state,lat,lon,price_usd}]}` ordered by `opis_id`. Unknown `state` → 400.

## 6. Complete example response

Illustrative. Station identities and prices are real rows from the supplied dataset (Carlstadt NJ SUNOCO #68102, Budd Lake NJ Exxon #69954, Girard OH MR FUEL #732 #63752). Route distances, durations, geometry, weather values and positions are **illustrative** (not produced by a live run). Geometry is truncated here with `…`; real responses carry up to 2,000 points. The arithmetic is internally consistent and is the reference for the contract test (`plan.example.json` must contain the same values, with the full coordinates list replaced by a short valid list).

```json
{
  "request_id": "7c1f0f0e-9e7a-4a73-9f1c-2f0b1d7d2c11",
  "status": "ok",
  "assumptions": {
    "mpg": 10.0, "max_range_miles": 500.0, "tank_capacity_gal": 50.0, "start_fuel_gal": 0.0,
    "reserve_gal": 0.0, "station_corridor_miles": 10.0, "circuity_factor": 1.3,
    "fuel_unit_gal": 0.01, "leftover_fuel_value_usd": 0
  },
  "start":  { "label": "New York, New York, United States", "lat": 40.7127, "lon": -74.0060, "source": "geocoded", "cached": false },
  "finish": { "label": "Chicago, Illinois, United States",  "lat": 41.8756, "lon": -87.6244, "source": "geocoded", "cached": false },
  "recommended_route_id": "r1",
  "recommendation": {
    "reason": "lowest_cost",
    "considered": 2,
    "discarded": []
  },
  "routes": [
    {
      "id": "r1", "rank": 1, "is_recommended": true,
      "summary": { "distance_miles": 790.4, "duration_minutes": 730 },
      "geometry": { "type": "LineString", "coordinates": [[-74.0060, 40.7127], [-74.0412, 40.7390], [-74.7310, 40.9168], "…", [-87.6244, 41.8756]] },
      "fuel_plan": {
        "status": "ok",
        "origin_price_source": "nearest_station",
        "stops": [
          {
            "sequence": 1, "kind": "origin_fill",
            "station": { "id": 3101, "opis_id": 68102, "name": "SUNOCO", "address": "ST 17", "city": "Carlstadt", "state": "NJ",
                         "lat": 40.8307, "lon": -74.0910, "position_precision": "place_centroid" },
            "route_mile": 0.0, "offset_miles": 0.0, "detour_miles": 0.0,
            "arrival_fuel_gal": 0.0, "gallons_bought": 4.70, "price_per_gal": 3.1623, "cost_usd": 14.86,
            "fuel_after_gal": 4.70, "eta_minutes_from_start": 0
          },
          {
            "sequence": 2, "kind": "en_route",
            "station": { "id": 3342, "opis_id": 69954, "name": "Exxon", "address": "I-80, EXIT 27A & US-46", "city": "Budd Lake", "state": "NJ",
                         "lat": 40.8715, "lon": -74.7410, "position_precision": "place_centroid" },
            "route_mile": 45.3, "offset_miles": 1.20, "detour_miles": 3.12,
            "arrival_fuel_gal": 0.01, "gallons_bought": 49.99, "price_per_gal": 3.1190, "cost_usd": 155.92,
            "fuel_after_gal": 49.84, "eta_minutes_from_start": 42
          },
          {
            "sequence": 3, "kind": "en_route",
            "station": { "id": 5871, "opis_id": 63752, "name": "MR FUEL #732", "address": "I-80, EXIT 226", "city": "Girard", "state": "OH",
                         "lat": 41.1734, "lon": -80.6961, "position_precision": "place_centroid" },
            "route_mile": 374.6, "offset_miles": 2.10, "detour_miles": 5.46,
            "arrival_fuel_gal": 16.63, "gallons_bought": 25.24, "price_per_gal": 3.2390, "cost_usd": 81.75,
            "fuel_after_gal": 41.59, "eta_minutes_from_start": 346
          }
        ],
        "totals": {
          "total_fuel_cost_usd": 252.53, "fuel_consumed_gal": 79.92, "fuel_purchased_gal": 79.93,
          "leftover_gal": 0.01, "avg_price_per_gal": 3.1594, "cost_per_mile_usd": 0.3195,
          "num_stops": 3, "extra_detour_miles": 8.58
        }
      },
      "weather": {
        "status": "ok", "risk_level": "low",
        "summary": "Light rain near mile 380 (ETA 2026-11-06T17:51Z); otherwise clear.",
        "samples": [
          { "route_mile": 0.0,   "lat": 40.7127, "lon": -74.0060, "eta": "2026-11-06T12:00:00Z", "temperature_f": 46.2, "precipitation_in": 0.0,  "wind_mph": 9.1,  "gust_mph": 17.0, "visibility_mi": 6.2, "weather_code": 3,  "condition": "Overcast",   "severity": "none" },
          { "route_mile": 380.0, "lat": 41.1010, "lon": -80.6500, "eta": "2026-11-06T17:51:00Z", "temperature_f": 41.5, "precipitation_in": 0.04, "wind_mph": 12.4, "gust_mph": 24.0, "visibility_mi": 4.1, "weather_code": 61, "condition": "Light rain", "severity": "low" },
          { "route_mile": 790.4, "lat": 41.8756, "lon": -87.6244, "eta": "2026-11-07T00:10:00Z", "temperature_f": 38.8, "precipitation_in": 0.0,  "wind_mph": 14.0, "gust_mph": 26.0, "visibility_mi": 9.9, "weather_code": 1,  "condition": "Mainly clear","severity": "none" }
        ]
      }
    },
    {
      "id": "r2", "rank": 2, "is_recommended": false,
      "summary": { "distance_miles": 806.9, "duration_minutes": 748 },
      "geometry": { "type": "LineString", "coordinates": [[-74.0060, 40.7127], "…", [-87.6244, 41.8756]] },
      "fuel_plan": {
        "status": "ok", "origin_price_source": "nearest_station",
        "stops": [ "…omitted in this documentation example; same Stop schema…" ],
        "totals": { "total_fuel_cost_usd": 261.40, "fuel_consumed_gal": 81.61, "fuel_purchased_gal": 81.62,
                    "leftover_gal": 0.01, "avg_price_per_gal": 3.2026, "cost_per_mile_usd": 0.3240,
                    "num_stops": 3, "extra_detour_miles": 9.20 }
      },
      "weather": { "status": "ok", "risk_level": "none", "summary": "No significant weather expected.", "samples": [] }
    }
  ],
  "comparison": [
    { "route_id": "r1", "distance_miles": 790.4, "duration_minutes": 730, "total_fuel_cost_usd": 252.53, "num_stops": 3,
      "avg_price_per_gal": 3.1594, "weather_risk": "low", "cost_delta_vs_recommended_usd": 0.00, "duration_delta_minutes": 0 },
    { "route_id": "r2", "distance_miles": 806.9, "duration_minutes": 748, "total_fuel_cost_usd": 261.40, "num_stops": 3,
      "avg_price_per_gal": 3.2026, "weather_risk": "none", "cost_delta_vs_recommended_usd": 8.87, "duration_delta_minutes": 18 }
  ],
  "meta": {
    "external_calls": { "geocoding": 2, "routing": 1, "weather": 1 },
    "cache": { "plan": "miss", "geocode": ["miss", "miss"], "route": "miss", "weather": "miss" },
    "timings_ms": { "total": 1840, "geocode": 1150, "routing": 410, "matching": 95, "optimization": 88, "weather": 160 },
    "data": { "station_count": 6626, "stations_data_version": "9d2f…c41a", "station_position_precision": "place_centroid", "price_aggregation": "median" },
    "attribution": ["Routing © OSRM contributors, data © OpenStreetMap contributors (ODbL)", "Geocoding © OpenStreetMap contributors", "Weather data by Open-Meteo.com (CC BY 4.0)"]
  }
}
```

Arithmetic check for `r1` (the reference for tests):

| Item | Value |
|---|---|
| Purchases | 4.70 + 49.99 + 25.24 = **79.93 gal** |
| Cost | 4.70 × 3.162333 = 14.863 → 14.86; 49.99 × 3.119 = 155.919 → 155.92; 25.24 × 3.239 = 81.752 → 81.75; **total 252.53** |
| Consumed | 79.04 (route) + 0.32 + 0.56 (rounded half-detours, 2 × 0.16 and 2 × 0.28) = 79.92; leftover 0.01 |
| Reachability | Leg 1 4.53 gal + 0.16 half-detour ≤ 4.70; leg 2 32.93 gal ≤ 49.84; leg 3 41.58 + 0.28 + 0.01 margin ≤ 41.87 |

`totals.extra_detour_miles` = 3.12 + 5.46 = 8.58.
