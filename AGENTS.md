# AGENTS.md — Instructions for the implementing AI agent (Google Antigravity)

Read this file completely before touching the repository. These rules override your defaults.

## 1. Product purpose

FuelRoute is a Django REST API (with a React map UI) built for Spotter's Backend Django Engineer assessment. Given two US locations it returns the driving route geometry, cost-optimal fuel stops under a **500-mile range at 10 MPG** using the supplied fuel-price CSV, and the total fuel money spent. Weather is an optional extra. The assessment core must work without weather and without the frontend. Deadline context and priorities: PLAN.md §2.

## 2. Source-of-truth documents and precedence

| Topic | Document | Precedence |
|---|---|---|
| Numbers, equations, optimizer behavior | `ALGORITHM.md` | 1 (wins on any numeric conflict) |
| Request/response/error contracts | `API_SPEC.md` | 2 |
| Structure, technology, data model, caching | `ARCHITECTURE.md` | 3 |
| Order of work, acceptance criteria | `PLAN.md` | 4 |
| Tests | `TESTING.md` | 5 |
| Build, run, deploy | `DEPLOYMENT.md` | 6 |
| Agent behavior | `AGENTS.md` | applies to everything |

If two documents disagree, stop and report it (§11). Do not choose silently.

## 3. Mandatory start-of-session routine

1. `git status`, `git log --oneline -20`, list the repository tree.
2. Read all seven documents. Read the files of the area you will touch.
3. State which task ID (PLAN.md) you are about to do and its acceptance criteria, then begin. If the repository state contradicts the plan (missing prerequisite task, unexpected files), stop and report.

## 4. Approved technology stack (nothing else without approval)

| Layer | Approved |
|---|---|
| Backend runtime | Python 3.13 (confirm supported by the pinned Django), Django (latest stable series, verified at djangoproject.com; record the version in README), Django REST Framework, `psycopg[binary]`, `numpy`, `httpx`, `polyline`, `gunicorn`, `django-cors-headers`, `python-json-logger` |
| Backend dev/test | `pytest`, `pytest-django`, `pytest-cov`, `respx`, `hypothesis`, `ruff`, `pip-audit`, `import-linter` |
| Database | PostgreSQL 17. **No PostGIS, Redis, Celery, pandas, shapely, geopandas, GeoDjango.** |
| Frontend | React, TypeScript (strict), Vite, Tailwind CSS v4 (`@tailwindcss/vite`), Leaflet, `react-leaflet`, `@tanstack/react-query` |
| Frontend dev/test | Vitest, `@vitest/coverage-v8`, React Testing Library, `@testing-library/user-event`, `@testing-library/jest-dom`, jsdom, MSW, ESLint with `typescript-eslint` |
| Infra | Docker, Docker Compose v2, Nginx, GitHub Actions, Ubuntu VPS, Let's Encrypt via certbot |
| External APIs | OSRM (routing), Nominatim (geocoding), Open-Meteo (weather), OSM raster tiles (dev only) |

**Dependency rule.** Before adding any package not listed: stop, name the package, the exact need, the alternatives considered (including "write 20 lines instead"), and its licence and maintenance status; wait for approval. Pin every dependency to an exact version in `requirements/*.txt` / `package-lock.json`. Prefer the standard library (`csv`, `statistics`, `dataclasses`, `heapq`, `math`).

## 4a. Version verification rule

Facts in the documents marked ⚠ or "verify" (Django series, Python support, `alternatives=<n>` behavior of OSRM, Open-Meteo terms/pricing, GitHub Action major versions, Census Gazetteer source URL) were **not** confirmed when the blueprint was written. Verify each against the primary source during the relevant task, record the finding in the task report, and request approval if it changes a decision.

## 5. Directory structure

Exactly as ARCHITECTURE.md §4. Do not create top-level directories or new Django apps not listed there. Dependency direction: `planner → fuel, geo, weather, stations → common`; `apps/fuel` has no Django, ORM, HTTP or file imports (enforced by `tests/unit/test_architecture.py`).

