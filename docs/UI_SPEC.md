# UI_SPEC.md — FuelRoute UI (interaction model from a reference recording; theme is ours)

Status: replaces the detail of PLAN.md T21–T24 (tasks U1–U5 below). Priority **P1**. Start **only after `v0.1.0` is tagged** (PLAN §2 cut rule). Time cap 4 h; if it slips, README keeps the geojson.io fallback. Precedence: ASSESSMENT.md > ALGORITHM.md > API_SPEC.md > this file > ARCHITECTURE.md §8. Any conflict → AGENTS.md §11.

## 1. What is copied and what is not

Copied: the **interaction model** only: one floating panel over a full-screen map, an analysis phase where routes are drawn and "driven" one by one, then a recommendation report with selectable route cards.
Not copied: name, copy text, colors, fonts, icons, logo, the "HQ" pin, code, assets. Theme is chosen by the project owner later; all visual values come from CSS custom properties (§9). Until the owner supplies a theme, use the neutral placeholder palette.

### Reference behaviour observed (screen recording, 16.7 s, desktop)
1. Panel (left, floating, translucent) shows a summary card (origin → destination, date/time), a title that changes per step, and a checklist: ✓ done / spinner active / empty pending, with a duration on the right of finished steps.
2. During analysis, a small vehicle marker travels along each candidate route in turn while the line is drawn progressively. The current route is drawn dark, previous routes turn grey. A letter-coded sub-list (A, B, C) shows `testing` → `✓` per route.
3. At the end all routes are drawn in color, the map camera eases to fit them, ETA time chips appear at checkpoints, and a label chip sits on each route ("A · 5h 14m · 225 mi" plus a badge).
4. The panel switches to a **Recommendation** view with a back arrow: headline, one-line reason, a "Why this route?" disclosure, an info notice about how many routes the router returned, then route cards (letter badge, name, badges, distance/time, a risk bar, a one-line verdict). A risk legend sits bottom-right of the map.
5. Map library: **MapLibre GL JS** with an OpenFreeMap vector style (owner decision, 2026-11-07), matching the reference's rendering approach [A: inferred from its footer credits and compact attribution control]. This replaces the earlier raster-map approach in ARCHITECTURE §2/§3/§8 and AGENTS §4; the required document changes are listed in §14 (CR-UI-1).

## 2. Layout

* Full-viewport map. A single floating **panel**: desktop width 380 px, 16 px margin, max-height `calc(100vh - 32px)`, internal scroll, rounded, translucent surface. Brand chip top-left (above/inside panel header), nothing else floating except the map's attribution and zoom control.
* Mobile (< 768 px): the panel becomes a bottom sheet with three states toggled by tapping its handle: peek (120 px), half (50 vh), full (90 vh). No drag library. The map keeps interactive area above the sheet.
* Only **one** view is visible in the panel at any time. A back arrow is shown in every view except the form.

## 3. Panel state machine (`features/route-planner/usePlannerFlow.ts`, reducer, unit-tested)

| State | Entered when | Panel shows | Map shows | Leaves when |
|---|---|---|---|---|
| `form` | initial; back from `results` | form (§4) | start/finish markers if known, else default US view | submit → `loading` |
| `loading` | request in flight | summary card + one **indeterminate** active step "Planning your route" + Cancel | pulsing start/finish markers once geocoded is unknown, so none | response → `revealing`; error → `error`; cancel → `form` |
| `revealing` | response received (and not reduced-motion) | analysis view (§5) | progressive draw + moving marker | finished or skipped → `results` |
| `results` | reveal done | report (§6) | all routes, selected highlighted | back → `form`; card click → stays, changes selection |
| `error` | request failed | message from error code (§10), Retry, Edit | previous map state | retry → `loading`; edit → `form` |

Honesty rule: the backend is one synchronous POST. While `loading`, show only the indeterminate step. Do **not** fake per-stage progress. The checklist in `revealing` is a replay of the stages the server reports, with **real durations from `meta.timings_ms`**.

## 4. Form view

