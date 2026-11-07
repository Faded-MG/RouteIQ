# TESTING.md — FuelRoute Test Strategy

Every requirement in §1 maps to at least one named test. Test IDs below are the **required function names** (agents must not rename them; add more freely).

## 1. Requirement → test traceability

| Req | Requirement | Primary tests |
|---|---|---|
| R1 | Two US locations accepted | `tests/api/test_plan.py::test_accepts_query_and_coordinate_forms`, `::test_rejects_both_query_and_coords` |
| R2 | Geocoding both locations | `tests/unit/geo/test_geocoding.py::test_geocode_success_and_cache`, `::test_us_bbox_rejection` |
| R3 | Route geometry and distance | `tests/unit/geo/test_geometry.py::test_decode_polyline6`, `::test_cumulative_distance_scaled_to_osrm`, `tests/api/test_plan.py::test_response_contains_geometry_and_distance` |
| R4 | ≤ 3 external calls, 1 routing | `tests/api/test_call_budget.py::test_cold_request_call_counts`, `::test_warm_request_zero_calls`, `::test_coordinates_skip_geocoding` |
| R5 | Uses Spotter CSV prices | `tests/integration/test_import.py::test_counts_on_supplied_csv`, `::test_median_price_per_id`, `tests/api/test_plan.py::test_stop_prices_come_from_dataset` |
| R6 | Stations along the route | `tests/unit/fuel/test_candidates.py::test_corridor_filter`, `::test_route_mile_and_offset`, `::test_loop_back_earliest_mile` |
| R7 | 500-mile range | `tests/unit/fuel/test_optimizer_edge_cases.py::test_E4_gap_over_range_infeasible`, `::test_E7_exact_500_infeasible_due_to_margin`, `tests/unit/fuel/test_validator.py::test_leg_over_range_detected` |
| R8 | 10 MPG | `tests/unit/fuel/test_equations.py::test_fuel_for_distance_10mpg`, `::test_purchased_equals_consumed_plus_leftover` |
| R9 | Total money spent | `tests/unit/fuel/test_optimizer_examples.py::test_example_A_total_278`, `tests/api/test_plan.py::test_total_equals_sum_of_stops_to_the_cent` |
| R10 | Fast results | `tests/perf/test_latency_budget.py::test_matching_budget`, `::test_dp_budget`, `::test_warm_cache_budget` (§8) |
| R11 | Latest stable Django | `tests/unit/test_settings.py::test_django_version_pinned_to_series` (compares `django.VERSION[:2]` with the series recorded in `requirements/base.txt` and `README`) |
| R12 | Map of route (geometry) | `tests/api/test_plan.py::test_geometry_is_geojson_linestring_lonlat_order`, frontend `RouteMap.test.tsx::renders_polyline_and_markers` |
| R13 | Weather optional and non-blocking | `tests/unit/weather/test_interpret.py` (all rows), `tests/api/test_weather.py::test_weather_failure_does_not_fail_request`, `::test_single_batched_call` |
| R14 | Route comparison | `tests/unit/planner/test_selection.py::test_lowest_cost_wins`, `::test_severe_weather_avoided`, `::test_duration_limit`, `::test_all_infeasible_raises` |
| R15 | Input validation | `tests/api/test_validation.py` (matrix §6) |
| R16 | Error handling | `tests/api/test_errors.py::test_each_error_code_envelope` (parametrized over API_SPEC §3 table) |
| R17 | Security | `tests/api/test_security.py::test_no_debug_info_in_errors`, `::test_unknown_fields_rejected`, `::test_body_size_limit`, `::test_throttle_429` |
| R18 | Deployment config | CI `docker build`, `docker compose config`, `nginx -t`, post-deploy smoke (§12) |
| R19 | CSV cleaning | `tests/integration/test_import.py::test_canadian_rows_excluded`, `::test_idempotent_reimport`, `::test_unlocated_reported` |
| R20 | Reachability guarantee | `tests/unit/fuel/test_oracle.py::test_validator_passes_all_plans`, `tests/unit/fuel/test_validator.py::test_negative_fuel_rejected` |
| R21 | Optimality (model) | `tests/unit/fuel/test_oracle.py::test_dp_equals_bruteforce`, `::test_dp_equals_classical_greedy_without_detours` |

## 2. Tools

Backend: `pytest`, `pytest-django`, `pytest-cov`, `respx` (httpx mocking), `hypothesis` (property tests), `ruff`, `pip-audit`, `import-linter`. Frontend: Vitest, React Testing Library, MSW, `@vitest/coverage-v8`. No other test libraries without approval.

