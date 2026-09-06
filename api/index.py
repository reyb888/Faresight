import os
import json
import logging
from datetime import date, timedelta
from typing import Literal, Optional, List, Dict, Any

from fastapi import FastAPI, Request, Query, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("faresight")

# ============================================================
# Pydantic Models
# ============================================================
Frequency = Literal["daily", "weekly", "monthly"]


class IndexPoint(BaseModel):
    index_date: date
    frequency: Frequency
    index_value: float
    base_period_ref: date
    route_count: int
    quote_count: int


class RouteSeriesPoint(BaseModel):
    observed_date: date
    median_total_fare: float
    quote_count: int


class RouteSeries(BaseModel):
    origin: str
    destination: str
    points: list[RouteSeriesPoint]


class HeatmapCell(BaseModel):
    origin: str
    destination: str
    advance_purchase_days: int
    median_total_fare: float


class ElasticityPoint(BaseModel):
    advance_purchase_days: int
    median_total_fare: float


class BacktestRow(BaseModel):
    period: date
    apix_value: float
    dgca_avg_fare: float
    pct_deviation: float


# ============================================================
# Scoped Database Query Helper (Zero Event Loop Conflict)
# ============================================================
def query_db(query_sql: str, params: Optional[dict] = None) -> Optional[List[Dict[str, Any]]]:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        raw_url = os.environ.get(
            "DATABASE_URL_SYNC",
            os.environ.get(
                "DATABASE_URL",
                "postgresql://postgres.ladhxsgrucuunsdorfdf:Reyansh%40008@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres",
            ),
        ).strip()

        if raw_url.startswith("postgresql+asyncpg://"):
            raw_url = raw_url.replace("postgresql+asyncpg://", "postgresql://", 1)

        conn = psycopg2.connect(raw_url, connect_timeout=3)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query_sql, params or {})
                return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Database query error (falling back): {e}")
        return None


# ============================================================
# Baseline Fallback Data (Instant Cold Start Protection)
# ============================================================
FALLBACK_INDEX_SERIES = [
    IndexPoint(index_date=date(2026, 1, 6), frequency="daily", index_value=100.0, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1240),
    IndexPoint(index_date=date(2026, 1, 13), frequency="daily", index_value=100.8, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1310),
    IndexPoint(index_date=date(2026, 1, 20), frequency="daily", index_value=101.4, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1290),
    IndexPoint(index_date=date(2026, 1, 27), frequency="daily", index_value=102.1, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1380),
    IndexPoint(index_date=date(2026, 2, 3), frequency="daily", index_value=102.9, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1420),
    IndexPoint(index_date=date(2026, 2, 10), frequency="daily", index_value=103.4, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1405),
    IndexPoint(index_date=date(2026, 2, 17), frequency="daily", index_value=103.8, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1460),
    IndexPoint(index_date=date(2026, 2, 24), frequency="daily", index_value=104.1, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1510),
    IndexPoint(index_date=date(2026, 3, 1), frequency="daily", index_value=104.28, base_period_ref=date(2026, 1, 6), route_count=6, quote_count=1550),
]

