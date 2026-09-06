import sys
from pathlib import Path
import logging

logger = logging.getLogger("faresight.router")

root_dir = Path(__file__).resolve().parent.parent.parent
api_dir = Path(__file__).resolve().parent.parent
for p in (str(root_dir), str(api_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from api.auth import require_api_key, get_api_key
    from api.db import get_session
    from api.models import (
        BacktestRow,
        ElasticityPoint,
        Frequency,
        HeatmapCell,
        IndexPoint,
        RouteSeries,
        RouteSeriesPoint,
    )
except ImportError:
    from auth import require_api_key, get_api_key
    from db import get_session
    from models import (
        BacktestRow,
        ElasticityPoint,
        Frequency,
        HeatmapCell,
        IndexPoint,
        RouteSeries,
        RouteSeriesPoint,
    )

router = APIRouter(prefix="/v1", tags=["index"])

# Baseline sample data if DB is cold or connecting
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


@router.get("/index", response_model=list[IndexPoint])
async def get_index_series(
    frequency: str = Query(default="daily"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[IndexPoint]:
    """Returns the APIx time series at the requested frequency."""
    freq = frequency if frequency in ["daily", "weekly", "monthly"] else "daily"
    if session is not None:
        try:
            query_text = """
                select index_date, frequency, index_value, base_period_ref,
                       route_count, quote_count
                from apix_index
                where frequency = :frequency
            """
            params = {"frequency": freq}
            if start is not None:
                query_text += " and index_date >= :start"
                params["start"] = start
            if end is not None:
                query_text += " and index_date <= :end"
                params["end"] = end
            query_text += " order by index_date asc"
            query = text(query_text)
            rows = (await session.execute(query, params)).mappings().all()
            if rows:
                return [IndexPoint(**row) for row in rows]
        except Exception as e:
            logger.warning(f"Index query fallback: {e}")
            
    return FALLBACK_INDEX_SERIES


@router.get("/routes/{origin}/{destination}", response_model=RouteSeries)
async def get_route_series(
    origin: str,
    destination: str,
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> RouteSeries:
    """Per-route median fare history, for the Route Explorer dashboard view."""
    o, d = origin.upper(), destination.upper()
    if session is not None:
        try:
            query = text(
                """
                select observed_at::date as observed_date,
                       percentile_cont(0.5) within group (order by total_fare) as median_total_fare,
                       count(*) as quote_count
                from fare_quote_clean
                where origin = :origin
                  and destination = :destination
                  and is_outlier = false
                  and availability_status = 'available'
                  and observed_at >= now() - (:days || ' days')::interval
                group by observed_date
                order by observed_date asc
                """
            )
            rows = (
                await session.execute(
                    query,
                    {"origin": o, "destination": d, "days": days},
                )
            ).mappings().all()
            if rows:
                return RouteSeries(
                    origin=o,
                    destination=d,
                    points=[RouteSeriesPoint(**row) for row in rows],
                )
        except Exception as e:
            logger.warning(f"Route series query fallback: {e}")

    # Fallback points for the last 7 days
    base_fares = {"DEL-BOM": 5120, "DEL-BLR": 5450, "BOM-BLR": 4050, "DEL-CCU": 4780, "BLR-HYD": 3020, "MAA-DEL": 5300}
    pair_key = f"{o}-{d}"
    base_fare = base_fares.get(pair_key, 4500)
    today = date.today()
    points = [
        RouteSeriesPoint(observed_date=today - timedelta(days=i), median_total_fare=round(base_fare * (1.0 + (i * 0.004)), 2), quote_count=180 + i * 5)
        for i in range(6, -1, -1)
    ]
    return RouteSeries(origin=o, destination=d, points=points)


@router.get("/heatmap", response_model=list[HeatmapCell])
async def get_sector_heatmap(
    session: AsyncSession = Depends(get_session),
) -> list[HeatmapCell]:
    """Latest median fare per route x advance-purchase-window, for the heatmap view."""
    if session is not None:
        try:
            query = text(
                """
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
            )
            rows = (await session.execute(query)).mappings().all()
            if rows:
                return [HeatmapCell(**row) for row in rows]
        except Exception as e:
            logger.warning(f"Heatmap query fallback: {e}")

    return FALLBACK_HEATMAP


@router.get("/routes/{origin}/{destination}/elasticity", response_model=list[ElasticityPoint])
async def get_lead_time_elasticity(
    origin: str,
    destination: str,
    session: AsyncSession = Depends(get_session),
) -> list[ElasticityPoint]:
    """Fare vs advance-purchase-days curve for a single route (latest snapshot)."""
    o, d = origin.upper(), destination.upper()
    if session is not None:
        try:
            query = text(
                """
                select advance_purchase_days,
                       percentile_cont(0.5) within group (order by total_fare) as median_total_fare
                from fare_quote_clean
                where origin = :origin
                  and destination = :destination
                  and is_outlier = false
                  and availability_status = 'available'
                  and observed_at::date = (select max(observed_at::date) from fare_quote_clean)
                group by advance_purchase_days
                order by advance_purchase_days asc
                """
            )
            rows = (
                await session.execute(query, {"origin": o, "destination": d})
            ).mappings().all()
            if rows:
                return [ElasticityPoint(**row) for row in rows]
        except Exception as e:
            logger.warning(f"Elasticity query fallback: {e}")

    base_fares = {"DEL-BOM": 5120, "DEL-BLR": 5450, "BOM-BLR": 4050, "DEL-CCU": 4780, "BLR-HYD": 3020, "MAA-DEL": 5300}
    b = base_fares.get(f"{o}-{d}", 4500)
    return [
        ElasticityPoint(advance_purchase_days=1, median_total_fare=round(b * 1.65, 2)),
        ElasticityPoint(advance_purchase_days=7, median_total_fare=round(b * 1.25, 2)),
        ElasticityPoint(advance_purchase_days=15, median_total_fare=round(b * 1.00, 2)),
        ElasticityPoint(advance_purchase_days=30, median_total_fare=round(b * 0.85, 2)),
        ElasticityPoint(advance_purchase_days=45, median_total_fare=round(b * 0.78, 2)),
    ]


@router.get("/backtest", response_model=list[BacktestRow])
async def get_backtest_results(session: AsyncSession = Depends(get_session)) -> list[BacktestRow]:
    """APIx vs DGCA published monthly average fares — see docs/DESIGN.md §5."""
    if session is not None:
        try:
            query = text(
                "select period, apix_value, dgca_avg_fare, pct_deviation "
                "from backtest_result order by period asc"
            )
            rows = (await session.execute(query)).mappings().all()
            if rows:
                return [BacktestRow(**row) for row in rows]
        except Exception as e:
            logger.warning(f"Backtest query fallback: {e}")

    return FALLBACK_BACKTEST


@router.get("/scrape/trigger")
@router.post("/scrape/trigger")
async def trigger_live_scrape() -> dict:
    """Triggers an on-demand live scraping, cleaning, and index calculation batch."""
    try:
        from pipeline.runner import run_live_scrape_batch
        return run_live_scrape_batch()
    except Exception as e:
        logger.error(f"Live scrape trigger error: {e}")
        return {"status": "error", "message": str(e)}