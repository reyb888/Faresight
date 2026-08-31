"""
/v1/index, /v1/routes, /v1/heatmap, /v1/elasticity, /v1/backtest

Read-only endpoints over the tables defined in db/migrations/001_init.sql.
The dashboard and any external consumer (NSO/RBI) hit these same endpoints —
see docs/SYSTEM_ARCHITECTURE.md §2.5 for why there's no direct-DB shortcut.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/v1", tags=["index"], dependencies=[Depends(require_api_key)])


@router.get("/index", response_model=list[IndexPoint])
async def get_index_series(
    frequency: str = Query(default="daily"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[IndexPoint]:
    """Returns the APIx time series at the requested frequency."""
    freq = frequency if frequency in ["daily", "weekly", "monthly"] else "daily"
    query = text(
        """
        select index_date, frequency, index_value, base_period_ref,
               route_count, quote_count
        from apix_index
        where frequency = :frequency
          and (:start is null or index_date >= :start)
          and (:end is null or index_date <= :end)
        order by index_date asc
        """
    )
    rows = (
        await session.execute(
            query, {"frequency": freq, "start": start, "end": end}
        )
    ).mappings().all()
    return [IndexPoint(**row) for row in rows]


@router.get("/routes/{origin}/{destination}", response_model=RouteSeries)
async def get_route_series(
    origin: str,
    destination: str,
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> RouteSeries:
    """Per-route median fare history, for the Route Explorer dashboard view."""
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
            {"origin": origin.upper(), "destination": destination.upper(), "days": days},
        )
    ).mappings().all()
    return RouteSeries(
        origin=origin.upper(),
        destination=destination.upper(),
        points=[RouteSeriesPoint(**row) for row in rows],
    )


@router.get("/heatmap", response_model=list[HeatmapCell])
async def get_sector_heatmap(
    session: AsyncSession = Depends(get_session),
) -> list[HeatmapCell]:
    """Latest median fare per route x advance-purchase-window, for the heatmap view."""
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
    return [HeatmapCell(**row) for row in rows]


@router.get("/routes/{origin}/{destination}/elasticity", response_model=list[ElasticityPoint])
async def get_lead_time_elasticity(
    origin: str,
    destination: str,
    session: AsyncSession = Depends(get_session),
) -> list[ElasticityPoint]:
    """Fare vs advance-purchase-days curve for a single route (latest snapshot)."""
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
        await session.execute(query, {"origin": origin.upper(), "destination": destination.upper()})
    ).mappings().all()
    return [ElasticityPoint(**row) for row in rows]


@router.get("/backtest", response_model=list[BacktestRow])
async def get_backtest_results(session: AsyncSession = Depends(get_session)) -> list[BacktestRow]:
    """APIx vs DGCA published monthly average fares — see docs/DESIGN.md §5."""
    query = text(
        "select period, apix_value, dgca_avg_fare, pct_deviation "
        "from backtest_result order by period asc"
    )
    rows = (await session.execute(query)).mappings().all()
    return [BacktestRow(**row) for row in rows]