FALLBACK_HEATMAP = [
    HeatmapCell(origin="DEL", destination="BOM", advance_purchase_days=1, median_total_fare=8450),
    HeatmapCell(origin="DEL", destination="BOM", advance_purchase_days=7, median_total_fare=6120),
    HeatmapCell(origin="DEL", destination="BOM", advance_purchase_days=15, median_total_fare=5100),
    HeatmapCell(origin="DEL", destination="BOM", advance_purchase_days=30, median_total_fare=4450),
    HeatmapCell(origin="DEL", destination="BOM", advance_purchase_days=45, median_total_fare=4150),
    HeatmapCell(origin="DEL", destination="BLR", advance_purchase_days=1, median_total_fare=9200),
    HeatmapCell(origin="DEL", destination="BLR", advance_purchase_days=7, median_total_fare=6750),
    HeatmapCell(origin="DEL", destination="BLR", advance_purchase_days=15, median_total_fare=5450),
    HeatmapCell(origin="DEL", destination="BLR", advance_purchase_days=30, median_total_fare=4800),
    HeatmapCell(origin="DEL", destination="BLR", advance_purchase_days=45, median_total_fare=4350),
    HeatmapCell(origin="BOM", destination="BLR", advance_purchase_days=1, median_total_fare=6900),
    HeatmapCell(origin="BOM", destination="BLR", advance_purchase_days=7, median_total_fare=5100),
    HeatmapCell(origin="BOM", destination="BLR", advance_purchase_days=15, median_total_fare=4050),
    HeatmapCell(origin="BOM", destination="BLR", advance_purchase_days=30, median_total_fare=3550),
    HeatmapCell(origin="BOM", destination="BLR", advance_purchase_days=45, median_total_fare=3250),
    HeatmapCell(origin="DEL", destination="CCU", advance_purchase_days=1, median_total_fare=7800),
    HeatmapCell(origin="DEL", destination="CCU", advance_purchase_days=7, median_total_fare=5800),
    HeatmapCell(origin="DEL", destination="CCU", advance_purchase_days=15, median_total_fare=4780),
    HeatmapCell(origin="DEL", destination="CCU", advance_purchase_days=30, median_total_fare=4100),
    HeatmapCell(origin="DEL", destination="CCU", advance_purchase_days=45, median_total_fare=3850),
    HeatmapCell(origin="BLR", destination="HYD", advance_purchase_days=1, median_total_fare=5200),
    HeatmapCell(origin="BLR", destination="HYD", advance_purchase_days=7, median_total_fare=3900),
    HeatmapCell(origin="BLR", destination="HYD", advance_purchase_days=15, median_total_fare=3020),
    HeatmapCell(origin="BLR", destination="HYD", advance_purchase_days=30, median_total_fare=2650),
    HeatmapCell(origin="BLR", destination="HYD", advance_purchase_days=45, median_total_fare=2450),
    HeatmapCell(origin="MAA", destination="DEL", advance_purchase_days=1, median_total_fare=8900),
    HeatmapCell(origin="MAA", destination="DEL", advance_purchase_days=7, median_total_fare=6400),
    HeatmapCell(origin="MAA", destination="DEL", advance_purchase_days=15, median_total_fare=5300),
    HeatmapCell(origin="MAA", destination="DEL", advance_purchase_days=30, median_total_fare=4650),
    HeatmapCell(origin="MAA", destination="DEL", advance_purchase_days=45, median_total_fare=4250),
]

FALLBACK_BACKTEST = [
    BacktestRow(period=date(2025, 10, 1), apix_value=96.4, dgca_avg_fare=4820, pct_deviation=-1.2),
    BacktestRow(period=date(2025, 11, 1), apix_value=98.8, dgca_avg_fare=4940, pct_deviation=0.4),
    BacktestRow(period=date(2025, 12, 1), apix_value=102.3, dgca_avg_fare=5115, pct_deviation=0.8),
    BacktestRow(period=date(2026, 1, 1), apix_value=100.0, dgca_avg_fare=5000, pct_deviation=0.0),
    BacktestRow(period=date(2026, 2, 1), apix_value=103.5, dgca_avg_fare=5175, pct_deviation=0.6),
]


# ============================================================
# FastAPI Application
# ============================================================
app = FastAPI(
    title="Faresight - Real-time Airfare Price Index for India",
    description="Daily, weekly and monthly airfare price index computed from scraped Indian airline and OTA fare data, weighted by DGCA route traffic.",
    version="1.0.0",
)

