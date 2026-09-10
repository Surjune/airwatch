# CLAUDE.md — AirWatch conventions

Conventions for this repository. Enforced by tooling (ruff, mypy, ESLint) where enforcement is
possible; the rest are review criteria.

## Architectural decisions already made

Recorded so they are not re-litigated. Anything **not** listed here that changes the architecture
must be raised before implementing.

| Decision | Choice | Rationale |
| --- | --- | --- |
| Python runtime | 3.12 (`requires-python = ">=3.12"`) | Current stable; matches CI. The floor is 3.12, not 3.11, so PEP 695 `type` aliases are available -- the recursive JSON type in `external/base.py` needs one. |
| Database | PostgreSQL 16 + PostGIS 3.4 + TimescaleDB via Docker Compose | Spatial queries and sensor time-series in one engine; container is reproducible. |
| Spatial unit | H3 hexagons, resolution 8 (~0.46 km²) | One index shared by fusion, hotspots, forecasts and federated features. Cross-city model sharing is only coherent if every node uses the same grid. |
| Map library | Leaflet + OpenStreetMap tiles | No access token, so the app runs on a clean clone with zero third-party signup. |
| Auth | None in v1; per-IP rate limiting + locked CORS | Tracked as a Known Limitation in the README. |
| Frontend types | Generated from the FastAPI OpenAPI spec via `openapi-typescript` | Never hand-edit generated files. |
| Federated framework | Flower, FedAvg with FedProx option | Non-IID city distributions; Flower supports both simulation and real deployment. |
| Task runner | `npm run <task>` from the repo root | `make` is not available on Windows; root `package.json` proxies to both workspaces. |

## Layering — the rule that matters most

Dependencies flow in exactly one direction. A module may import from layers **below** it, never
from above or sideways at the same level.

```
routes  ->  services  ->  repositories  ->  database
              |                 |
              +--> external ----+
              +--> ml
              +--> core (importable by everything)
```

- `routes/` parse the request, call exactly one service, return the response. No business rules,
  no arithmetic, no DB access.
- `services/` hold all business logic. They call repositories, external clients and ML wrappers.
  They never touch a `Session` or write SQL. **Services never import other services** — shared
  logic moves down into `core/`.
- `repositories/` are the only place a `Session`/SQL/PostGIS function appears.
- `external/` are thin, typed clients (OpenAQ, CPCB, FIRMS, Open-Meteo, Sentinel-5P) with
  timeouts, retries and typed errors. Business code never imports `httpx` directly.
- `ml/` holds the analysis itself -- fusion, hotspot detection, attribution, forecasting -- as pure
  functions over plain data, plus inference wrappers that load artifacts once at startup. Training
  code lives in `/ml` at the repo root and is never imported at request time.
  **A pure computation belongs here, not in `services/`.** Detection and attribution touch no
  database, so putting them in the service layer forced a route needing both to make one service
  import another, which the layering forbids for good reason.
- `core/` is leaf-level: config, logging, exceptions, constants and every shared calculation. It
  imports nothing from the layers above.

SQLAlchemy ORM models live in `repositories/models.py`. The repository layer is the only layer
permitted to touch the database, so the table definitions belong to it.

## Modularity

- One responsibility per file. A service file over ~300 lines is split by sub-responsibility.
- A pillar must be **deletable**: removing `forecast_service.py`, its route and its frontend
  feature folder must not break hotspot detection.
- Each external client is independently mockable and has its own test file.
- React: one component per file, none over ~200 lines, no fetch logic inside components.

## DRY

- A calculation used in more than one place lives in exactly **one** function in
  `backend/app/core/` and is imported. AQI sub-index math, H3 indexing, and geodesic distance are
  already there — use them, do not re-derive them.
- No copy-pasted fetch boilerplate in React components. Every request goes through
  `frontend/src/lib/api-client.ts`.
- Repeated Tailwind class strings become a component in `components/ui/`.

## No magic numbers

Every threshold, weight, hyperparameter and physical constant lives in a named constant in
`backend/app/core/constants.py` with a comment giving its source or reasoning. A bare numeric
literal in a service or a model is a review failure. Exceptions: `0`, `1`, and array indices.

## Errors

- Every external call has explicit error handling and raises a typed exception from
  `backend/app/core/exceptions.py`. Never `except: pass`, never a bare `except:`.
- Exceptions carry a machine-readable `code` and a human-readable message; the global handler maps
  them to a consistent JSON error envelope. No unhandled 500s.
- Missing credentials or unavailable upstreams produce an explicit typed error. They **never**
  produce fabricated or placeholder readings. In a public-health context a wrong number is worse
  than an error.

## Types

- Python: full annotations on every function, `mypy --strict` clean. No bare `Any`.
- TypeScript: `strict: true`. No `any`. No `@ts-ignore`/`@ts-expect-error` without a comment on the
  line above explaining why it is unavoidable.

## Validation

Every request body, query and path parameter is a Pydantic v2 model using constrained types
(`Annotated[float, Field(ge=..., le=...)]`) and field validators. Validation happens at the
boundary, before business logic. Coordinates, H3 indices and uploaded images are untrusted input
and are validated structurally and semantically.

## Uncertainty is a first-class output

Any estimated quantity — a fused cell value, a citizen-photo PM2.5 proxy, a source attribution —
carries an explicit uncertainty or confidence alongside it, and the UI must show it. A ranked
attribution candidate is never presented as established fact.

## Determinism

Fusion and scoring are pure functions of their inputs. External responses are cached with the
request's spatial + temporal key so a re-run cannot drift because an upstream changed. Anything
non-deterministic (model randomness, FL client sampling) is seeded from `core/constants.py`.

## Observability

Structured JSON logging via `core/logging.py`. Never `print`. Every request gets a correlation ID
(`X-Request-ID`, generated if absent) bound to a context var and appearing on every log line for
that request, including inside services and external clients.

## Testing

- `backend/app/tests/` mirrors `backend/app/` 1:1.
- Tests never make real network calls. Every external client is mocked.
- Model math is tested at its edges: zero sensor coverage, missing data, minimum and maximum
  concentration, and both boundary conditions of the forecast horizon.
- `npm run test:all` from the repo root runs everything.

## Units

Every unit conversion is annotated inline at the point of conversion, naming source and target
unit. Canonical internal units:

| Quantity | Internal unit |
| --- | --- |
| PM2.5 / PM10 | micrograms per cubic metre (µg/m³) |
| Gaseous pollutants | micrograms per cubic metre (µg/m³) at the CPCB reference condition |
| Satellite column density | mol/m² as delivered; converted only at the fusion feature boundary |
| Wind speed | metres per second (m/s), as `wind_u` / `wind_v` components |
| Temperature | degrees Celsius (°C) |
| Distance | metres (m) |
| Timestamps | UTC in storage; IST only at the presentation boundary |
| Coordinates | WGS84 / EPSG:4326, `(longitude, latitude)` order |

GeoJSON is always `(lon, lat)`. Leaflet is always `(lat, lon)`. Convert at the boundary in
`frontend/src/lib/`, never ad hoc in a component.

## Commits

- No commented-out code, no dead code, no unresolved `TODO` in committed state. Deferred work goes
  in the README's "Known limitations" section.
- Commit after every completed task, scoped conventional messages
  (`feat(ingestion): add FIRMS VIIRS client`), pushed immediately.
- Every commit leaves the repo in a working state.
- No AI attribution of any kind in commit messages or PR descriptions.
