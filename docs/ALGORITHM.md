# ALGORITHM.md — FuelRoute Fuel Optimization & Geospatial Matching

Status: source of truth for `apps/geo` and `apps/fuel`. Constants here are the only approved values; code must import them from `apps/common/constants.py` (AGENTS.md §5).

## 1. Problem statement

Given one driving route (polyline, total length `D` miles) and a set of fuel stations with prices, choose **where to stop and how much to buy** so the vehicle reaches the destination without ever running out of fuel, minimizing total money spent on fuel.

Route selection (which of up to 3 OSRM alternatives) is a **separate, outer step** (§10). The optimizer in this document operates on **one fixed route at a time**.

## 2. Constants and assumptions (normative)

| Name | Value | Meaning / rationale |
|---|---|---|
| `MPG` | 10.0 | Given by assessment. |
| `MAX_RANGE_MILES` | 500.0 | Given by assessment. |
| `TANK_CAPACITY_GAL` | 50.0 | `MAX_RANGE_MILES / MPG`. The 500-mile range is modeled as a 50-gallon usable tank. |
| `START_FUEL_GAL` | 0.0 (request option `start_fuel_gal`, 0–50) | **Starting fuel assumption.** Default: tank empty at origin; the first fill is a priced purchase (§5). Fuel already onboard (when the option > 0) is free (sunk cost) and is not part of `total_fuel_cost_usd`. |
| `RESERVE_GAL` | 0.0 | Fuel that must remain on arrival at every stop and the destination. 0 = the stated 500-mile theoretical range is fully usable. Configurable; tests cover 5.0. |
| `FUEL_UNIT_GAL` | 0.01 | DP fuel grid. 1 unit = 0.01 gal = 0.1 mile of range. |
| `SAFETY_MARGIN_UNITS` | 1 | Extra 0.1 mile of fuel required at every arrival; absorbs grid rounding (proof §7). |
| `STATION_CORRIDOR_MILES` | 10.0 | Station eligible if straight-line distance to route ≤ this. |
| `CIRCUITY_FACTOR` | 1.3 | Straight-line → road distance multiplier for detours. |
| `ORIGIN_SNAP_MILES` | 25.0 | Radius to find the price of the initial fill (§5). |
| `STOP_PENALTY_USD` | 0.005 | Tie-breaker added per visited station so the optimizer never makes pointless micro-stops (§6.4). |
| `PRICE_AGGREGATION` | `median` | How duplicate price rows per station collapse (ARCHITECTURE §5.1). |
| `MAX_CANDIDATES` | 1500 | Cap on stations entering the DP after dominance pruning (§8). |
| `MAX_DURATION_RATIO` | 1.25 | Route selection: discard routes slower than this × fastest feasible (§10). |
| `RESERVE_UNITS` | `round(RESERVE_GAL / FUEL_UNIT_GAL)` | Derived; `m = RESERVE_UNITS + SAFETY_MARGIN_UNITS`. |

**Operational constants** (also in `apps/common/constants.py`, defined in ARCHITECTURE; listed so no module hard-codes them): geocode TTL 30 days (negative 1 h), route cache TTL 24 h, weather TTL 1 h, plan cache TTL 1 h, Nominatim min interval 1.05 s, HTTP timeouts (geocoding 5 s, routing 8 s, weather 3 s), weather sample spacing 100 mi and max 12 samples per route, display geometry cap 2,000 points, matching/display simplification tolerances 0.05 / 0.25 mi, contiguous-US bounding box lat 24.0–49.5 / lon −125.0 to −66.5, `MIN_ROUTE_MILES` 1.0.

**Partial refueling policy.** Any amount may be bought at any visited station, in 0.01 gal increments, up to tank capacity. Buying "just enough" is allowed and often optimal.

**Station detour policy.** A station off the route is reachable by a round-trip detour of `detour_miles = 2 × CIRCUITY_FACTOR × offset_miles`, where `offset_miles` is the perpendicular distance to the route. The detour burns fuel (`detour_miles / MPG` gal), which must be purchased, so detours are priced into the objective. No extra routing API call is made for detours (call budget: ARCHITECTURE §6.7).

**Leftover fuel.** Fuel remaining at the destination is **worth $0**. The optimizer therefore never buys fuel it will not use, except grid-rounding slack of at most `SAFETY_MARGIN_UNITS + #detour-roundings` units (≤ ~0.1 gal, reported in `fuel_plan.totals.leftover_gal`). Crediting leftover fuel at some price was rejected: it would reward overbuying at cheap stations and misstate "money spent".

## 3. Equations