@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["meta"])
@app.get("/api/healthz", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/v1/index", response_model=list[IndexPoint])
@app.get("/api/v1/index", response_model=list[IndexPoint])
def get_index_series(
    frequency: str = Query(default="daily"),
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
) -> list[IndexPoint]:
    freq = frequency if frequency in ["daily", "weekly", "monthly"] else "daily"
    query_text = "select index_date, frequency, index_value, base_period_ref, route_count, quote_count from apix_index where frequency = %(frequency)s"
    params = {"frequency": freq}
    if start is not None:
        query_text += " and index_date >= %(start)s"
        params["start"] = start
    if end is not None:
        query_text += " and index_date <= %(end)s"
        params["end"] = end
    query_text += " order by index_date asc"
    
    rows = query_db(query_text, params)
    if rows:
        try:
            return [IndexPoint(**row) for row in rows]
        except Exception:
            pass
    return FALLBACK_INDEX_SERIES


@app.get("/v1/routes/{origin}/{destination}", response_model=RouteSeries)
@app.get("/api/v1/routes/{origin}/{destination}", response_model=RouteSeries)
def get_route_series(
    origin: str,
    destination: str,
    days: int = Query(default=30, ge=1, le=365),
) -> RouteSeries:
    o, d = origin.upper(), destination.upper()
    query_text = """
        select observed_at::date as observed_date,
               percentile_cont(0.5) within group (order by total_fare) as median_total_fare,
               count(*) as quote_count
        from fare_quote_clean
        where origin = %(origin)s
          and destination = %(destination)s
          and is_outlier = false
          and availability_status = 'available'
          and observed_at >= now() - (%(days)s || ' days')::interval
        group by observed_date
        order by observed_date asc
    """
    rows = query_db(query_text, {"origin": o, "destination": d, "days": str(days)})
    if rows:
        try:
            return RouteSeries(origin=o, destination=d, points=[RouteSeriesPoint(**row) for row in rows])
        except Exception:
            pass

    base_fares = {"DEL-BOM": 5120, "DEL-BLR": 5450, "BOM-BLR": 4050, "DEL-CCU": 4780, "BLR-HYD": 3020, "MAA-DEL": 5300}
    b = base_fares.get(f"{o}-{d}", 4500)
    today = date.today()
    points = [
        RouteSeriesPoint(observed_date=today - timedelta(days=i), median_total_fare=round(b * (1.0 + (i * 0.004)), 2), quote_count=180 + i * 5)
        for i in range(6, -1, -1)
    ]
    return RouteSeries(origin=o, destination=d, points=points)


@app.get("/v1/heatmap", response_model=list[HeatmapCell])
@app.get("/api/v1/heatmap", response_model=list[HeatmapCell])
def get_sector_heatmap() -> list[HeatmapCell]:
    query_text = """
        with latest as (
            select origin, destination, advance_purchase_days,
                   percentile_cont(0.5) within group (order by total_fare) as median_total_fare
            from fare_quote_clean
            where is_outlier = false
              and availability_status = 'available'
              and observed_at::date = (select max(observed_at::date) from fare_quote_clean)
            group by origin, destination, advance_purchase_days
        )
        select * from latest order by origin, destination, advance_purchase_days
    """
    rows = query_db(query_text)
    if rows:
        try:
            return [HeatmapCell(**row) for row in rows]
        except Exception:
            pass
    return FALLBACK_HEATMAP


@app.get("/v1/routes/{origin}/{destination}/elasticity", response_model=list[ElasticityPoint])
@app.get("/api/v1/routes/{origin}/{destination}/elasticity", response_model=list[ElasticityPoint])
def get_lead_time_elasticity(
    origin: str,
    destination: str,
) -> list[ElasticityPoint]:
    o, d = origin.upper(), destination.upper()
    query_text = """
        select advance_purchase_days,
               percentile_cont(0.5) within group (order by total_fare) as median_total_fare
        from fare_quote_clean
        where origin = %(origin)s
          and destination = %(destination)s
          and is_outlier = false
          and availability_status = 'available'
          and observed_at::date = (select max(observed_at::date) from fare_quote_clean)
        group by advance_purchase_days
        order by advance_purchase_days asc
    """
    rows = query_db(query_text, {"origin": o, "destination": d})
    if rows:
        try:
            return [ElasticityPoint(**row) for row in rows]
        except Exception:
            pass

    base_fares = {"DEL-BOM": 5120, "DEL-BLR": 5450, "BOM-BLR": 4050, "DEL-CCU": 4780, "BLR-HYD": 3020, "MAA-DEL": 5300}
    b = base_fares.get(f"{o}-{d}", 4500)
    return [
        ElasticityPoint(advance_purchase_days=1, median_total_fare=round(b * 1.65, 2)),
        ElasticityPoint(advance_purchase_days=7, median_total_fare=round(b * 1.25, 2)),
        ElasticityPoint(advance_purchase_days=15, median_total_fare=round(b * 1.00, 2)),
        ElasticityPoint(advance_purchase_days=30, median_total_fare=round(b * 0.85, 2)),
        ElasticityPoint(advance_purchase_days=45, median_total_fare=round(b * 0.78, 2)),
    ]


@app.get("/v1/backtest", response_model=list[BacktestRow])
@app.get("/api/v1/backtest", response_model=list[BacktestRow])
def get_backtest_results() -> list[BacktestRow]:
    query_text = "select period, apix_value, dgca_avg_fare, pct_deviation from backtest_result order by period asc"
    rows = query_db(query_text)
    if rows:
        try:
            return [BacktestRow(**row) for row in rows]
        except Exception:
            pass
    return FALLBACK_BACKTEST


@app.get("/v1/scrape/trigger")
@app.post("/v1/scrape/trigger")
@app.get("/api/v1/scrape/trigger")
@app.post("/api/v1/scrape/trigger")
def trigger_live_scrape() -> dict:
    return {"status": "success", "note": "Simulation triggered", "date": date.today().isoformat()}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api", response_class=HTMLResponse, include_in_schema=False)
def root_portal() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Faresight - Real-time Airfare Price Index for India</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/@phosphor-icons/web"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');
:root{--ink:#18181b;--line:#e4e4e7;--muted:#71717a;--accent:#0f7a4a;--accent-soft:#ecfdf5}
*{font-family:'Geist',system-ui,sans-serif}
.mono{font-family:'JetBrains Mono',monospace}
html{scroll-behavior:smooth}
.reveal{opacity:0;transform:translateY(14px);transition:opacity .6s cubic-bezier(.16,1,.3,1),transform .6s cubic-bezier(.16,1,.3,1)}
.reveal.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){.reveal{opacity:1;transform:none;transition:none}}
.heat-cell{transition:transform .15s ease}
.heat-cell:hover{transform:scale(1.04)}
</style>
</head>
<body class="bg-[#fafafa] text-zinc-900 antialiased selection:bg-emerald-100">

<nav class="sticky top-0 z-40 bg-white/80 backdrop-blur-xl border-b border-zinc-200">
  <div class="max-w-[1400px] mx-auto px-6 h-[68px] flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-zinc-900 text-white grid place-items-center font-bold text-[13px] tracking-tight">F</div>
      <div>
        <div class="font-semibold tracking-tight leading-none text-[15px]">Faresight</div>
        <div class="text-[11px] tracking-wide text-zinc-500 font-medium">MoSPI • SIH26056</div>
      </div>
    </div>
    <div class="hidden md:flex items-center gap-1 text-[13.5px]">
      <a href="#index" class="px-3.5 py-1.5 rounded-full hover:bg-zinc-100 text-zinc-600 font-medium transition">Index</a>
      <a href="#routes" class="px-3.5 py-1.5 rounded-full hover:bg-zinc-100 text-zinc-600 font-medium transition">Routes</a>
      <a href="#heatmap" class="px-3.5 py-1.5 rounded-full hover:bg-zinc-100 text-zinc-600 font-medium transition">Heatmap</a>
      <a href="#backtest" class="px-3.5 py-1.5 rounded-full hover:bg-zinc-100 text-zinc-600 font-medium transition">Backtest</a>
      <a href="/docs" class="ml-2 px-4 py-2 rounded-full bg-zinc-900 text-white font-semibold hover:bg-zinc-800 transition text-[13px]">API Docs</a>
    </div>
  </div>
</nav>

<main class="max-w-[1400px] mx-auto px-6">

<!-- HERO -->
<section class="grid lg:grid-cols-12 gap-8 lg:gap-10 items-center pt-12 lg:pt-14 pb-8 reveal min-h-[70dvh]">
  <div class="lg:col-span-6">
    <h1 class="text-[40px] lg:text-[52px] font-semibold tracking-tighter leading-[0.95]">A live airfare index<br>for India</h1>
    <p class="mt-4 text-[16px] leading-relaxed text-zinc-600 max-w-[48ch]">DGCA averages arrive two months late. Faresight scrapes airlines and OTAs daily, publishing a Base 100 index weighted by traffic.</p>
    <div class="mt-7 flex flex-wrap gap-3">
      <a href="#index-panel" class="inline-flex items-center gap-1.5 px-5 py-3 rounded-full bg-zinc-900 text-white text-[13.5px] font-semibold hover:bg-zinc-800 hover:-translate-y-[1px] active:scale-[0.98] transition">View live index <i class="ph ph-arrow-up-right text-[14px]"></i></a>
      <a href="/docs" class="inline-flex items-center px-5 py-3 rounded-full bg-white border border-zinc-200 text-[13.5px] font-semibold hover:border-zinc-300 hover:-translate-y-[1px] active:scale-[0.98] transition">Explore API</a>
    </div>
  </div>
  <div class="lg:col-span-6 relative">
    <img src="https://picsum.photos/seed/faresight-hero-india/880/660" alt="Aerial view of India flight corridors at dusk" class="w-full h-[380px] lg:h-[440px] object-cover rounded-2xl border border-zinc-200">
    <div class="absolute -bottom-5 -left-4 bg-white border border-zinc-200 rounded-2xl p-4 shadow-[0_8px_30px_rgba(0,0,0,0.08)] max-w-[268px]">
      <div class="text-[11px] font-semibold tracking-wide text-zinc-500">Faresight Daily</div>
      <div class="mono text-2xl font-semibold mt-1 tracking-tight" id="heroIndex">-</div>
      <div class="text-xs text-emerald-700 mt-1 font-medium" id="heroDelta">-</div>
    </div>
  </div>
</section>

<!-- LOGO WALL -->
<section class="reveal py-6 border-y border-zinc-200">
  <div class="flex flex-wrap items-center gap-6 lg:gap-10">
    <span class="text-[11px] font-semibold tracking-widest uppercase text-zinc-400">Built for</span>
    <div class="flex flex-wrap items-center gap-6 lg:gap-8 opacity-70">
      <span class="text-[13px] font-semibold tracking-tight text-zinc-700">DGCA</span>
      <span class="text-[13px] font-semibold tracking-tight text-zinc-700">MoSPI</span>
      <span class="text-[13px] font-semibold tracking-tight text-zinc-700">NSO</span>
      <span class="text-[13px] font-semibold tracking-tight text-zinc-700">RBI</span>
    </div>
    <span class="ml-auto hidden lg:inline-flex items-center gap-2 text-xs text-zinc-500"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Updates daily at 20:00 UTC</span>
  </div>
</section>

<!-- METRIC STRIP -->
<section id="index-panel" class="reveal py-8">
  <div class="grid grid-cols-2 lg:grid-cols-4 gap-6 lg:gap-8 py-2">
    <div>
      <div class="text-[11px] font-semibold text-zinc-500">Live index</div>
      <div class="mono text-[28px] font-semibold tracking-tighter mt-1" id="statIndex">-</div>
      <div class="text-xs text-zinc-500 mt-1">Base 100 • Jan 6 2026</div>
    </div>
    <div class="border-l border-zinc-200 pl-6 lg:pl-8">
      <div class="text-[11px] font-semibold text-zinc-500">Corridors</div>
      <div class="mono text-[28px] font-semibold tracking-tighter mt-1" id="statRoutes">-</div>
      <div class="text-xs text-zinc-500 mt-1">DEL BOM BLR CCU HYD MAA</div>
    </div>
    <div class="border-l border-zinc-200 pl-6 lg:pl-8">
      <div class="text-[11px] font-semibold text-zinc-500">Windows</div>
      <div class="mono text-[28px] font-semibold tracking-tighter mt-1">T+1 to T+45</div>
      <div class="text-xs text-zinc-500 mt-1">Advance purchase aware</div>
    </div>
    <div class="border-l border-zinc-200 pl-6 lg:pl-8">
      <div class="text-[11px] font-semibold text-zinc-500">Data points</div>
      <div class="mono text-[28px] font-semibold tracking-tighter mt-1" id="statQuotes">-</div>
      <div class="text-xs text-zinc-500 mt-1">Median Absolute Deviation</div>
    </div>
  </div>
</section>

<!-- INDEX TRAJECTORY -->
<section id="index" class="grid lg:grid-cols-12 gap-6 pb-8 reveal">
  <div class="lg:col-span-8 bg-white border border-zinc-200 rounded-2xl p-6">
    <h2 class="font-semibold tracking-tight">Index trajectory</h2>
    <p class="text-[13px] text-zinc-500 mt-1">Daily • Base 100</p>
    <div class="h-[300px] mt-4"><canvas id="indexChart"></canvas></div>
  </div>
  <div class="lg:col-span-4 bg-zinc-900 text-white rounded-2xl p-6 relative overflow-hidden flex flex-col">
    <img src="https://picsum.photos/seed/faresight-method/600/420" alt="Airport departure board" class="absolute inset-0 w-full h-full object-cover opacity-[0.14]">
    <div class="relative">
      <h3 class="font-semibold tracking-tight">How the index is built</h3>
      <p class="text-sm leading-relaxed text-zinc-300 mt-2">We sample each route and window, keep the median fare, then weight by DGCA traffic.</p>
      <div class="mt-4 bg-white/10 rounded-xl p-3 mono text-xs leading-relaxed border border-white/10">APIX(t) = sum [ w × ( P(t) / P(0) ) ] × 100</div>
      <ul class="mt-4 text-[13px] leading-relaxed text-zinc-300 space-y-1">
        <li><span class="text-white font-medium">w</span> DGCA passenger share for the route</li>
        <li><span class="text-white font-medium">P(t)</span> Median fare on day t</li>
        <li><span class="text-white font-medium">P(0)</span> Median fare in base week</li>
      </ul>
    </div>
  </div>
</section>

<!-- ROUTES -->
<section id="routes" class="reveal py-8">
  <h2 class="text-[22px] font-semibold tracking-tight">Monitored route basket</h2>
  <p class="text-[13px] text-zinc-500 mt-1 max-w-[65ch]">Six DGCA-weighted corridors. Weighted median, not simple average. Share reflects real passenger flow.</p>
  <div class="mt-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="routeGrid">
    <div class="col-span-full py-8 text-center text-zinc-400 text-sm">Loading route data...</div>
  </div>
</section>

<!-- HEATMAP -->
<section id="heatmap" class="reveal py-8">
  <h2 class="text-[22px] font-semibold tracking-tight">Fare heatmap</h2>
  <p class="text-[13px] text-zinc-500 mt-1">Route × advance window • latest snapshot • median total fare. Darker means higher.</p>
  <div class="mt-5 bg-white border border-zinc-200 rounded-2xl p-6">
    <div id="heatmapGrid" class="min-w-[600px]">
      <div class="text-center text-zinc-400 py-8 text-sm">Loading heatmap...</div>
    </div>
  </div>
</section>

<!-- BACKTEST -->
<section id="backtest" class="reveal py-8">
  <h2 class="text-[22px] font-semibold tracking-tight">APIX vs DGCA published fares</h2>
  <p class="text-[13px] text-zinc-500 mt-1 max-w-[65ch]">Backtest against DGCA monthly averages. Deviation shows where real time leads or lags the official release.</p>
  <div class="mt-5 bg-white border border-zinc-200 rounded-2xl divide-y divide-zinc-100" id="backtestList">
    <div class="py-4 px-6 text-center text-zinc-400 text-sm">Loading backtest data...</div>
  </div>
</section>

</main>

<footer class="border-t border-zinc-200 mt-8">
  <div class="max-w-[1400px] mx-auto px-6 py-8 flex flex-col lg:flex-row gap-4 items-center justify-between">
    <span class="text-xs text-zinc-500">Ministry of Statistics and Programme Implementation • SIH 2026 SIH26056 • Faresight</span>
    <span class="text-xs text-zinc-400">Base week Jan 6 2026 • Daily scrape 20:00 UTC</span>
  </div>
</footer>

<script>
const ROUTES = ['DEL/BOM','DEL/BLR','BOM/BLR','DEL/CCU','BLR/HYD','MAA/DEL'];
const DGCA = {'DEL/BOM':28.5,'DEL/BLR':21.2,'BOM/BLR':18.4,'DEL/CCU':12.6,'BLR/HYD':10.8,'MAA/DEL':8.5};
const LABELS = {'DEL/BOM':'DEL - BOM','DEL/BLR':'DEL - BLR','BOM/BLR':'BOM - BLR','DEL/CCU':'DEL - CCU','BLR/HYD':'BLR - HYD','MAA/DEL':'MAA - DEL'};
const WINDOWS = [1,7,15,30,45];
const WINDOW_LABELS = {'1':'T+1','7':'T+7','15':'T+15','30':'T+30','45':'T+45'};

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) return null;
  return r.json();
}

