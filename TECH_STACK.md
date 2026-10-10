# Tech Stack — APIx

Every choice below is picked for a specific reason tied to what this system has to do: scrape unreliable JS-heavy sites, handle a time-series-heavy dataset, compute a reproducible index, and serve it to both a dashboard and external consumers (NSO/RBI). Alternatives are noted where the trade-off is close.

## 1. Scraping Layer

| Component | Choice | Why |
|---|---|---|
| Static/simple pages | **Scrapy** | Battle-tested Python crawling framework: built-in scheduling, retry/backoff, middleware pipeline, item pipelines — exactly the shape we need for "spider per source." |
| JS-rendered pages (most OTAs, many airline search UIs) | **Playwright** (Python) | Faster and more stable than Selenium for modern SPA-style flight-search UIs; native async support fits Scrapy's async reactor better via `scrapy-playwright`; built-in network interception is useful for reading fare data straight out of XHR/JSON responses instead of scraping rendered DOM. |
| Fallback JS automation | **Selenium** | Kept as a fallback for any source where Playwright hits an incompatibility (rare, but airline sites vary) — problem statement explicitly names it, and it has the widest browser-compatibility track record. |
| Scheduling | **Airflow** (or lightweight **APScheduler**/cron for MVP) | Airflow gives DAG-based daily scheduling with retries, alerting, and a UI to see run history per source — useful once we have 10+ spiders running on independent schedules. APScheduler is the pragmatic MVP substitute if Airflow is too heavy for the hackathon timeline. |
| Rate limiting / anti-bot resilience | Scrapy `AutoThrottle`, custom middleware, rotating proxy pool (e.g. residential/datacenter proxy provider), `fake-useragent` for header rotation | Keeps scraping polite and resilient to transient blocks — see `SECURITY.md §1.2–1.3` for the ethical constraints these are configured under. |
| CAPTCHA handling | Avoid, not defeat — retry/backoff and route around rather than solve (see `SECURITY.md §1.4`) | Consistent with the project's ethical-scraping stance. |

## 2. Data Pipeline

| Component | Choice | Why |
|---|---|---|
| Cleaning/transformation | **Python (pandas)** | Standard for outlier detection, missing-value handling, dedup logic; integrates directly with the Scrapy item pipeline. |
| Message queue / task broker | **Redis + Celery** (or Airflow tasks if already adopted) | Decouples "scrape finished" from "clean & load" so a slow source doesn't block others; also backs the scheduled daily jobs. |
| Fare database | **PostgreSQL** with **TimescaleDB** extension | Fare quotes are fundamentally a time series (route × date-observed × advance-purchase-window). TimescaleDB gives hypertables for efficient time-range queries and continuous aggregates for daily/weekly/monthly rollups, while staying full SQL/Postgres — easy for a student team to reason about and easy to back up. |
| Data quality checks | **pydantic** (for scraped item schema validation) + **Great Expectations** (optional, if time permits) | pydantic gives structural validation for every fare quote before it enters the pipeline; Great Expectations is a stretch-goal for statistical sanity checks (e.g. "fare should not be negative," "total fare ≥ base fare"). |

## 3. Index Construction

| Component | Choice | Why |
|---|---|---|
| Computation | **Python (pandas/NumPy)** | Weighted index formulas (route weights × price relatives) are straightforward vectorized pandas operations; keeps the whole backend in one language. |
| Weight source | **DGCA monthly domestic traffic statistics** (manually ingested CSV, refreshed periodically) | Matches the problem statement's explicit instruction to weight routes by DGCA passenger-traffic data. |
| Back-testing | **Python + matplotlib/plotly for validation plots**, results stored alongside index tables | Needed to demonstrate the required ≥30-day comparison against DGCA published averages. |

## 4. Backend / API