## 3. Global rules

* **No real network in tests.** `tests/conftest.py` has an autouse fixture that patches `httpx` transports with `respx.mock(assert_all_called=False)` and fails any unmocked request. Real network is allowed only in `scripts/live_smoke.py` (never run by CI).
* **Fixtures** (`backend/tests/fixtures/`): `osrm_nyc_chicago.json` (recorded as returned by OSRM demo: 2 routes when `alternatives=3` requested; 790.6 mi and 824.7 mi), `osrm_three_routes_synthetic.json` (hand-built 3-route fixture for AT-13 and selection tests), `osrm_la_nyc.json` (~2,800 mi), `nominatim_*.json`, `open_meteo_multi.json`, `stations_mini.csv` (≈ 60 hand-made rows covering Canadian rows, duplicate IDs, bad prices, unmatched city), `places_mini.csv`. They are recorded once with `scripts/record_fixtures.py` (≤ 1 req/s, real `APP_CONTACT`) and then committed.
* Tests are deterministic: fixed seeds for random/hypothesis (`derandomize=True` in CI profile), frozen time (`freezegun` is **not** allowed; inject a `clock` callable).
* A test must fail when the feature is removed (verify by temporarily breaking the code during development of critical tests R7, R9, R20).

## 4. Unit tests

| Module | Required content |
|---|---|
| `common` | Error envelope shape; request-id propagation; constants equal ALGORITHM §2 (`test_constants_match_algorithm_doc` compares `apps/common/constants.py` with `tests/fixtures/algorithm_constants.json`, a checked-in mirror of the ALGORITHM §2 tables that may only change in the same commit as the document). |
| `geo.geometry` | Haversine against 5 known city pairs (±0.2%); polyline decode/encode round-trip; rescale; Douglas–Peucker tolerance property; display cap 2,000 points; degenerate inputs (2 points, identical points). |
| `geo.geocoding` | Normalization (case, whitespace, punctuation); positive/negative cache TTL with injected clock; User-Agent header present and not default; throttle spacing; error mapping (404 empty array → `LOCATION_NOT_FOUND`, 429/503 → `UPSTREAM_UNAVAILABLE`, timeout → `UPSTREAM_TIMEOUT`, bad JSON → `UPSTREAM_BAD_RESPONSE`). |
| `geo.routing` | URL built exactly as PLAN T10; one call; cache by rounded coords; `NoRoute`; fewer alternatives than requested handled. |
| `stations` | Importer rules (§5); `StationIndex` lazy load, version reload, 0 queries after load. |
| `fuel.candidates` | Synthetic straight-line and L-shaped routes with stations at known offsets; bbox prefilter equivalence (with and without prefilter yields the same set); chunking boundary (chunk size 1 vs default same result); dominance pruning keeps the optimum. |
| `fuel.optimizer` | Worked examples A/B/C; E1–E13 (`test_E1…test_E13`, one each); tie determinism; grid unit 0.5 gal for speed. |
| `weather` | Table-driven interpretation (each ALGORITHM/ARCH row); route risk aggregation; sampling stride and cap (≤ 12); dedupe by 0.1°; ETA beyond 16 days → `partial`. |
| `planner.selection` | ALGORITHM §10 steps 1–4 with constructed inputs, tie-break order. |

## 5. Algorithm testing (the critical suite)

1. **Examples** (`test_optimizer_examples.py`): A → total $278.00, purchases (10.00, 50.00, 30.00) with unit 1.0; naive baseline $347.40 asserted greater; B → break-even at q = 41.6 gal, i.e. at q = 40 the on-route station wins by $0.24, at q = 45 the detour station wins; C → infeasible with `largest_gap = {300, 850, 550}`.
2. **Brute-force oracle** (`test_oracle.py::test_dp_equals_bruteforce`): instances with ≤ 6 stations, route ≤ 12 "gallon-miles" units (`fuel_unit_gal = 1`, `MPG = 1`, `tank = 5`), integer positions/prices; the oracle enumerates every subset of stations × every purchase vector and returns the minimal cost. DP cost must equal the oracle exactly on ≥ 200 hypothesis-generated instances (includes detours as integer units and reserve ∈ {0,1}).
3. **Classical greedy** (`test_dp_equals_classical_greedy_without_detours`): for no-detour instances, the look-ahead rule ("buy just enough to reach the next cheaper station within range, else fill") equals the DP cost.
4. **Properties** (hypothesis, ≥ 300 examples): (a) validator accepts every plan; (b) cost ≥ `(D / MPG − start_fuel) × min_price`; (c) cost ≤ cost of "fill to capacity at each reachable station"; (d) adding a station never increases cost; (e) multiplying all prices by k multiplies cost by k (without stop penalty effects: run with `STOP_PENALTY=0`); (f) leftover ≤ 0.1 gal at default grid.
5. **Reachability negative tests** (`test_validator.py`): hand-crafted plans that run dry by 0.02 gal, exceed capacity, or buy at a station behind the vehicle are rejected with the specific reason.
6. **Edge cases E1–E13:** one test each, named `test_E<n>_<slug>`, asserting the "Required behavior" column of ALGORITHM §9.