```
fuel_gal(miles)           = miles / MPG
range_miles(fuel_gal)     = fuel_gal × MPG
route_fuel_gal            = D / MPG
detour_miles(i)           = 2 × CIRCUITY_FACTOR × offset_miles(i)
detour_fuel_gal(i)        = detour_miles(i) / MPG
fuel_consumed_gal         = route_fuel_gal + Σ detour_fuel_gal(i) over visited stations i
purchase_cost_usd(i)      = gallons_bought(i) × price_per_gal(i)
total_fuel_cost_usd       = Σ purchase_cost_usd(i)               (all en-route purchases incl. initial fill)
fuel_purchased_gal        = fuel_consumed_gal − START_FUEL_GAL + leftover_gal
avg_price_per_gal         = total_fuel_cost_usd / fuel_purchased_gal
cost_per_mile             = total_fuel_cost_usd / D
```

## 4. Station eligibility and route projection

Input: route polyline `P = [p0 … pm]` (decoded polyline6, `[lat, lon]`), stations table in memory (`StationIndex`: numpy arrays `lat`, `lon`, `price`, `id`).

1. **Cumulative distance.** `cum[k]` = haversine path length to vertex `k` (R = 3958.7613 mi). Scale all values by `osrm_distance_miles / cum[m]` so the total equals OSRM's reported distance (haversine under-measures curved roads slightly; scaling keeps mile markers consistent with the displayed distance).
2. **Bounding-box prefilter.** Route bbox expanded by `STATION_CORRIDOR_MILES` (convert miles→degrees: 1° lat = 69.0 mi; 1° lon = 69.17·cos(lat) mi). Keeps typically 5–15% of 6,626 stations.
3. **Matching geometry.** Simplify the route with Douglas–Peucker at 0.05 mi tolerance (matching copy only; display copy uses 0.25 mi). Expect ≤ ~6,000 segments for a 2,800-mile route.
4. **Point-to-segment distance (vectorized).** For each candidate station and each segment (processed in chunks of ≤ 2,000,000 pairs) use a local equirectangular projection centered on the station's latitude: `x = Δlon·cos(lat0)·69.17`, `y = Δlat·69.0`. Compute the projection parameter `t = clamp(((s−a)·(b−a))/|b−a|², 0, 1)` and the distance to `a + t(b−a)`. Per station keep the segment with minimum distance (`argmin`). Error vs haversine ≤ 0.1% for offsets ≤ 10 mi.
5. **Eligibility.** Keep stations with `offset_miles ≤ STATION_CORRIDOR_MILES`.
6. **Route mile marker.** `route_mile = cum[seg] + t × seg_length` (scaled). A station whose nearest approach is a loop-back (route passes near it twice) is assigned the **earliest** mile marker within 1 mile of the minimum offset; this is conservative for reachability and documented in tests.
7. Output: array of `Candidate(station_id, route_mile, offset_miles, detour_miles, price)` sorted by `(route_mile, price, station_id)`.

**Known data limitation.** The CSV has no coordinates. Station positions are **city/place centroids** (`geocode_precision = "place_centroid"`), typically 1–8 miles from the real truck stop. The 10-mile corridor and the conservative detour formula tolerate this; positions are not claimed to be exact. P3 refinement: geocode the "I-xx, EXIT nnn" strings.

## 5. Origin node and destination node

* **Origin node** `N0`: position 0, detour 0, price `p0`. `p0` = price of the nearest station (haversine) within `ORIGIN_SNAP_MILES` of the route start, else the median price of the origin's state, else the national median. The chosen source is returned as `origin_price_source` (`nearest_station | state_median | national_median`). It exists because with an empty tank the vehicle cannot drive to a detoured station. It is shown to the user as the first stop with `kind = "origin_fill"` naming that nearest station.
* **Destination node** `N(n+1)`: position `D`, no price, no purchase.

If `START_FUEL_GAL ≥ D/MPG + margin`, no purchase is required: the plan has zero stops and `total_fuel_cost_usd = 0` (`status = "no_refuel_needed"`).

## 6. Optimization

### 6.1 Why not a greedy "cheapest next stop"

A cheapest-reachable greedy is not globally optimal once detours and per-station price differences interact. The classical gas-station problem (Khuller, Malekian & Mestre, 2007) shows an optimal look-ahead structure *for stations exactly on a line without detours*: buy just enough to reach the next cheaper station within range, otherwise fill the tank. FuelRoute adds detour costs and fuel-dependent feasibility, so we use an **exact dynamic program** and use the classical rule only as a **test oracle** (TESTING §5).