Fields: Start (text), Finish (text), "Include weather" toggle (default on), "Starting fuel (gal)" inside a collapsed "Advanced" section (0–50, default 0). Primary button "Plan route". Three example chips ("New York → Chicago", "Los Angeles → Denver", "Miami → Atlanta") fill the fields. Validation mirrors API_SPEC §4.1 (length 3–200, fuel 0–50) with inline messages; the button is disabled while `loading`. Coordinates input is not exposed in the UI.

## 5. Analysis (reveal) view

Checklist rows (omit the weather row if `include_weather` was false or `weather.status = "disabled"`), each with the server duration from `meta.timings_ms`:
1. Located start and finish (`geocode`)
2. Found N routes (`routing`)
3. Matched fuel stations (`matching`)
4. Optimized fuel stops (`optimization`)
5. Checked weather (`weather`)
6. Chose the best route (client-side, no duration)

Below the checklist, a route sub-list: `A  Route A · 790 mi` with state `reviewing` → `✓ $252.53`.

**Choreography** (`features/route-planner/revealTimeline.ts`, a pure function from routes + `meta.cache.plan` to ordered keyframes; unit-tested):
* Per route, in rank order: draw the polyline from start to end over 900 ms (ease-in-out) while a vehicle marker moves along it, rotated to the local bearing; the sub-list row turns active, then ✓ with the route's cost. When the route finishes, it fades to a muted tone (250 ms) and the next starts.
* After the last route: all routes fade to their final styles (250 ms), camera eases to fit all (800 ms), ETA/label chips appear (stagger 60 ms), panel cross-fades to `results` (200 ms).
* Total ≤ 5 s. If `meta.cache.plan = "hit"`, use 300 ms per route. A **Skip** button is visible throughout; pressing `Esc` or clicking the map also skips.
* `prefers-reduced-motion: reduce` → no `revealing` state: go straight to `results` with the camera fitted.
* Announce step changes through an `aria-live="polite"` region.

## 6. Results view ("report")

Top to bottom:
1. Header: back arrow, "Start → Finish", departure date/time, small assumptions line "10 MPG · 500 mi range" (from `assumptions`).
2. Recommendation block: eyebrow `RECOMMENDATION`, headline, reason line, "Why this route?" disclosure.
   * Headline by `recommendation.reason`:
     `lowest_cost` → "Route A is the cheapest choice";
     `lowest_cost_avoiding_severe_weather` → "Route A is the cheapest route with safe weather";
     `lowest_cost_within_duration_limit` → "Route A is the cheapest reasonable route";
     `only_feasible_route` → "Route A is the only feasible route".
   * Reason line from `comparison`: "$8.87 less than Route B · 18 min faster" (use the delta fields; omit the clause that is zero; wording flips for slower/dearer).
   * Disclosure lists `recommendation.discarded[]` with human text and the selection rule (ALGORITHM §10 in one sentence).
3. Info notice when `alternatives` was requested and `routes.length < 3`: "The routing service returned N distinct route(s)." (client-computed).
4. **Route cards**, one per route in rank order, rendered as a radio group (`role="radiogroup"`; arrow keys move selection; Enter/Space selects):
   * Header: letter badge A/B/C, "Route A", badges: `Recommended`, `Cheapest`, `Fastest` (by comparison), `+18 min` when slower than fastest, weather chip (`Low`, `Moderate`, `Severe`, or `Weather unavailable`).
   * Stats grid: Fuel cost (largest, monospace), Distance, Drive time, Fuel stops, Avg price/gal. Departs → arrives.
   * Weather bar (only when `weather.status` is `ok` or `partial`): segments colored by sample severity.
   * Selected card is expanded and shows **Fuel stops** (`StopList`) and **Totals**:
     stop row = number, station name, city/state, route mile, `gallons × price = cost`, ETA clock time, detour miles if > 0; the first row is labelled "Start fill" (`kind = origin_fill`).
     totals = gallons purchased, total cost, avg price, cost per mile, extra detour miles.
   * `status = "infeasible"` cards are muted, not selectable, and show the largest gap ("No fuel station within range between mile 300 and 850").