## 6. API tests (`tests/api`, DRF `APIClient`, mocked providers, real test Postgres)

Validation matrix `test_validation.py` (each row → one parametrized case → 400 `VALIDATION_ERROR` with the listed `details.fields` key):

| Input | Field key |
|---|---|
| missing `start` | `start` |
| `start` has both `query` and `lat/lon` | `start` |
| `query` of 2 chars / 201 chars / `"\u0000"` | `start.query` |
| `lat` 23.9 / 49.6; `lon` -125.1 / -66.4 | `start.lat` / `start.lon` |
| `start_fuel_gal` -1 / 50.1 / `"a"` | `options.start_fuel_gal` |
| `departure_time` naive datetime / > 14 days / < now−1h | `options.departure_time` |
| unknown root or options key | the key |
| invalid JSON → 400 `VALIDATION_ERROR`; wrong content type → 415; GET → 405 | — |

Also required by name: `test_route_too_short_422` (start/finish < 1 mile apart), `test_optimizer_validator_failure_returns_internal_error` (monkeypatch the validator to fail → 500 `INTERNAL_ERROR`, no stack trace, no plan returned), and in `test_optimizer_edge_cases.py` `test_margin_applies_on_station_arrival` (a plan whose station arrival fuel would be 0.00 gal is never produced; arrival ≥ `SAFETY_MARGIN_UNITS`).

Plus: 422 cases for each code in API_SPEC §3; response schema validation against a Python schema derived from API_SPEC §4.2 (`jsonschema` is **not** allowed — use DRF serializers `PlanResponseSerializer` in test mode to validate); `test_total_equals_sum_of_stops_to_the_cent`; `test_stops_ordered_by_route_mile`; `test_example_response_in_spec_is_valid` (parses the JSON block of API_SPEC §6 after replacing `"…"` placeholders using a documented transformation).

## 7. Integration and database tests

* `test_import.py` on `stations_mini.csv`: Canadian rows excluded; duplicate `opis_id` collapsed with median; price outliers rejected; unmatched city reported and excluded; second run is a no-op (row counts and `updated` count 0); constraints enforced at DB level (`IntegrityError` for price 0).
* `test_import.py::test_counts_on_supplied_csv` runs on the real CSV (marked `slow`; included in CI) and asserts 8,151 / 7,531 / 6,626.
* Cache tables: TTL expiry with injected clock; unique-key conflict handling (concurrent insert → one row).
* Migration tests: `makemigrations --check --dry-run` fails the build if models drift; migrate forward and backward on empty DB.
* End-to-end in-process (`test_e2e_plan.py`): real importer → real index → mocked OSRM/Nominatim → full plan; assertions from §10 AT-01.

## 8. Performance testing

`backend/tests/perf/measure.py` (run manually and in a separate CI job `perf`, non-blocking but recorded as an artifact):

| Metric | How measured | Budget |
|---|---|---|
| Candidate matching, 3 routes coast-to-coast | `time.perf_counter` around `candidates.find()` with `osrm_la_nyc.json` | ≤ 150 ms per route (p95 over 30 runs) |
| DP optimization, ~600 candidates | around `optimize()` | ≤ 150 ms per route (p95) |
| Total compute (mocked providers), 3 routes | Django test client, 50 sequential requests, plan cache disabled | p50 ≤ 400 ms, p95 ≤ 700 ms |
| Warm plan cache | same, cache enabled | p95 ≤ 50 ms |
| Cold live request (manual, `scripts/live_smoke.py`) | real OSRM + Nominatim | recorded in README; expected 1–3 s, dominated by upstream |
| Memory | `tracemalloc` peak around one 3-route plan | ≤ 150 MB |

Budgets apply on a 2-vCPU machine. `test_latency_budget.py` asserts them with a 2× tolerance in CI (shared runners) and prints the actual numbers.

## 9. Acceptance test scenarios (end-to-end, mocked providers unless noted)