## 6. Coding conventions

**Python**
* `ruff` (line length 100) must pass with no suppressions except with a one-line justification.
* Type hints on every function signature; frozen `@dataclass` for domain data; no mutable default arguments.
* All tunable numbers come from `apps/common/constants.py` (values per ALGORITHM §2). **No magic numbers** (500, 10, 50, 1.3, 0.01, 10 miles, TTLs, timeouts) in other modules.
* Views are thin (parse → service → serialize). No business logic in views, serializers or models.
* Raise `ApiError(code, …)` with codes from API_SPEC §3 only; never return ad-hoc error shapes; never expose stack traces or upstream bodies in responses.
* No `print`; use `logging` with the structured fields of ARCHITECTURE §10. Never log secrets.
* All outbound HTTP goes through the provider classes with explicit timeouts (ARCHITECTURE §7). Never call an external API from tests, from import time, or from a view directly.
* Money: compute with `Decimal` at the boundary where cost is aggregated and rounded (2 dp); the optimizer may use floats internally. Rounding rules: API_SPEC §4.2.
* No global mutable state except the documented `StationIndex` singleton and provider throttle.

**TypeScript / React**
* `strict: true`; no `any`, no `@ts-ignore`; function components and hooks only.
* **Feature-based structure** (`src/features/<feature>/…`), shared code only in `src/shared`. A feature must not import from another feature's internals; use its `index.ts`.
* **Styling convention:** every component has a co-located plain CSS file (`Component.css`) that starts with `@reference "../../shared/styles/tailwind.css";` and uses `@apply` for Tailwind utilities. **No Tailwind utility strings in JSX `className`s** — class names are semantic (`route-card`, `route-card__title`). This is a deliberate project convention that satisfies the Tailwind requirement.
* Types mirror API_SPEC exactly in `features/route-planner/types.ts`.
* When you present code in a report or chat, give complete files, not fragments or diffs, unless the file is longer than 300 lines (then give the complete changed functions with the file path).

## 7. Architectural boundaries (do not cross)

* Route selection and fuel optimization are separate (ALGORITHM §10 vs §6).
* The optimizer is exact over the stated model; do not replace it with a greedy heuristic, reduce `FUEL_UNIT_GAL`, change tank/reserve/start-fuel/leftover/detour policies, or alter the objective without approval.
* External call budget per cold request: geocoding ≤ 2, routing = 1, weather ≤ 1. Do not add calls (e.g., per-station routing) — detours use the formula.
* Weather must never change the fuel plan and its failure must never fail the request.
* Station positions are city centroids; never present them as exact.
* The frontend only talks to `/api/v1`; it contains no optimization logic.

## 8. Testing requirements

* Every task ships with its tests from TESTING.md (use the exact test names listed). A task is not complete until the relevant tests pass **and** the whole suite passes.
* Tests never use the real network (conftest blocker); fixtures come from `backend/tests/fixtures/`.
* Run before every commit: backend `ruff check . && ruff format --check . && pytest -m "not perf"`; frontend `npm run lint && npm run typecheck && npm test`.
* Coverage targets: TESTING §11. Do not lower thresholds to make CI pass.
* For critical tests (R7, R9, R20) prove the test can fail: break the code briefly, see it fail, restore, and say so in the report.

## 9. Workflow, reporting, and approval gates

**One logical task at a time** (PLAN.md IDs). For each task:

1. Announce the task ID and acceptance criteria.
2. Inspect existing code; implement only that task.
3. Run the verification commands of the task.
4. Commit (format in §10).
5. Report in exactly this template (terse; no pleasantries):

```
Task: T07 geometry primitives
Files: <created/changed list>
Commands run: <command> → <result summary, test counts, coverage numbers>
Acceptance: [x] criterion 1 — evidence ; [ ] criterion 2 — NOT MET: reason
Deviations/conflicts: none | <description and request for approval>
Open questions: none | <…>
Next: T08 (waiting for approval at phase boundary: yes/no)
```