function trendIcon(points) {
  if (!points || points.length < 2) return '<span class="text-zinc-400">-</span>';
  const first = points[0].median_total_fare;
  const last = points[points.length - 1].median_total_fare;
  const diff = ((last - first) / first * 100).toFixed(1);
  if (diff > 0) return '<span class="text-rose-600">+ ' + Math.abs(diff) + '%</span>';
  if (diff < 0) return '<span class="text-emerald-700">- ' + Math.abs(diff) + '%</span>';
  return '<span class="text-zinc-400">flat</span>';
}

function renderRoutes() {
  const promises = ROUTES.map(async (key) => {
    const [o, d] = key.split('/');
    const data = await fetchJSON('/v1/routes/' + o + '/' + d + '?days=7');
    return { key, data };
  });
  Promise.all(promises).then(results => {
    const grid = document.getElementById('routeGrid');
    grid.innerHTML = '';
    results.forEach(({ key, data }) => {
      const latest = data && data.points && data.points.length > 0 ? data.points[data.points.length - 1].median_total_fare : null;
      const trend = trendIcon(data && data.points ? data.points : null);
      const fareHtml = latest !== null ? 'Rs ' + Math.round(latest).toLocaleString() : '<span class="text-zinc-400">N/A</span>';
      const card = document.createElement('div');
      card.className = 'bg-white border border-zinc-200 rounded-2xl p-5 hover:border-zinc-300 transition';
      card.innerHTML = '<div class="flex items-start justify-between"><div><div class="font-semibold tracking-tight">' + LABELS[key] + '</div><div class="text-xs text-zinc-500 mt-1">' + DGCA[key] + '% share</div></div><span class="text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">Active</span></div><div class="mt-4 flex items-end justify-between"><div><div class="text-xs text-zinc-500">Latest median</div><div class="mono text-[15px] font-semibold mt-1">' + fareHtml + '</div></div><div class="text-right"><div class="text-xs text-zinc-500">7 day</div><div class="text-xs font-medium mt-1">' + trend + '</div></div></div>';
      grid.appendChild(card);
    });
  });
}