| ID | Scenario | Expected |
|---|---|---|
| AT-01 | NYC → Chicago (`osrm_nyc_chicago.json`), defaults | 200; ≥ 2 stops needed (route > 500 mi, start fuel 0); `origin_fill` first; all constraints; validator passes; total = Σ stops; cold calls = 2 geocode + 1 route. |
| AT-02 | LA → NYC (≈ 2,800 mi) | 200; plan has ≥ 6 stops; no leg > 500 mi (assert from output); total cost within the range `[D/MPG × min_price, D/MPG × max_price]`. |
| AT-03 | Short trip (≈ 120 mi) | `fuel_plan.status="ok"`, single origin fill sized to the trip, total ≈ trip gallons × origin price. |
| AT-04 | `start_fuel_gal = 50`, trip 300 mi | `no_refuel_needed`, 0 stops, $0. |
| AT-05 | Same request twice | Second: `meta.cache.plan="hit"`, all `external_calls` = 0, identical `routes`. |
| AT-06 | Coordinates instead of text | 0 geocoding calls. |
| AT-07 | Unknown place | 422 `LOCATION_NOT_FOUND`, `details.which`. |
| AT-08 | Geocodes outside the contiguous US (e.g., Honolulu) | 422 `LOCATION_OUTSIDE_US`. |
| AT-09 | OSRM returns `NoRoute` | 422 `ROUTE_NOT_FOUND`. |
| AT-10 | Open-Meteo times out | 200, `weather.status="unavailable"`, plan unchanged, plan not cached. |
| AT-11 | Synthetic desert route, 550-mile station gap | 422 `NO_FEASIBLE_FUEL_PLAN` with `largest_gap`. |
| AT-12 | OSRM 503 | 503 `UPSTREAM_UNAVAILABLE` with `details.provider="osrm"`; no stack trace in body. |
| AT-13 | Three alternatives, one severe weather | Severe route not recommended if another feasible route exists; `recommendation.reason="lowest_cost_avoiding_severe_weather"` when it changes the choice. |
| AT-14 | 31 requests/min from one IP | 31st → 429 with `Retry-After`. |
| AT-15 | Station data not imported | `/health/ready` 503; plan → 503 `FUEL_DATA_NOT_LOADED`. |

## 10. Frontend tests (Vitest + RTL + MSW)

| Area | Tests |
|---|---|
| Form | Required fields, length limits, submit disabled while pending, coordinate toggle (if implemented), error banner per error code (`LOCATION_NOT_FOUND`, `NO_FEASIBLE_FUEL_PLAN`, `UPSTREAM_*`, `RATE_LIMITED`). |
| API client | Parses the API_SPEC §6 example (`plan.example.json`); maps the error envelope; handles network failure. |
| Map | `renders_polyline_and_markers`: polyline coordinates stay `[lon, lat]` for MapLibre; one marker per stop with sequence number; selecting another route changes the recommended styling; attribution present. (`maplibre-gl` is mocked at the module boundary.) |
| Panels | Totals text equals fixture numbers; stop table ordered; weather unavailable placeholder; comparison deltas formatted; currency/number formatting helpers. |
| Accessibility | Form inputs labelled; route selection reachable by keyboard; map has a text alternative (list of stops). |

## 11. Coverage targets (enforced in CI with `--cov-fail-under`)

| Scope | Line | Branch |
|---|---|---|
| `apps/fuel` | ≥ 95% | ≥ 90% |
| `apps/geo/geometry.py` | ≥ 95% | ≥ 90% |
| `apps/stations`, `apps/weather`, `apps/planner`, `apps/common` | ≥ 85% | ≥ 75% |
| Backend overall | ≥ 85% | — |
| Frontend overall | ≥ 70% | — |

## 12. CI test pipeline (matches DEPLOYMENT.md §8)

1. `ruff check` and `ruff format --check`.
2. `python manage.py makemigrations --check --dry-run`; `python manage.py check --deploy` with prod settings and dummy env.
3. `pytest -m "not perf" --cov --cov-fail-under=85` against a Postgres 17 service.
4. `pip-audit -r requirements/base.txt` (fail on high/critical).
5. Frontend: `npm ci`, `npm run lint`, `npm run typecheck`, `npm run test:coverage`, `npm run build`, `npm audit --omit=dev --audit-level=high`.
6. `docker build` for both images; `docker compose -f deploy/docker-compose.prod.yml config`; `nginx -t` in the frontend image with the prod config mounted.
7. (Deploy job only) post-deploy smoke: `curl -fsS https://$DOMAIN/api/v1/health/ready` and one `POST /routes/plan` with coordinates.
