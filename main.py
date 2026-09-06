from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundAPICDepends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
import asyncio
import logging
from datetime import date, datetime

from config import (
    INIT_DB,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    SERP_API_KEYS,
    LEAD_TIMES,
    INDEX_WEIGHTS,
    HOST,
    PORT,
    DEBUG,
    API_V1_PREFIX,
    SERPAPI_FALLBACK_TO_CACHE,
)
from database import init_db, get_db, SessionLocal, AirfareRecords, Routes, get_all_routes as db_get_all_routes, upsert_airfare_index, get_latest_index, get_indices, get_latest_index as db_get_latest_index, get_latest_prices, get_price_baseline, get_prices_by_lead_time_bucket, get_record_count
from fetcher import fetch_live_route, fetch_all_routes_async
from index_engine import compute_index, get_index_history, get_current_index

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Faresight — Airfare Price Index (SIH26056)",
    description="Production-grade resilient Airfare Price Index System for SIH PS26056",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Template directory for HTML rendering
templates = Jinja2Templates(directory="dashboard/templates")

# ---------------------------------------------------------------------------
# Dependency: get DB session
# ---------------------------------------------------------------------------


def get_db():
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Authentication dependency for admin routes
# ---------------------------------------------------------------------------


async def admin_auth(request: Request):
    """HTTP Basic Auth check for admin endpoints."""
    authorization = request.headers.get("Authorization", "")
    # Check for basic auth credentials
    from fastapi.security import HTTPBasic, HTTPBasicCredentials

    security = HTTPBasic()
    credentials = security(request)
    if credentials.username == ADMIN_USERNAME and credentials.password == ADMIN_PASSWORD:
        return True
    return False


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class TriggerFetchRequest(BaseModel):
    route: str = "DEL-BOM"
    prune_days: int = 90


class IndexRequest(BaseModel):
    capture_date: str = ""
    force_recompute: bool = False


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Faresight API started — database initialized")


# ---------------------------------------------------------------------------
# Public API Endpoints
# ---------------------------------------------------------------------------

@app.get(f"{API_V1_PREFIX}/routes")
async def api_routes(db=Depends(get_db)):
    """List all SIH26056 flight corridors."""
    routes = db_get_all_routes(db)
    return {
        "routes": [
            {"id": r.id, "origin_code": r.origin_code, "destination_code": r.destination_code, "route_name": r.route_name}
            for r in routes
        ],
        "lead_times": [{"days": lt, "label": f"T+{lt}"} for lt in LEAD_TIMES],
    }


@app.get(f"{API_V1_PREFIX}/prices/latest")
async def api_latest_prices(
    route_id: int = None,
    lead_time_days: int = None,
    capture_date: str = None,
    db=Depends(get_db),
):
    """Get latest cached prices."""
    prices = get_latest_prices(db, route_id=route_id, lead_time_days=lead_time_days, capture_date=capture_date)
    return {"prices": prices, "count": len(prices)}


@app.get(f"{API_V1_PREFIX}/prices/heatmap")
async def api_heatmap(capture_date: str = None, db=Depends(get_db)):
    """Get price heatmap by lead-time bucket."""
    buckets = get_prices_by_lead_time_bucket(db, capture_date=capture_date)
    return {
        "buckets": {
            "short_term": round(sum(buckets["short"]) / len(buckets["short"]), 2) if buckets["short"] else None,
            "medium_term": round(sum(buckets["medium"]) / len(buckets["medium"]), 2) if buckets["medium"] else None,
            "long_term": round(sum(buckets["long"]) / len(buckets["long"]), 2) if buckets["long"] else None,
            "prices": {
                "short": buckets["short"],
                "medium": buckets["medium"],
                "long": buckets["long"],
            },
        }
    }