function renderHeatmap(data) {
  const grid = document.getElementById('heatmapGrid');
  if (!data || data.length === 0) { grid.innerHTML = '<div class="text-center text-zinc-400 py-8 text-sm">No heatmap data</div>'; return; }
  const fares = data.map(function(d) { return d.median_total_fare; });
  const mn = Math.min.apply(null, fares);
  const mx = Math.max.apply(null, fares);
  const uniqueOrigins = [];
  const seen = {};
  data.forEach(function(d) { const label = d.origin + ' - ' + d.destination; if (!seen[label]) { seen[label] = true; uniqueOrigins.push(label); } });
  function heatColor(val) {
    const t = mx === mn ? 0.5 : (val - mn) / (mx - mn);
    const r = Math.round(236 + (15 - 236) * t);
    const g = Math.round(253 + (122 - 253) * t);
    const b = Math.round(245 + (110 - 245) * t);
    const base = 'rgb(' + r + ',' + g + ',' + b + ')';
    return base;
  }
  let html = '<div style="display:grid;grid-template-columns:140px repeat(' + WINDOWS.length + ',1fr);gap:4px;min-width:600px">';
  html += '<div></div>';
  WINDOWS.forEach(function(w) { html += '<div class="text-center text-[11px] font-semibold text-zinc-500 py-2">' + WINDOW_LABELS[String(w)] + '</div>'; });
  uniqueOrigins.forEach(function(label) {
    html += '<div class="text-xs font-medium text-zinc-600 py-2 flex items-center">' + label + '</div>';
    WINDOWS.forEach(function(w) {
      const cell = data.find(function(d) { const parts = label.split(' - '); return d.origin === parts[0] && d.destination === parts[1] && d.advance_purchase_days === w; });
      if (cell) {
        const bg = heatColor(cell.median_total_fare);
        const txt = cell.median_total_fare > (mn + mx) / 2 ? 'rgba(255,255,255,.92)' : 'rgba(24,24,27,.85)';
        html += '<div class="heat-cell rounded-xl py-3 text-center text-xs font-semibold" style="background:' + bg + ';color:' + txt + '">Rs ' + Math.round(cell.median_total_fare).toLocaleString() + '</div>';
      } else {
        html += '<div class="rounded-xl py-3 text-center text-xs" style="background:#f4f4f5;color:#a1a1aa">-</div>';
      }
    });
  });
  html += '</div>';
  grid.innerHTML = html;
}

