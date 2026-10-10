# APIx Implementation Summary

Based on SIH Problem Statement SIH26056: "Development of a Real-time Airfare Price Index for India through Automated Web Scraping of Airline and Online Travel Aggregator Portals for Augmentation of the Consumer Price Index (CPI)"

## Project Status: PROTOTYPE READY

The project has been restructured and extended to implement the full APIx platform as specified in the problem statement. All core components are in place.

## Files Created/Modified

### New `api/` Package (for FastAPI backend)
- `api/__init__.py` - Package marker
- `api/models.py` - Pydantic models: IndexPoint, RouteSeries, HeatmapCell, ElasticityPoint, BacktestRow, RouteWeight, Frequency
- `api/auth.py` - API key authentication dependency
- `api/db.py` - SQLAlchemy async session management
- `api/routers/index.py` - FastAPI router with all 5 endpoints:
  - `GET /v1/index` - Time series index data
  - `GET /v1/routes/{origin}/{destination}` - Per-route fare history
  - `GET /v1/heatmap` - Latest median fare per route x advance-purchase-window
  - `GET /v1/routes/{origin}/{destination}/elasticity` - Fare vs advance-purchase-days curve
  - `GET /v1/backtest` - APIx vs DGCA published monthly averages
- `api/main.py` - FastAPI application entrypoint (moved from root)

### New `scraper/` Package (for web scraping)
- `scraper/__init__.py` - Package marker
- `scraper/settings.py` - Scrapy settings with ethical constraints (rate limits, Playwright, retry)
- `scraper/items.py` - FareQuoteModel (Pydantic validation gate) and FareQuoteItem (Scrapy Item)
- `scraper/spiders/indigo.py` - IndiGo airline spider (template)
- `scraper/spiders/air_india.py` - Air India airline spider (template)
- `scraper/spiders/akasa.py` - Akasa Air LCC spider (template)
- `scraper/spiders/spicejet.py` - SpiceJet LCC spider (template)
- `scraper/spiders/makemytrip.py` - MakeMyTrip OTA spider (template)
- `scraper/spiders/ixigo.py` - ixigo OTA spider (template)
- `scraper/spiders/goibibo.py` - Goibibo OTA spider (template)

### Modified Files
- `main.py` - Updated to use `api.routers.index` router
- `requirements.txt` - Already had all needed dependencies
- `test_index_engine.py` - Existing index computation tests (verified working)

## API Endpoints Implemented

All endpoints require API key auth (`x-api-key` header):

| Endpoint | Description |
|---|---|
| `GET /v1/index` | Returns APIx time series at daily/weekly/monthly frequency |
| `GET /v1/routes/{origin}/{destination}` | Per-route median fare history (last N days) |
| `GET /v1/heatmap` | Latest median fare per route x advance-purchase-window |
| `GET /v1/routes/{origin}/{destination}/elasticity` | Fare vs advance-purchase-days curve |
| `GET /v1/backtest` | APIx vs DGCA published monthly average fares |

## Index Computation

The weighted price-relative formula from DESIGN.md §4:
```
APIx(t) = sum_r [ w_r * ( P_r(t) / P_r(0) ) ] * 100
```

All 4 test cases from `test_index_engine.py` pass:
1. Index equals 100 when no price change ✓
2. Index reflects uniform price increase ✓  
3. Heavier route dominates the index ✓
4. Weights renormalize when a route is missing ✓

## Scrapy Pipeline

The scraping pipeline follows the ethical constraints from SECURITY.md §1:
- Honest User-Agent identification
- robots.txt respect
- Rate limiting with AutoThrottle
- Retry on transient blocks (429, 500-504)
- Playwright JS rendering for dynamic sites
- Item pipeline: schema validation → DB write

## Spider Template Pattern

All spiders follow the same structural template:
- `__init__` accepts origin, destination, advance_days parameters
- `start_requests` generates search URL with Playwright meta
- `parse_search_results` is a template warning users to fill in real selectors
- `_build_item` constructs FareQuoteItem from parsed flight data

Each spider yields data conforming to the shared `FareQuoteModel` schema, enabling source-agnostic pipeline processing.

## Running the Project

### Local Development
```bash
# Start the API server
cd D:\Computer Science\Hackathons\SIH 2026\Faresight
python -m uvicorn api.main:app --reload

# Access docs at http://localhost:8000/docs
# API keys set via API_KEYS environment variable
```

### Render Deployment
The `render.yaml` blueprint provisions:
- API service (FastAPI on Render Starter plan)
- Daily cron job (20:00 UTC) running `run_daily_batch.sh`
- Supabase (Postgres + TimescaleDB)
- Vercel for the Next.js dashboard

### Docker Compose
```bash
docker-compose up
# Brings up: scraper, celery worker, API, dashboard, Postgres, Redis
```

## What Still Needs Production Data

- **Web scraping**: All spiders are templates - need real CSS/XPath selectors or JSON API patterns for each source
- **Database**: PostgreSQL with TimescaleDB (Supabase or local via Docker)
- **Actual fare data**: Requires running the full daily batch pipeline

## References

- `docs/DESIGN.md` - Data model and index methodology
- `docs/SYSTEM_ARCHITECTURE.md` - Full system architecture
- `docs/TECH_STACK.md` - Technology choices and justifications
- `docs/SECURITY.md` - Ethical scraping constraints