### 6.2 Model

Nodes `0..n+1` ordered by snapped position `s̃_i` (§7). Let `C = TANK_CAPACITY_GAL / FUEL_UNIT_GAL = 5000` units, `δ = FUEL_UNIT_GAL`. For node `i`: price `p_i`, half-detour `h_i = ceil((detour_miles_i / 2) / MPG / δ)` units (0 for origin), gap to next node `g_i = (s̃_{i+1} − s̃_i)/MPG/δ` units (exact integer by construction), `m = RESERVE_UNITS + SAFETY_MARGIN_UNITS`.

State `A_i[f]` = minimum cost to be **on the route at node i's position with `f` fuel units**, before deciding whether to visit station i.

Objective: minimize `J = Σ price × gallons_bought + STOP_PENALTY_USD × (#visited stations)`.

### 6.3 Transitions at node i

1. **Skip:** `B_i[f] = A_i[f]`.
2. **Visit** (only for stations, `h_i` units each way): arrive at the station with `g = f − h_i ≥ m` (the margin applies at the station too; for the origin node `h_0 = 0` and the requirement is `g ≥ 0`); buy `b ≥ 0` so `q = g + b ≤ C`; cost `A_i[g + h_i] + b·δ·p_i + STOP_PENALTY`; leave and return to route with `q − h_i ≥ 0` units: candidate for `B_i[q − h_i]`.
   Closed form per node, all `q` at once (vectorized):
   `V[q] = p_i·δ·q + cummin_{g ≤ q}( a[g] − p_i·δ·g )`, with `a[g] = A_i[g + h_i] + STOP_PENALTY` for `g ≥ g_min` and `+∞` for `g < g_min`, where `g_min = m` for stations and `0` for the origin; `q ∈ [h_i, C]`.
   `B_i[q − h_i] ← min(B_i[q − h_i], V[q])` **only if strictly smaller than the skip value** (ties → skip → fewer stops).
3. **Drive:** `A_{i+1}[f − g_i] = B_i[f]` for `f ≥ g_i + m`, otherwise infeasible (`+∞`). The margin `m` is applied at every arrival (also the destination).

Initialization: `A_0[f0] = 0` with `f0 = round(START_FUEL_GAL/δ)`, all else `+∞`. For the origin node, the visit transition has `h_0 = 0` and no stop penalty is charged if only the origin fill is used (it is not an optional visit, but a purchase at `p0`; implemented as visit with `h=0` and penalty 0).

Answer: `min_{f ≥ m} A_{n+1}[f]` (leftover fuel valued at $0). If all values are `+∞`, the route is infeasible (§9).

### 6.4 Optimality statement (what is and is not claimed)

The DP is **exact** for the model above: fixed route, candidate set = stations within the corridor, positions snapped as in §7, fuel quantized to 0.01 gal, objective `J`. Compared with the continuous problem (any real gallon amounts, exact positions) the cost differs by at most: `(#stops × 0.01 gal × max price spread) + STOP_PENALTY × #stops`, i.e. under $0.50 for realistic plans. It does **not** claim optimality over routes not returned by OSRM, over stations outside the corridor, or over true truck-stop coordinates (data limitation §4).

### 6.5 Pseudocode

```python
def optimize(nodes, dest_mile, cfg, start_fuel_units) -> FuelPlan | Infeasible:
    C, m = cfg.capacity_units, cfg.reserve_units + cfg.margin_units
    INF = float("inf")
    A = np.full(C + 1, INF); A[start_fuel_units] = 0.0
    back = []                                   # per node: (visit_mask[C+1], arrive_g[C+1])
    for i, node in enumerate(nodes):            # nodes[0] = origin, sorted by snapped mile
        B = A.copy()
        visit_mask = np.zeros(C + 1, bool)
        arrive_g = np.zeros(C + 1, np.int32)
        if node.price is not None:
            h, pd = node.half_detour_units, node.price * DELTA
            pen = 0.0 if node.is_origin else STOP_PENALTY
            a = np.full(C + 1, INF)
            a[: C + 1 - h] = A[h:] + pen         # a[g] = A[g + h] + pen
            g_min = 0 if node.is_origin else m   # margin also applies on arrival at the station
            a[:g_min] = INF
            g_idx = np.arange(C + 1)
            tmp = a - pd * g_idx
            run_min = np.minimum.accumulate(tmp)
            # argmin positions of the running minimum (index of the first position attaining it)
            arg = running_argmin(tmp, run_min)
            V = pd * g_idx + run_min             # V[q]
            q = np.arange(h, C + 1)
            cand = V[q]
            tgt = q - h
            better = cand < B[tgt] - 1e-12       # strict: tie -> skip
            B[tgt[better]] = cand[better]
            visit_mask[tgt[better]] = True
            arrive_g[tgt[better]] = arg[q[better]]
        back.append((visit_mask, arrive_g))
        gap = node.gap_units_to_next            # last station node: gap to the destination
        A_next = np.full(C + 1, INF)
        ok = np.arange(C + 1) >= gap + m
        A_next[(np.arange(C + 1) - gap)[ok]] = B[ok]
        A = A_next                              # after the loop, A is A_dest
    f_star = argmin over f >= m of A[f]
    if cost is INF: return Infeasible(largest_gap(nodes, C))
    return reconstruct(back, f_star, nodes)     # walk nodes in reverse (§6.6)
```