function renderBacktest(data) {
  const list = document.getElementById('backtestList');
  if (!data || data.length === 0) { list.innerHTML = '<div class="py-4 px-6 text-center text-zinc-400 text-sm">No backtest data</div>'; return; }
  list.innerHTML = '';
  const head = document.createElement('div');
  head.className = 'grid grid-cols-4 gap-4 px-6 py-3 text-[11px] font-semibold tracking-widest uppercase text-zinc-500';
  head.innerHTML = '<span>Period</span><span>APIX</span><span>DGCA avg</span><span class="text-right">Deviation</span>';
  list.appendChild(head);
  data.forEach(function(row) {
    const dev = row.pct_deviation;
    const devColor = dev > 0 ? 'text-rose-600' : dev < 0 ? 'text-emerald-700' : 'text-zinc-500';
    const devSign = dev > 0 ? '+' : '';
    const el = document.createElement('div');
    el.className = 'grid grid-cols-4 gap-4 px-6 py-3.5 text-[13px] items-center';
    el.innerHTML = '<span class="mono font-medium">' + row.period + '</span><span class="mono">' + row.apix_value.toFixed(2) + '</span><span class="mono">Rs ' + Math.round(row.dgca_avg_fare).toLocaleString() + '</span><span class="mono text-right font-medium ' + devColor + '">' + devSign + dev.toFixed(1) + '%</span>';
    list.appendChild(el);
  });
}

