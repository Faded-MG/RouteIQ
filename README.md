# FuelRoute — Optimal Refueling Route Planner

FuelRoute is a Django REST API (with an accompanying React map interface) built for Spotter's Backend Django Engineer assessment. Given two locations within the continental United States, it computes the driving route geometry, cost-optimal fuel stops adhering strictly to a **500-mile vehicle range at 10 MPG**, and the total fuel expenditure using the provided fuel price dataset.

---

## 1. Verified Dataset Reference

The original fuel price dataset provided by Spotter is committed unchanged at `data/fuel-prices-for-be-assessment.csv`. Its integrity is verified as part of task T01:

* **File:** `data/fuel-prices-for-be-assessment.csv`
* **SHA-256 Checksum:** `c704371f141ded9c54df6c32d488a0ba2ceb589f88c936c967daa5330e0cd241`
* **Line Count:** 8,152 lines (1 header + 8,151 records)
* **Byte Size:** 577,081 bytes

---

## 2. Technology Stack & Pinned Series

* **Backend Runtime:** Python 3.13
* **Web Framework:** Django 6.1.3 (latest stable 6.1 series, verified at [djangoproject.com](https://www.djangoproject.com/download/)) + Django REST Framework
* **Database:** PostgreSQL 17 (plain relational schema — strictly no PostGIS, Redis, or Celery)
* **Geospatial & Numerics:** NumPy (vectorized equirectangular projection and DP solver), `polyline` (polyline6 decoding), `httpx` (outbound HTTP with strict timeouts)
* **Testing & Quality:** `pytest`, `pytest-django`, `pytest-cov`, `respx`, `hypothesis`, `ruff` (100 character line limit)
* **Frontend (Phase 5):** React 19, TypeScript (strict), Vite, Tailwind CSS v4, Leaflet via `react-leaflet`, TanStack Query

---

## 3. Project Structure

```
fuelroute/
├── AGENTS.md                          # Operating instructions & rules for AI agent
├── ASSESSMENT.md                      # Verbatim Spotter assessment requirements
├── docs/                              # Project blueprints & formal specifications
│   ├── ALGORITHM.md                   # Math, dynamic programming & reachability proof
│   ├── API_SPEC.md                    # OpenAPI specification & JSON contracts
│   ├── ARCHITECTURE.md                # System design, data model & call budgets
│   ├── DEPLOYMENT.md                  # Docker Compose, Nginx, SSL & VPS runbook
│   ├── PLAN.md                        # Task roadmap, dependencies & time budget
│   └── TESTING.md                     # Traceability matrix, oracle & test strategy
├── scripts/                           # Fixture recording and live smoke utilities
│   ├── record_fixtures.py             # Recorded offline API mocks
│   └── live_smoke.py                  # Live end-to-end sanity checker
├── backend/                           # Django REST API application
│   ├── manage.py
│   ├── pyproject.toml
│   ├── requirements/                  # Pinned Python dependencies (base.txt, dev.txt)
│   ├── config/                        # Settings split (base, dev, prod, test), WSGI, URLs
│   ├── apps/
│   │   ├── common/                    # Constants, API error envelope, request-id
│   │   ├── stations/                  # Station & ImportRun models, CSV importer, in-memory index
│   │   ├── geo/                       # Geometry, Nominatim geocoder, OSRM router
│   │   ├── fuel/                      # DP optimizer, reachability validator, candidate search
│   │   ├── weather/                   # Open-Meteo weather sampling & interpretation
│   │   └── planner/                   # Plan view, serializers, route selection
│   └── tests/                         # Unit, integration, API, and latency budget tests
├── frontend/                          # React + Leaflet client application
├── deploy/                            # Docker Compose, Nginx configs, deploy scripts
└── data/                              # Static data assets (read-only CSV)
```

---

## 4. Quickstart (Development Setup)

### Prerequisites
* Docker & Docker Compose v2
* Python 3.13
* Node.js 22 LTS (for frontend)

### Running Full-Stack Locally

#### 1. Backend (Django REST API)
```bash
# 1. Start PostgreSQL container (runs on port 5433 to avoid host port conflicts)
docker compose --env-file .env -f deploy/docker-compose.yml up -d db

# 2. Activate virtual environment
source backend/.venv/bin/activate

# 3. Run migrations and import station prices (if first run)
cd backend
python manage.py migrate
python manage.py createcachetable
python manage.py import_stations --csv ../data/fuel-prices-for-be-assessment.csv

# 4. Start backend API server (listens on http://localhost:8000)
python manage.py runserver 0.0.0.0:8000
```

#### 2. Frontend (React 19 + TypeScript + Vite + Leaflet)
In a separate terminal window:
```bash
cd frontend

# Install dependencies (if first run)
npm install

# Start Vite dev server with proxy to backend (http://localhost:5173)
npm run dev

# Run automated frontend test suite
npm test

# Run strict TypeScript typecheck and production build
npm run typecheck && npm run build
```

Open `http://localhost:5173` in your browser. The Vite development server automatically proxies all `/api/*` calls to `http://localhost:8000`.

---

## 5. Core Architectural Assumptions & Algorithm

* **Range & Consumption:** 500.0 miles max range, 10.0 MPG consumption rate, modeled as a 50.0-gallon usable fuel tank (`apps/common/constants.py`).
* **Fuel Quantization:** 0.01 gallon units (0.1 mile range increments) solved via exact dynamic programming.
* **Corridor & Detour Formula:** 10.0 mile corridor. Detours modeled as `2 × circuity × offset` with circuity factor 1.3.
* **Origin Fill:** Empty start tank (`start_fuel_gal = 0.0`). The vehicle fills at origin with price from the nearest station within 25 miles (or state/national median fallback).
* **Objective Function:** Strictly minimize total fuel dollars spent + tie-breaking stop penalty ($0.005/stop). Leftover fuel at destination valued at $0.
* **Independent Validator:** Every generated plan is verified by an independent float simulation (`apps/fuel/validator.py`) proving reachability without running dry.

---

## 6. Known Limitations

* **Station Position Precision:** The provided dataset contains city and state names but no street coordinates. Stations are geocoded to U.S. Census Bureau **place centroids** (`position_precision = "place_centroid"`), typically 1–8 miles from the actual highway exit. The 10-mile corridor and detour circuity factor conservatively absorb this displacement.
* **OSRM Public Demo Server:** Development uses the public OSRM demo server (`router.project-osrm.org`) which throttles to ~1 request/s. For production deployments, DEPLOYMENT.md provides a self-hosted OSRM profile.

---

## 7. Example API Usage

### Trip Planning Request
```bash
curl -X POST http://localhost:8000/api/v1/routes/plan \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"query": "New York, NY"},
    "finish": {"query": "Chicago, IL"},
    "options": {"start_fuel_gal": 0.0}
  }'
```

### Response (Extract)
```json
{
  "request_id": "0aa4ae6a-c188-4e21-8e63-b25ba0529595",
  "status": "ok",
  "routes": [
    {
      "id": "r1",
      "summary": {
        "distance_miles": 790.6,
        "duration_minutes": 891
      },
      "fuel_plan": {
        "status": "ok",
        "origin_price_source": "nearest_station",
        "stops": [
          {
            "sequence": 1,
            "kind": "origin_fill",
            "station": {"name": "ENRITE", "city": "Jersey City", "state": "NJ"},
            "route_mile": 0.0,
            "gallons_bought": 6.59,
            "price_per_gal": 3.349,
            "cost_usd": 22.07
          },
          {
            "sequence": 2,
            "kind": "en_route",
            "station": {"name": "ACI TRUCK STOP", "city": "Columbia", "state": "NJ"},
            "route_mile": 65.44,
            "gallons_bought": 33.54,
            "price_per_gal": 3.079,
            "cost_usd": 103.27
          },
          {
            "sequence": 3,
            "kind": "en_route",
            "station": {"name": "SHEETZ #791", "city": "North Jackson", "state": "OH"},
            "route_mile": 398.98,
            "gallons_bought": 39.33,
            "price_per_gal": 3.0657,
            "cost_usd": 120.57
          }
        ],
        "totals": {
          "total_fuel_cost_usd": 245.91,
          "fuel_consumed_gal": 79.46,
          "fuel_purchased_gal": 79.46,
          "avg_price_per_gal": 3.0948,
          "num_stops": 3
        }
      }
    }
  ],
  "meta": {
    "external_calls": {"geocoding": 2, "routing": 1, "weather": 0}
  }
}
```

---

## 8. Measured Performance (Benchmark Results)

Measured on macOS Python 3.13 via `backend/tests/perf/measure.py`:

| Metric | Budget | Measured | Status |
|---|---|---|---|
| **DP Optimizer (LA → NYC, 462 nodes)** | ≤ 150 ms (p95) | **82.39 ms** | Pass |
| **Candidate Matching (NYC → Chicago)** | ≤ 100 ms (p95) | **52.10 ms** | Pass |
| **Candidate Matching (LA → NYC, coast-to-coast)** | ≤ 500 ms (p95) | **458.20 ms** | Pass |
| **Cold Live Request (NYC → Chicago, real APIs)** | 1–4 s | **2.73 s** | Pass |
| **Peak Memory (TraceMalloc)** | ≤ 250 MB | **208.66 MB** | Pass |

---

## 9. Loom Recording Checklist (5-Minute Walkthrough)

* **0:00–0:30 Overview:** Problem statement, Spotter assessment constraints (500-mile range, 10 MPG, empty start, median prices, place-centroid precision).
* **0:30–2:30 Live Demo (React Map UI & Postman):**
  * Open `http://localhost:5173` in your browser (or fallback visualizer `docs/demo-map.html`, or Postman `docs/FuelRoute.postman_collection.json`).
  * NYC → Chicago: show full route polyline on Leaflet, numbered fuel stops with rich popups, exact totals to the cent, travel time, and detour calculation.
  * Multi-route alternatives: toggle route alternatives to view comparison table with cost and duration deltas, plus recommendation decision code.
  * Weather strip: show live route weather risk assessment along the corridor.
  * Cross-country trip (LA → NYC, ~2,800 miles) with 6 stops, mathematically proving no leg exceeds 500 miles.
* **2:30–4:15 Code Architecture:**
  * Clean layered architecture: `planner` orchestrates `geo`, `weather`, `stations`, and pure-Python `fuel`.
  * `candidates.py`: vectorized equirectangular projection & dominance pruning.
  * `optimizer.py`: exact dynamic programming with vectorized closed-form transitions.
  * `validator.py`: independent unsnapped float re-simulation.
* **4:15–5:00 Quality & Test Results:**
  * Test suite execution: 149 passed in ~2.5 min across unit, oracle, acceptance, weather, and API tests.
  * Coverage reports (95% overall, 100% in `optimizer.py` and `services.py`).

* **Corridor & Detours:** 10.0-mile perpendicular corridor filter; detours modeled conservatively as $2 \times 1.3 \times \text{offset}$ with fuel burned priced into the objective.
* **Station Geocoding:** The raw CSV contains city/state text with highway descriptions. Station coordinates are located as city centroids (`geocode_precision = "place_centroid"`).
* **Call Budget:** $\le 3$ external HTTP calls per cold request (1 OSRM routing, $\le 2$ Nominatim geocoding, 0 external calls for optimization).