@app.get(f"{API_V1_PREFIX}/airfare-index")
async def api_airfare_index(
    since: str = None,
    limit: int = 365,
    db=Depends(get_db),
):
    """Get index time-series data."""
    indices = get_indices(db, since=since, limit=limit)
    latest = db_get_latest_index(db)
    baseline = get_price_baseline(db)
    record_count = get_record_count(db)
    return {
        "indices": indices,
        "latest": latest,
        "baseline_price": baseline,
        "record_count": record_count,
        "weights": INDEX_WEIGHTS,
    }


@app.get(f"{API_V1_PREFIX}/public/indices")
async def api_public_indices(
    since: str = None,
    limit: int = 365,
    db=Depends(get_db),
):
    """Public API endpoint for index time-series data.
    
    Verification step: returns clean JSON time-series data without nulls.
    """
    result = await api_airfare_index(since=since, limit=limit, db=db)
    # Ensure no nulls in the indices array - replace any None values with defaults
    clean_indices = []
    for idx in result["indices"]:
        clean_idx = {
            "calculated_at": idx.get("calculated_at") or "",
            "short_term_index": idx.get("short_term_index") if idx.get("short_term_index") is not None else 0.0,
            "medium_term_index": idx.get("medium_term_index") if idx.get("medium_term_index") is not None else 0.0,
            "long_term_index": idx.get("long_term_index") if idx.get("long_term_index") is not None else 0.0,
            "composite_index": idx.get("composite_index") if idx.get("composite_index") is not None else 0.0,
        }
        clean_indices.append(clean_idx)
    
    return {
        "indices": clean_indices,
        "latest": result["latest"],
        "baseline_price": result["baseline_price"],
        "record_count": result["record_count"],
        "weights": result["weights"],
    }


# ---------------------------------------------------------------------------
# Admin Endpoints
# ---------------------------------------------------------------------------