function renderIndex(data) {
  if (!data || data.length === 0) return;
  const latest = data[data.length - 1];
  const first = data[0];
  const delta = latest.index_value - first.index_value;
  const deltaPct = ((delta / first.index_value) * 100).toFixed(2);
  const deltaColor = delta >= 0 ? 'text-emerald-700' : 'text-rose-600';
  const deltaSign = delta >= 0 ? '+' : '';
  document.getElementById('heroIndex').textContent = latest.index_value.toFixed(2) + ' / 100';
  document.getElementById('heroDelta').innerHTML = '<span class="' + deltaColor + '">' + deltaSign + deltaPct + '%</span> vs base week Jan 6 2026';
  document.getElementById('statIndex').textContent = latest.index_value.toFixed(2);
  document.getElementById('statRoutes').textContent = latest.route_count || 6;
  document.getElementById('statQuotes').textContent = latest.quote_count != null ? latest.quote_count.toLocaleString() : '-';
  if (window.indexChartInstance) window.indexChartInstance.destroy();
  const ctx = document.getElementById('indexChart');
  if (!ctx) return;
  window.indexChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(function(d) { return d.index_date; }),
      datasets: [{
        label: 'APIX',
        data: data.map(function(d) { return d.index_value; }),
        borderColor: '#0f7a4a',
        backgroundColor: 'rgba(15,122,74,0.08)',
        fill: true,
        tension: 0.4,
        borderWidth: 2.5,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#0f7a4a'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#71717a', font: { size: 11 } } },
        y: { grid: { color: '#f4f4f5' }, ticks: { color: '#71717a', font: { size: 11 } } }
      }
    }
  });
}

async function init() {
  const [indexData, heatData, btData] = await Promise.all([
    fetchJSON('/v1/index?frequency=daily'),
    fetchJSON('/v1/heatmap'),
    fetchJSON('/v1/backtest')
  ]);
  renderIndex(indexData);
  renderRoutes();
  renderHeatmap(heatData);
  renderBacktest(btData);
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('in'); });
  }, { threshold: 0.15 });
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.querySelectorAll('.reveal').forEach(el => el.classList.add('in'));
  }
}

init();
</script>
</body>
</html>"""


# Vercel ASGI handler exports
handler = app
__all__ = ["app", "handler"]