| Component | Choice | Why |
|---|---|---|
| API framework | **FastAPI** | Async-native (matches Playwright/Celery's async nature), automatic OpenAPI docs (useful for handing NSO/RBI a ready-made API spec), built-in request validation via pydantic — same validation library as the scraping layer, one mental model end to end. |
| Auth | API-key based (FastAPI dependency), upgradeable to OAuth2 client-credentials | Simple enough for a hackathon demo, structured enough to harden later — see `SECURITY.md §2.4`. |
| Caching | **Redis** (already present for Celery) | Cache expensive aggregate queries (e.g. "30-day index series") since the underlying data only changes once a day. |

## 5. Dashboard

| Component | Choice | Why |
|---|---|---|
| Framework | **React** (via Next.js) | Component model fits well for reusable chart widgets (trend line, heatmap, elasticity curve) reused across route/date filters; Next.js gives easy static/SSR hosting for a clean demo deployment. |
| Charting | **Recharts** for trend/line charts, **D3** (or a heatmap-specific lib like `react-heatmap-grid`/`nivo`) for the sector-wise heatmap | Recharts covers standard time-series charts with minimal code; D3/nivo needed for the more custom heatmap and lead-time elasticity curve visuals. |
| Styling | **Tailwind CSS** | Fast to iterate on a data-dense dashboard within hackathon time constraints. |
| Data fetching | REST calls to the FastAPI backend, typed via the auto-generated OpenAPI schema | Keeps frontend/backend contract in sync automatically. |

## 6. Infrastructure & DevOps

### 6.1 Deployment Targets (chosen)

| Layer | Platform | Service type | Why |
|---|---|---|---|
| Frontend (dashboard) | **Vercel** | Next.js native hosting | Zero-config deploy for Next.js, preview URLs per PR (useful for a team iterating fast pre-demo), free tier is generous enough for a hackathon judge to load the live site. |
| Backend API | **Render** | Web Service (Docker or native Python runtime) | Runs FastAPI directly; auto-deploys from the `api/` path on push; supports environment-variable secrets management out of the box. |
| Scraper execution | **Render** | **Cron Job** (daily trigger) + optional **Background Worker** (queue-driven) | A Cron Job is Render's dedicated scheduled-task service type — isolated container, spins up on the schedule, runs, tears down, capped at 12h/run — a near-exact match for "scrape the full route×window basket once a day." A Background Worker is the fallback if the team wants a continuously-running queue consumer instead of one daily batch (see `SYSTEM_ARCHITECTURE.md §2.1, §4`). Playwright's headless Chromium needs real memory (budget ≥512MB–1GB per concurrent browser instance) — plan the Render instance size accordingly, not the smallest free tier. |
| Broker/queue (if using the worker pattern) | **Render Key Value** (Redis-compatible) | Replaces a self-hosted Redis instance; used by Celery for the scrape-task queue and by FastAPI for response caching. |
| Database | **Supabase** (managed Postgres) | Provides the Postgres instance behind the data model in `DESIGN.md §2`. Supabase's supported extension set includes `timescaledb` and `pg_cron`, so the hypertable/continuous-aggregate design still applies — enable these from the Supabase dashboard during setup and confirm current availability for your plan/Postgres version, since managed-extension lists do shift over time. |

### 6.2 Local Development
- **Docker + docker-compose** remains the local dev story — bring up a local Postgres (with the same extensions enabled), a local Redis, the API, the scraper, and the dashboard with one command, so the team isn't dependent on live Render/Supabase/Vercel environments for day-to-day iteration. Point `DATABASE_URL` at Supabase only for staging/demo deploys.

### 6.3 CI/CD & Testing

| Component | Choice | Why |
|---|---|---|
| CI | **GitHub Actions** | Runs automated tests (pytest + frontend tests), lint (`ruff`/`flake8`, `eslint`), and dependency audit on every push; on merge to `main`, Render and Vercel auto-deploy from their respective connected branches/paths — no separate deploy step to script. |
| Testing | **pytest** (scraper item parsing, pipeline cleaning logic, index math) + **pytest-vcr/responses** (record/replay HTTP for spider tests without hitting live sites) + **Jest/React Testing Library** (dashboard components) | Item parsing and index formulas are exactly the kind of logic that silently breaks when a source changes its HTML — deterministic unit tests catch that before a demo does. |
| Monitoring/logging (stretch) | Structured logging (`structlog`) + simple run-history table in the DB, optionally Grafana Cloud free tier reading Render logs | Supports the auditability requirement in `SECURITY.md §2.7`. |

### 6.4 Architectural Guardrail

Because Supabase can auto-expose Postgres tables via a REST layer (PostgREST), it's tempting to let the Vercel-hosted dashboard query Supabase directly and skip the API. **Don't** — `SYSTEM_ARCHITECTURE.md §5` deliberately routes the dashboard through FastAPI only, so the API stays a real, versioned, rate-limited contract. That contract is also literally what the problem statement asks for ("provide an API that the NSO and RBI can consume") — bypassing it to save dev time undercuts a graded deliverable.

## 7. Why This Combination Works Together

- **One language (Python) across scraping, pipeline, index, and API** minimizes context-switching for a small hackathon team and lets the same pydantic schemas validate data at every stage.
- **TimescaleDB** means we don't need a separate time-series database — one Postgres instance serves both the raw fare-quote table and the pre-aggregated index tables.
- **FastAPI's auto-generated OpenAPI spec** doubles as the deliverable NSO/RBI would need to integrate APIx as a data source, satisfying the "provide an API" requirement with near-zero extra documentation effort.
- **Docker Compose** makes the whole system judge-runnable in one command — important for a hackathon demo where setup time is part of the evaluation experience.

## 8. Alternatives Considered

| Decision | Alternative | Why not (for this project) |
|---|---|---|
| FastAPI | Django REST Framework | Heavier, more opinionated ORM; FastAPI's async fit with the scraping stack and auto-docs win for this scope. |
| TimescaleDB | MongoDB | Fare data is naturally tabular/relational (route, date, carrier, fare fields) with heavy time-range aggregation — a relational + time-series engine beats a document store here. |
| Next.js/React | Streamlit | Streamlit is faster to prototype but weaker for a polished, interactive multi-view dashboard (heatmaps + elasticity curves + filters) that needs to look like a credible statistical product. |
| Airflow | Plain cron | Airflow chosen once the number of independently-scheduled spiders grows; cron/APScheduler is the acceptable MVP shortcut if hackathon time is tight. |