`running_argmin` returns, for each index, the index of the running minimum (computed with `np.maximum.accumulate` over `np.where(tmp == run_min, idx, 0)`).

### 6.6 Reconstruction

Walk from the destination backwards with `f = f_star`: at node `i`, if `visit_mask[f]` then `q = f + h_i`, `g = arrive_g[f]`, record purchase `(q − g)` units at station `i`, set `f_arrive = g + h_i`; else `f_arrive = f`. Previous node's `f = f_arrive + gap_{i−1}`. Convert purchases to gallons (`× δ`) and cost (`× price`). Drop zero-unit purchases (cannot occur given the strict tie rule; asserted).

### 6.7 Independent validation (mandatory)

`validate_plan(plan, route, cfg)` re-simulates the plan **with exact float distances (unsnapped miles)**:

```
fuel = start_fuel
pos = 0
for stop in plan.stops:                 # sorted by route_mile
    fuel -= (stop.route_mile - pos) / MPG
    fuel -= stop.detour_miles / 2 / MPG
    assert fuel >= RESERVE_GAL - 1e-9
    fuel += stop.gallons_bought; assert fuel <= TANK_CAPACITY_GAL + 1e-9
    fuel -= stop.detour_miles / 2 / MPG; assert fuel >= -1e-9
    pos = stop.route_mile
fuel -= (D - pos) / MPG
assert fuel >= RESERVE_GAL - 1e-9
```

The planner calls the validator on every plan and returns `INTERNAL_ERROR` (never an invalid plan) on failure. This is the runtime guarantee of reachability; §7 explains why it never fires.

## 7. Why every stop is reachable (proof sketch)

1. Constraint `f ≥ g_i + m` on every drive transition forces fuel ≥ 0 over each leg in the snapped model, and ≥ `m` units on arrival.
2. Snapped positions: `s̃ = ceil(s / 0.1 mi) × 0.1 mi`, destination likewise. Gaps are differences of snapped positions, so they **telescope**: for any chosen stops `a < b`, `s̃_b − s̃_a ∈ (s_b − s_a − 0.1, s_b − s_a + 0.1)` and the error does not accumulate across stops.
3. Detour half-legs are rounded **up** (conservative, never under-counted).
4. Therefore real fuel at any arrival ≥ snapped fuel − 1 unit ≥ `RESERVE_UNITS` (the extra `SAFETY_MARGIN_UNITS = 1` absorbs exactly that error). "Arrival" includes the arrival **at the station after the outbound half-detour** (`g ≥ m`, §6.3), the arrival back on the route at the next node, and the destination. Capacity is respected by construction (`q ≤ C`).
5. §6.7 verifies this independently on exact floats.

## 8. Complexity

* Matching: `O(S_c × M)` for `S_c` bbox candidates and `M` simplified segments, chunked numpy; ≈ 1,500 × 6,000 = 9M pair evaluations for a coast-to-coast route.
* DP: `O(n × C)` time with numpy-vector inner steps (`n` candidates ≤ `MAX_CANDIDATES = 1500`, `C = 5000` → 7.5M cell updates ×~6 vector passes); memory `O(n × C)` for back-pointers as `int16/bool` ≈ 1,500 × 5,000 × 3 B ≈ 22 MB worst case.
* If `n > MAX_CANDIDATES`: thin by **dominance pruning** — drop station `j` if another station `k` within 0.5 mi of `j` along the route has `price_k ≤ price_j` and `detour_k ≤ detour_j`. This keeps the optimum (dominated stations are never strictly better). Log `pruned_count`.
* Target: optimizer ≤ 150 ms per route on the dev VPS class (2 vCPU) for `n ≈ 600`.

## 9. Edge cases (each has a test in TESTING §5)