6. **Wait for approval before starting the next phase** (Phase 0 … 6 in PLAN.md). Within a phase, continue to the next task only if the previous task is fully verified.

**Verification honesty.** Never say a feature "works", "passes", or "is deployed" without having run the command that shows it in this session. Paste or summarize actual output. If something could not be run (network blocked, no Docker), say so explicitly and mark the criterion as NOT VERIFIED. Never mark a criterion met on the basis of reading code.

## 10. Git workflow

* Work on `task/Txx-slug` branches off `main`; merge to `main` only when the task is verified and the user approved the phase (or the task is inside an approved phase).
* Commit format: `type(scope): summary [Txx]`, `type ∈ feat|fix|test|docs|chore|refactor|ci`. One logical change per commit; commit after each verified task.
* Tags per PLAN §7.
* Never: `git push --force`, `--no-verify`, history rewriting of pushed commits, committing `.env`, secrets, dumps, `node_modules`, caches, or large binaries. Never edit `data/fuel-prices-for-be-assessment.csv`.
* Do not push or open PRs unless the user asks.

## 11. Conflicts and changes to architecture

If an implementation need conflicts with any document, or you think a decision is wrong:
1. Stop work on the affected task.
2. Report: the document and section, the conflict, the options with trade-offs, your recommendation.
3. Wait for explicit approval. If approved, update **all** affected documents in the same commit (`docs:` type) so they stay consistent.

Silent changes to architecture, API shape, constants, algorithm, dependencies, or directory structure are forbidden.

## 12. Environment configuration

* Config only through environment variables (DEPLOYMENT §2). `.env.example` lists every variable with dummy values; update it whenever you add one. `.env` is git-ignored.
* `APP_CONTACT` is mandatory for outbound `User-Agent`. **Never hard-code a personal email address or name anywhere in code, fixtures, docs, or User-Agent strings.** If the value is missing, fail fast at startup in prod settings and use `https://github.com/example/fuelroute` placeholder only in `.env.example`/tests.
* Settings: `base`, `dev`, `prod`, `test`. `prod` must pass `python manage.py check --deploy`.

## 13. Security restrictions

* No secrets in the repository, logs, error messages, or images.
* No disabling TLS verification, CSRF/host checks, or `DEBUG=True` outside dev settings.
* Never run `curl … | sh`, `sudo`, destructive commands (`rm -rf` outside the working tree, `DROP`, `docker system prune`, volume deletion) without explicit approval.
* Respect provider policies: Nominatim ≤ 1 request/s, descriptive User-Agent, cache everything, no bulk or autocomplete; OSRM demo ≤ 1 request/s and never use it in load tests; tile.openstreetmap.org for development only. Any script that touches a public API must throttle and be run manually, once.
* Validate all input with serializers; no string-built SQL; no shell invocation with user input.
* No new endpoints beyond API_SPEC §1. Django admin and DRF browsable API stay disabled.

## 14. Out of scope (do not build, suggest, or scaffold)

User accounts/auth · saved or shared trips · multi-stop/waypoint routing · turn-by-turn directions · live traffic/tolls · other fuel types/EVs · user-configurable MPG, range, or tank · Canada/Mexico · live price feeds or scraping · admin UI · notifications · i18n · payments · PostGIS · Redis · Celery · analytics/telemetry · any feature not in PLAN.md. If you believe something out of scope is needed, follow §11.

## 15. Do not modify unrelated files

Touch only files required by the current task. Do not reformat, rename, reorder imports, upgrade dependencies, or "clean up" files you were not asked to change. If a refactor seems necessary, propose it (§11) instead of doing it. Generated files (lockfiles) change only as a direct consequence of an approved dependency change.

## 16. Definition of "task complete"

All acceptance criteria met with evidence · full suite green · lint/type checks clean · docs updated if behavior or configuration changed · commit created · report delivered in the §9 template.