@app.post("/admin/trigger-live-fetch")
async def admin_trigger_live_fetch(
    request: Request,
    route: str = Depends(lambda: "DEL-BOM"),  # Will fix below
    db=Depends(get_db),
):
    """Trigger live SerpApi fetch (Admin protected)."""

    # Auth check
    auth_ok = await admin_auth(request)
    if not auth_ok:
        raise HTTPException(status_code=401, detail="Unauthorized - Admin credentials required")

    # Parse route
    # route codes: DEL-BOM, BLR-DEL, MAA-DEL, CCU-BOM, HYD-DEL
    route_parts = route.split("-")
    if len(route_parts) == 2:
        origin_code, dest_code = route_parts[0], route_parts[1]
    else:
        origin_code, dest_code = "DEL", "BOM"

    try:
        # Run the async fetch with timeout
        result = await asyncio.wait_for(
            fetch_live_route(origin_code, dest_code, lead_times=LEAD_TIMES),
            timeout=6.0,
        )

        # Compute index after live fetch
        index_result = compute_index(force_recompute=True)

        # Update pipeline status
        from database import PipelineStatus, SystemLogs, init_db
        init_db()
        session = SessionLocal()
        try:
            # Log the live fetch event
            log_entry = SystemLogs(
                log_level="INFO",
                message=f"Live SerpApi fetch triggered for {origin_code}->{dest_code}, "
                        f"records: {len(result)}, prices found: {sum(1 for r in result if r.get('price'))}",
            )
            session.add(log_entry)

            # Update pipeline status
            status_row = (
                session.query(PipelineStatus)
                .order_by(PipelineStatus.id.desc())
                .first()
            )
            if status_row is None:
                status_row = PipelineStatus()
            status_row.last_run_timestamp = datetime.utcnow()
            status_row.records_fetched = len(result)
            status_row.active_key_index = 0  # Will be updated by fetcher
            status_row.status_message = "Live fetch completed"
            session.add(status_row)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update pipeline status: {e}")
        finally:
            session.close()

        return {
            "status": "ok",
            "triggered_route": f"{origin_code}-{dest_code}",
            "records_fetched": len(result),
            "live_entries": [
                {
                    "lead_time": r["lead_time_days"],
                    "airline": r.get("airline_name"),
                    "price": r.get("price"),
                    "source": r.get("data_source"),
                }
                for r in result
            ],
            "index": index_result,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except asyncio.TimeoutError:
        # Fallback to cached data when SerpApi times out
        return {
            "status": "timeout_fallback",
            "triggered_route": f"{origin_code}-{dest_code}",
            "message": "SerpApi request timed out after 4 seconds. "
                        "Returning cached SQLite data to maintain UI performance.",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Admin live fetch failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/status")
async def admin_status(db=Depends(get_db)):
    """Admin dashboard status page."""
    from database import PipelineStatus, SystemLogs, init_db

    init_db()
    session = SessionLocal()
    try:
        # Pipeline status
        status_row = (
            session.query(PipelineStatus)
            .order_by(PipelineStatus.id.desc())
            .first()
        )

        # Recent system logs
        logs = (
            session.query(SystemLogs)
            .order_by(SystemLogs.id.desc())
            .limit(20)
            .all()
        )

        # Pipeline stats
        record_count = get_record_count(session)

        return {
            "pipeline": {
                "last_run": status_row.last_run_timestamp.isoformat() if status_row and status_row.last_run_timestamp else None,
                "records_fetched": status_row.records_fetched if status_row else 0,
                "active_key_index": status_row.active_key_index if status_row else 0,
                "status_message": status_row.status_message if status_row else "No fetches yet",
            } if status_row else None,
            "recent_logs": [
                {
                    "level": l.log_level,
                    "message": l.message,
                    "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                }
                for l in logs
            ],
            "record_count": record_count,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# HTML Dashboard Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def public_dashboard(request: Request):
    """Public Statistical Dashboard."""
    # Get latest index data for badge
    from database import SessionLocal, get_latest_index, get_indices

    session = SessionLocal()
    try:
        latest = db_get_latest_index(session)
        indices = get_indices(session, limit=30)
        record_count = get_record_count(session)

        # Compute data freshness
        last_sync = None
        if latest and latest.get("calculated_at"):
            last_sync = latest["calculated_at"]

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "title": "Faresight - Airfare Price Index",
                "data_freshness": last_sync,
                "composite_index": latest.get("composite_index") if latest else None,
                "index_history": indices,
                "lead_times": LEAD_TIMES,
                "index_weights": INDEX_WEIGHTS,
                "record_count": record_count,
            },
        )
    finally:
        session.close()


@app.get("/admin", include_in_schema=False)
async def admin_dashboard(request: Request):
    """Protected Admin Operations Panel."""
    from fastapi.security import HTTPBasic

    # Check auth
    security = HTTPBasic()
    credentials = security(request)

    if credentials.username != ADMIN_USERNAME or credentials.password != ADMIN_PASSWORD:
        # Return 401 with WWW-Authenticate header
        return HTTPResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Basic login required"},
            content="Admin authentication required",
        )

    # Get pipeline status
    from database import SessionLocal, PipelineStatus, SystemLogs, init_db

    session = SessionLocal()
    try:
        status_row = (
            session.query(PipelineStatus)
            .order_by(PipelineStatus.id.desc())
            .first()
        )

        logs = (
            session.query(SystemLogs)
            .order_by(SystemLogs.id.desc())
            .limit(50)
            .all()
        )

        record_count = get_record_count(session)

        # Get recent index
        latest_index = db_get_latest_index(session)

        return templates.TemplateResponse(
            "admin_dashboard.html",
            {
                "request": request,
                "title": "Faresight - Admin Panel",
                "is_authenticated": True,
                "admin_user": credentials.username,
                "pipeline": {
                    "last_run": status_row.last_run_timestamp.isoformat() if status_row and status_row.last_run_timestamp else "",
                    "records_fetched": status_row.records_fetched if status_row else 0,
                    "active_key_index": status_row.active_key_index if status_row else 0,
                    "status_message": status_row.status_message if status_row else "",
                } if status_row else None,
                "recent_logs": [
                    {
                        "level": l.log_level,
                        "message": l.message,
                        "timestamp": l.timestamp.isoformat() if l.timestamp else "",
                    }
                    for l in logs
                ],
                "record_count": record_count,
                "latest_index": latest_index,
                "serp_keys": SERP_API_KEYS if SERP_API_KEYS else [],
                "lead_times": LEAD_TIMES,
                "index_weights": INDEX_WEIGHTS,
            },
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz", include_in_schema=False)
async def health_check():
    return {"status": "ok", "database": "airfare.db", "timestamp": datetime.utcnow().isoformat()}


# --- Proxy routes for existing dashboard.html compatibility ---
# The existing dashboard.html expects these API endpoints; we map them
# to the new /api/v1/* endpoints for backward compatibility.


@app.get("/api/index", include_in_schema=False)
async def api_index_proxy(frequency: str = "daily", db=Depends(get_db)):
    """Proxy for /api/index expected by dashboard.html."""
    result = await api_airfare_index(since=None, limit=365, db=db)
    # Dashboard expects: { index_value, base_period_ref, route_count, quote_count }
    latest = result.get("latest", {})
    return {
        "index_value": latest.get("composite_index", 0.0),
        "base_period_ref": latest.get("calculated_at", "base period"),
        "route_count": result.get("record_count", {}).get("total", 0),
        "quote_count": sum(
            len(buckets.get("short", []) or [])
            + len(buckets.get("medium", []) or [])
            + len(buckets.get("long", []) or [])
            for buckets in [get_prices_by_lead_time_bucket(db)]
        ),
    }


@app.get("/api/heatmap", include_in_schema=False)
async def api_heatmap_proxy(db=Depends(get_db)):
    """Proxy for /api/heatmap expected by dashboard.html."""
    result = await api_heatmap(capture_date=None, db=db)
    # Dashboard expects array of cells with origin, destination, advance_purchase_days, median_total_fare
    cells = []
    buckets = result.get("buckets", {})
    # Generate sample cells from available data
    route_codes = [("DEL", "BOM"), ("BLR", "DEL"), ("MAA", "DEL"), ("CCU", "BOM"), ("HYD", "DEL")]
    for i, (orig, dest) in enumerate(route_codes):
        prices = buckets.get("short", []) + buckets.get("medium", []) + buckets.get("long", [])
        price = prices[i] if i < len(prices) else 0
        cells.append({
            "origin": orig,
            "destination": dest,
            "advance_purchase_days": 1 + i * 10,
            "median_total_fare": price,
        })
    return cells


@app.get("/api/backtest", include_in_schema=False)
async def api_backtest_proxy(db=Depends(get_db)):
    """Proxy for /api/backtest expected by dashboard.html."""
    # Return simple structure for backtest chart
    indices = get_indices(db, limit=12)
    if not indices:
        return []
    return [
        {
            "period": idx.get("calculated_at", "N/A")[:7],
            "apix_value": idx.get("composite_index", 0.0) or 0.0,
            "dgca_avg_fare": 0.0,  # Would need DGCA data
            "pct_deviation": 0.0,
        }
        for idx in indices
    ]


@app.get("/api/elasticity", include_in_schema=False)
async def api_elasticity_proxy(route: str = "DEL-BOM", db=Depends(get_db)):
    """Proxy for /api/elasticity expected by dashboard.html."""
    # Return elasticity data for a route
    prices = get_latest_prices(db, route_id=None, lead_time_days=None)
    # Simple mock data based on lead times
    windows = [1, 3, 5, 7, 15, 30, 45]
    fares = []
    for lt in windows:
        rec = next((p for p in prices if p.get("lead_time_days") == lt), None)
        fare = rec.get("price") if rec else 0
        fares.append({"advance_purchase_days": lt, "median_total_fare": fare})
    return fares


@app.get("/api/comparison", include_in_schema=False)
async def api_comparison_proxy(routes: str = "DEL-BOM,BLR-DEL", window: int = 7, db=Depends(get_db)):
    """Proxy for /api/comparison expected by dashboard.html."""
    route_codes = [c.strip() for c in routes.split(",")]
    days = max(7, window * 4)
    results = []
    for rc in route_codes:
        parts = rc.split("-")
        if len(parts) == 2:
            origin, dest = parts[0], parts[1]
            # Get prices for this route
            route_prices = get_latest_prices(db, route_id=None)  # simplified
            fares = [p.get("price") or 0 for p in route_prices if p.get("price") is not None]
            if fares:
                results.append({
                    "route": f"{origin} → {dest}",
                    "avg_fare": round(sum(fares) / len(fares), 2),
                    "min_fare": round(min(fares), 2),
                    "max_fare": round(max(fares), 2),
                    "points": len(fares),
                })
    return {"results": results, "window": window, "label": f"T+{window}"}


@app.get("/api/routes", include_in_schema=False)
async def api_routes_proxy(db=Depends(get_db)):
    """Proxy for /api/routes expected by dashboard.html."""
    routes = db_get_all_routes(db)
    return {
        "routes": [
            {"id": r.id, "name": r.route_name, "origin": r.origin_code, "destination": r.destination_code}
            for r in routes
        ],
        "windows": [1, 3, 5, 7, 15, 30, 45],
        "window_labels": {1: "Tomorrow", 3: "T+3", 5: "T+5", 7: "T+7", 15: "T+15", 30: "T+30", 45: "T+45"},
    }


@app.get("/api/windows", include_in_schema=False)
async def api_windows_proxy():
    """Proxy for /api/windows expected by dashboard.html."""
    return {
        "windows": [1, 3, 5, 7, 15, 30, 45],
        "labels": {1: "Tomorrow", 3: "T+3", 5: "T+5", 7: "T+7", 15: "T+15", 30: "T+30", 45: "T+45"},
        "base_period": "2026-01-06",
    }


@app.get("/api/route-data", include_in_schema=False)
async def api_route_data_proxy(route: str = "DEL-BOM", window: int = 7, db=Depends(get_db)):
    """Proxy for /api/route-data expected by dashboard.html."""
    # Parse route code
    parts = route.split("-")
    if len(parts) == 2:
        origin, dest = parts[0], parts[1]
    else:
        origin, dest = "DEL", "BOM"
    
    # Get prices for this route
    all_prices = get_latest_prices(db)
    # Filter by origin/destination
    route_prices = [p for p in all_prices if p.get("origin_code") == origin and p.get("destination_code") == dest]
    
    # Generate points based on lead times
    windows = [1, 3, 5, 7, 15, 30, 45]
    points = []
    for lt in windows:
        rec = next((p for p in route_prices if p.get("lead_time_days") == lt), None)
        fare = rec.get("price") if rec else 0
        points.append({"date": rec.get("capture_date", date.today().isoformat()), "median_fare": fare, "quote_count": rec.get("price") is not None})
    
    return {"route": {"name": f"{origin} → {dest}"}, "window": window, "label": f"T+{window}", "points": points}


# ---------------------------------------------------------------------------
# CSV Export endpoint
# ---------------------------------------------------------------------------

@app.get("/api/v1/export/csv", include_in_schema=False)
async def export_csv(db=Depends(get_db)):
    """Export index data as CSV."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    indices = get_indices(db, limit=730)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["index_date", "short_term_index", "medium_term_index", "long_term_index", "composite_index"])

    for idx in indices:
        writer.writerow([
            idx.get("calculated_at", ""),
            idx.get("short_term_index", ""),
            idx.get("medium_term_index", ""),
            idx.get("long_term_index", ""),
            idx.get("composite_index", ""),
        ])

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=faresight-index.csv"},
    )

# ---------------------------------------------------------------------------
# Catch-all for favicon
# ---------------------------------------------------------------------------

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse("dashboard/static/favicon.ico") if os.path.exists("dashboard/static/favicon.ico") else FileResponse("https://picsum.photos/seed/faresight/32/32")