| # | Case | Required behavior |
|---|---|---|
| E1 | Route ≤ 500 mi, `start_fuel_gal = 0` | Buy only what is needed; ≥ 1 stop (origin fill). |
| E2 | `start_fuel_gal` covers the trip | `no_refuel_needed`, 0 stops, $0. |
| E3 | Zero stations in corridor | Only origin fill possible → feasible iff `D ≤ 500 − margin`; else `NO_FEASIBLE_FUEL_PLAN`. |
| E4 | Gap between consecutive reachable stations > 500 mi | `NO_FEASIBLE_FUEL_PLAN` with `details.largest_gap {from_mile, to_mile, gap_miles}`. |
| E5 | Two stations at the same mile marker | Both are nodes with zero gap; DP picks the better; deterministic tie-break `(price, station_id)`. |
| E6 | Equal prices everywhere | Minimum stops; no micro-purchases (strict ties + `STOP_PENALTY_USD`). |
| E7 | Station exactly 500.0 mi from the previous stop | Infeasible because of the 0.1-mi safety margin; reachable at ≤ 499.9 mi (documented). |
| E8 | `RESERVE_GAL = 5` | Max leg becomes 450 mi; tests verify arrival fuel ≥ 5 at every stop. |
| E9 | Cheaper station is off-route with a large detour | Chosen only if savings exceed the detour fuel cost (worked example B). |
| E10 | Route passes the same station twice (loop) | Earliest mile marker used (§4.6). |
| E11 | Price outliers (max $6.399 in data) | No special handling; DP avoids them naturally. Prices ≤ 0 or > 20 → station rejected at import. |
| E12 | Very short route (< 1 mi) | Request rejected by validation (API_SPEC §4), not by the optimizer. |
| E13 | Start point beyond `ORIGIN_SNAP_MILES` of any station | `state_median` price with `origin_price_source` flagged. |

## 10. Route selection (separate from fuel optimization)

For every OSRM route (≤ 3): run §4–§6 independently → `{distance, duration, total_fuel_cost, num_stops, weather_risk}`. **Recommendation rule** (deterministic):

1. Discard routes with an infeasible fuel plan.
2. Discard routes slower than `MAX_DURATION_RATIO (1.25) × fastest feasible duration`.
3. Among the rest, discard routes with `weather.risk_level == "severe"` if any non-severe route remains.
4. Choose the lowest `total_fuel_cost_usd`; ties → lower duration → lower route id.

The reason code of the choice is returned (`recommendation.reason`). Weather never changes the fuel plan; it only informs step 3 and the displayed comparison.

## 11. Worked examples

### Example A — optimal vs "fill at every stop" (no detours)

`D = 900 mi`, `start_fuel = 0`, origin price `p0 = $3.50`.

| Node | Mile | Price |
|---|---|---|
| Origin | 0 | 3.50 |
| S1 | 100 | 3.00 |
| S2 | 450 | 3.40 |
| S3 | 590 | 3.10 |

(Safety margin of 0.01 gal omitted for readability.)

Optimal plan: origin buy 10.0 gal (just reach S1) → $35.00; at S1 (cheapest in reach) fill to 50 gal → $150.00, arrive S3 (490 mi later) with 1.0 gal; at S3 buy 30.0 gal (31 gal needed, 1 on hand) → $93.00. S2 skipped (more expensive than S1 and S3). **Total = $278.00**, gallons bought 90 = 900/10, leftover 0.

Naive "fill the tank at every stop": 10.0 gal ($35.00) + S1 50.0 ($150.00) + S2 35.0 ($119.00) + S3 14.0 ($43.40) = **$347.40**, 109 gal bought, 19 gal wasted at the destination. Difference $69.40.

### Example B — detour breakeven

Two stations at mile 200: A at $3.00 with `offset = 8 mi` → `detour = 2 × 1.3 × 8 = 20.8 mi = 2.08 gal`; B at $3.15 on the route (`detour = 0`). Buying `q` gallons:
`cost_A = (q + 2.08) × 3.00`, `cost_B = q × 3.15` (to first order; extra detour fuel must also be bought).
`A` wins iff `0.15 q > 6.24` → `q > 41.6 gal`. For `q = 40` the on-route station B wins by `126.00 vs 126.24` ($0.24). The DP reproduces this breakeven (test `test_detour_breakeven`).

### Example C — infeasible gap

Stations at miles 0 (origin), 300, and 850 on a 900-mile route: gap 550 > 500 → `NO_FEASIBLE_FUEL_PLAN`, `largest_gap = {from_mile: 300, to_mile: 850, gap_miles: 550}`.
