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

### Running Locally (Backend)
```bash
# 1. Clone repository and set up environment
cp .env.example .env

# 2. Start PostgreSQL container
docker compose --env-file .env -f deploy/docker-compose.yml up -d db

# 3. Create virtualenv and install dependencies
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements/dev.txt

# 4. Run migrations and import stations
cd backend
python manage.py migrate
python manage.py createcachetable
python manage.py import_stations --csv ../data/fuel-prices-for-be-assessment.csv

# 5. Start development server
python manage.py runserver 0.0.0.0:8000
```

---

## 5. Core Architectural Assumptions

* **Range & Consumption:** 500.0 miles max range, 10.0 MPG consumption rate, modeled as a 50.0-gallon usable fuel tank.
* **Fuel Quantization:** 0.01 gallon units (0.1 mile range increments) solved via exact dynamic programming.
* **Corridor & Detours:** 10.0-mile perpendicular corridor filter; detours modeled conservatively as $2 \times 1.3 \times \text{offset}$ with fuel burned priced into the objective.
* **Station Geocoding:** The raw CSV contains city/state text with highway descriptions. Station coordinates are located as city centroids (`geocode_precision = "place_centroid"`).
* **Call Budget:** $\le 3$ external HTTP calls per cold request (1 OSRM routing, $\le 2$ Nominatim geocoding, 0 external calls for optimization).