5. Footer: `meta.attribution[]`, plus "Station positions are approximate (city centre)" from `meta.data.station_position_precision`.

Selecting a card: map highlights that route (§7), fits bounds, stops appear as numbered markers; the card scrolls into view.

## 7. Map behaviour (MapLibre GL JS, used directly; no React map-wrapper library)

* **Library:** `maplibre-gl` (BSD-3-Clause). The implementer verifies the latest stable version on npm and pins it exactly. Search results mention a v6 line described as WebGL-mandatory and ESM-only [A: release notes not read]; Vite handles ESM. Large bundle: load `TripMap` with `React.lazy` so the form renders first.
* **Basemap:** vector style from env `VITE_MAP_STYLE_URL`; default OpenFreeMap "positron" (light, low contrast), expected `https://tiles.openfreemap.org/styles/positron` ⚠ confirm in https://openfreemap.org/quick_start/. Terms verified on openfreemap.org: free public instance, no API key, commercial use allowed, attribution required (MapLibre adds it automatically). No SLA is stated [A]. If the style fails to load (`error` event), show a "Basemap unavailable" notice and keep drawing routes on a plain background color.
* **Init:** one `maplibregl.Map` created once in `TripMap` (stored in a ref, destroyed on unmount). `attributionControl: false`, then add `AttributionControl({ compact: true, customAttribution: meta.attribution })` and a zoom-only `NavigationControl`. Keep the map north-up: `dragRotate: false`, `pitchWithRotate: false`, touch rotation disabled.
* **Sources and layers** (added after `load`): per route a GeoJSON source `route-{id}` with a LineString and two layers, `route-{id}-casing` (white, 9 px) and `route-{id}-line`. Selection changes use `setPaintProperty` (selected 6 px, full opacity; others 4 px, 45 %) and `moveLayer` to bring the selected route on top; never remove and re-add on selection or re-render. Layer ids are stable. Route colors come from tokens `--route-a/b/c`.
* **Weather coloring (selected route only, when `weather.status` is `ok`):** one source `route-{id}-weather` with one LineString feature per segment between samples and a `severity` property; `line-color` uses a `match` expression over `severity`. MapLibre paint properties cannot read CSS variables, so `readTheme.ts` reads the tokens once with `getComputedStyle(document.documentElement)` at init and on theme change.
* **Progressive draw:** during the reveal call `source.setData()` each animation frame with the sliced coordinates (≤ 2,000 points).
* **Markers** (`maplibregl.Marker` with HTML elements, created once per result and removed on cleanup): start = ring, finish = square, numbered stops on the selected route only, route label chips at 40 % / 55 % / 70 % along routes A/B/C ("A · 12h 10m · 790 mi" + `CHEAPEST` on the recommended one), ETA chips at start, each stop and finish (browser locale; departure from `options.departure_time` or the request time), vehicle marker (SVG, `setRotation(bearing)`, `rotationAlignment: "map"`).
* **Popups:** `maplibregl.Popup` on stop click (station, city/state, price, gallons, cost). Two-way hover between stop rows and stop markers.
* **Camera:** `map.fitBounds(bounds, { padding: { top: 24, right: 24, bottom: B, left: L }, duration: 800, maxZoom: 12 })` with `L = panelWidth + 32` on desktop and `B = sheetHeight + 16` on mobile. Call `map.resize()` after panel or sheet size transitions. Reduced motion → `duration: 0`.
* **Vehicle animation:** precompute cumulative haversine distance over the display geometry (API_SPEC §4.2, ≤ 2,000 points, `[lon, lat]` is MapLibre's native order, so no flip is needed); `requestAnimationFrame` loop; bearing from the segment under the marker; cancel on skip/unmount.
* **WebGL:** if WebGL is unavailable (`canvas.getContext("webgl2")` and `"webgl"` both fail), `TripMap` renders a text fallback ("This map needs WebGL") and the panel (form, report, stop lists) still works.
* **Tests:** jsdom has no WebGL. Mock `maplibre-gl` at the module boundary (`src/test/mocks/maplibre-gl.ts`, Vitest alias) with spies for `addSource`, `addLayer`, `setPaintProperty`, `moveLayer`, `fitBounds`, `resize`, `Marker`, `Popup`. Tests assert calls and arguments, not pixels.
* **Security headers:** MapLibre uses blob web workers and fetches tiles/styles cross-origin. DEPLOYMENT §6 CSP must include `worker-src blob:`, `img-src 'self' data: blob:` and `connect-src 'self' https://tiles.openfreemap.org` (adjust to the actual style host).

## 8. Data mapping

| UI element | API field |
|---|---|
| Route list, rank, badges | `routes[].rank`, `is_recommended`, `comparison[]` |
| Distance / drive time | `routes[].summary.distance_miles`, `duration_minutes` |
| Fuel cost, gallons, avg price, cost/mile, stops | `routes[].fuel_plan.totals.*`, `fuel_plan.stops[]` |
| Stop rows and markers | `stops[].station.{name,city,state,lat,lon}`, `route_mile`, `gallons_bought`, `price_per_gal`, `cost_usd`, `eta_minutes_from_start`, `detour_miles`, `kind` |
| Route geometry | `routes[].geometry.coordinates` (`[lon, lat]`, MapLibre's native order) |
| Weather chip/bar/legend | `routes[].weather.{status,risk_level,samples[].severity}` |
| Headline, reason, disclosure | `recommendation.{reason,discarded}`, `comparison[].cost_delta_vs_recommended_usd`, `duration_delta_minutes` |
| Step durations | `meta.timings_ms.*` |
| Reveal speed | `meta.cache.plan` |
| Footer | `meta.attribution`, `meta.data.station_position_precision`, `assumptions` |

## 9. Theme tokens (`src/shared/styles/theme.css`, the only place with raw colors)

`--color-bg`, `--color-surface`, `--color-surface-glass`, `--color-border`, `--color-text`, `--color-text-muted`, `--color-accent`, `--color-accent-contrast`, `--color-route-a`, `--color-route-b`, `--color-route-c`, `--color-route-muted`, `--color-risk-none`, `--color-risk-low`, `--color-risk-moderate`, `--color-risk-severe`, `--color-risk-unknown`, `--radius-panel`, `--radius-card`, `--shadow-panel`, `--font-sans`, `--font-mono` (numbers use mono with tabular figures), `--motion-fast`, `--motion-route-draw`. Components reference tokens only. Copy strings live in `src/shared/strings.ts` so tone can be changed in one file. Dark mode is out of scope. Map paint colors are read from these tokens in JS (§7).

## 10. Errors and edge states

| Case | UI |
|---|---|
| `VALIDATION_ERROR` | inline field errors from `details.fields` |
| `LOCATION_NOT_FOUND` | message naming the field (`details.which`), focus that input |
| `LOCATION_OUTSIDE_US`, `ROUTE_TOO_SHORT`, `ROUTE_NOT_FOUND` | clear sentence + Edit |
| `NO_FEASIBLE_FUEL_PLAN` | explain the gap from `details.largest_gap` |
| `RATE_LIMITED` | "Too many requests" + countdown from `Retry-After` if present |
| `UPSTREAM_*` | "A map service is unavailable. Try again." + Retry |
| `INTERNAL_ERROR`, network failure | generic message + request id (copyable) |
| Weather `unavailable` | weather chip "Weather unavailable"; no bar, no legend |
| Only one route | single card; no notice if `alternatives=false` |

## 11. Files (extends ARCHITECTURE §4 `frontend/src/features`, same names)

```
features/route-planner/  RoutePlannerPanel.tsx/.css  RouteForm.tsx/.css  AnalysisView.tsx/.css  StepList.tsx/.css
                         usePlannerFlow.ts  revealTimeline.ts  useRoutePlan.ts  api.ts  types.ts
features/map/            TripMap.tsx/.css  mapLayers.ts  markers.ts  VehicleMarker.ts  useCamera.ts  geometry.ts  readTheme.ts
test/mocks/              maplibre-gl.ts
features/route-comparison/ RecommendationHeader.tsx/.css  RouteCard.tsx/.css  RouteCardList.tsx  WhyThisRoute.tsx
features/fuel-plan/      StopList.tsx/.css  Totals.tsx/.css
features/weather/        WeatherBar.tsx/.css  RiskLegend.tsx/.css  severity.ts
shared/                  styles/{tailwind.css,theme.css}  strings.ts  ui/{Badge,Spinner,Disclosure}.tsx/.css  lib/{format.ts,errors.ts}
```
Styling convention (AGENTS §6): each component has a co-located `.css` starting with `@reference "../../shared/styles/tailwind.css";` using `@apply` on semantic class names. No utility strings in JSX. Dependency: add only `maplibre-gl`.

## 12. Tasks

| ID | Task | Est | Acceptance criteria | Verify |
|---|---|---|---|---|
| U1 | Tokens, panel shell (desktop + mobile sheet), `usePlannerFlow` reducer, `RouteForm` with validation and example chips, API client and `useRoutePlan` | 45 min | All transitions of §3 covered by reducer tests; form errors match API_SPEC §4.1; error-code → message map (§10) tested | `npm test`, manual |
| U2 | `TripMap` (MapLibre): style loading, sources/layers, markers, popups, camera with panel padding, WebGL fallback, `lazy` loading | 75 min | Mocked-`maplibre-gl` tests: fixture response adds one source + two layers per route and the call counts stay constant after re-render and after selection change; selection calls `setPaintProperty`/`moveLayer` only; `fitBounds` padding includes the panel width; coordinates stay `[lon, lat]`; WebGL-unavailable fallback renders | tests + screenshot |
| U3 | Reveal animation: `revealTimeline`, `AnalysisView`, `StepList`, vehicle marker, skip, reduced-motion | 60 min | Timeline pure-function tests (order, total ≤ 5 s, cache-hit speed, reduced motion → none); Skip and Esc work; `aria-live` updates; durations equal `meta.timings_ms` | tests + screen recording |
| U4 | Results view: recommendation header, disclosure, route cards (radio group), stop list, totals, two-way hover | 60 min | Headline for each `recommendation.reason`; totals equal API numbers to the cent; infeasible card muted; keyboard selection works | tests |
| U5 | Weather bar, risk legend, severity-colored selected route, polish, coverage ≥ 70 % | 45 min | `unavailable` weather hides bar/legend; segments colored by severity; `npm run lint && typecheck && test:coverage && build` pass | commands |

## 13. Out of scope

Weather time scrubber/play control, satellite toggle, help modal, truck-weight input, HQ pin, saved trips, draggable bottom sheet, dark mode, any new dependency, any change to API_SPEC.

## 14. Required document changes (CR-UI-1, apply in one `docs:` commit before U1, list every edited line)

| Document | Section | Change |
|---|---|---|
| ARCHITECTURE | §2 technology table (Frontend row), §3 (map library and tile rows), §8 (RouteMap) | Prior raster map library + OSM raster tiles → MapLibre GL JS + OpenFreeMap vector style; OSM tile policy no longer applies; record OpenFreeMap terms (free, no key, attribution required, no stated SLA) |
| ARCHITECTURE | §4 tree, §8 env | `VITE_TILE_URL`/`VITE_TILE_ATTRIBUTION` → `VITE_MAP_STYLE_URL`; map feature files per §11 here |
| AGENTS | §4 frontend row | Replace the previous raster map dependencies with `maplibre-gl` |
| DEPLOYMENT | §2 env table, §3 frontend Dockerfile build args, §6 CSP | replace tile env/args with `VITE_MAP_STYLE_URL`; CSP per §7 here |
| TESTING | §10 Map row | mock `maplibre-gl` at the module boundary; call-based assertions |
| PLAN | T21–T24 | replaced by U1–U5 of this file |
