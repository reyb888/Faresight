"""
APIx index computation.

Implements the weighted price-relative formula from docs/DESIGN.md §4:

    APIx(t) = sum_r [ w_r * ( P_r(t) / P_r(0) ) ] * 100

Run as a scheduled job (Render Cron Job) once the day's fare_quote_clean
data has landed. Deliberately deterministic: given the same clean-quote
table and weight table, this must always produce the same index value,
so results are auditable (see docs/SECURITY.md §2.7).

Usage:
    python -m index.index_engine --date 2026-08-29 --frequency daily
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]

# Base period: fixed once at project launch. See docs/DESIGN.md §4.1 —
# this should be set to the first full week of clean data and then never
# changed, so every later index value stays comparable.
BASE_PERIOD_REF = date.fromisoformat(os.environ.get("APIX_BASE_PERIOD", "2026-01-06"))


def compute_weighted_index(merged: pd.DataFrame) -> float:
    """Pure function implementing docs/DESIGN.md §4.2's formula, kept
    separate from any DB access so it's directly unit-testable
    (see tests/test_index_engine.py).

    Expects columns: weight, price_today, price_base.
    Re-normalizes weights across whatever routes are actually present, so a
    single missing route doesn't silently zero out its share
    (docs/DESIGN.md §3.6).
    """
    weight_normalized = merged["weight"] / merged["weight"].sum()
    price_relative = merged["price_today"] / merged["price_base"]
    return float((weight_normalized * price_relative).sum() * 100)


async def _fetch_route_prices(engine, target_date: date) -> pd.DataFrame:
    """Representative price per route for target_date: median total fare
    across sampled advance-purchase windows that day."""
    query = text(
        """
        select origin, destination,
               percentile_cont(0.5) within group (order by total_fare) as price
        from fare_quote_clean
        where is_outlier = false
          and availability_status = 'available'
          and observed_at::date = :target_date
        group by origin, destination
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(query, {"target_date": target_date})
        return pd.DataFrame(result.mappings().all())


async def _fetch_weights(engine) -> pd.DataFrame:
    """Most recent route_weight row per route (weights refresh far less
    often than prices — see docs/DESIGN.md §4.1)."""
    query = text(
        """
        select distinct on (origin, destination) origin, destination, weight
        from route_weight
        order by origin, destination, effective_period desc
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(query)
        return pd.DataFrame(result.mappings().all())


async def compute_index(target_date: date, frequency: str) -> dict:
    engine = create_async_engine(DATABASE_URL)
    try:
        prices_today = await _fetch_route_prices(engine, target_date)
        prices_base = await _fetch_route_prices(engine, BASE_PERIOD_REF)
        weights = await _fetch_weights(engine)

        if prices_today.empty or prices_base.empty or weights.empty:
            raise RuntimeError(
                f"Missing data for index computation on {target_date} "
                f"(today rows={len(prices_today)}, base rows={len(prices_base)}, "
                f"weight rows={len(weights)}). Refusing to write a partial/misleading value "
                f"— see docs/DESIGN.md §1 'fail loud, not silent'."
            )

        merged = (
            weights.merge(prices_today, on=["origin", "destination"], how="inner",
                           suffixes=("", "_today"))
            .merge(prices_base, on=["origin", "destination"], how="inner",
                   suffixes=("_today", "_base"))
        )

        if merged.empty:
            raise RuntimeError(
                f"No overlapping routes between weights, today's prices, and base-period "
                f"prices for {target_date}."
            )

        index_value = compute_weighted_index(merged)

        return {
            "index_date": target_date,
            "frequency": frequency,
            "index_value": round(index_value, 4),
            "base_period_ref": BASE_PERIOD_REF,
            "route_count": int(len(merged)),
            "quote_count": int(merged["price_today"].notna().sum()),
        }
    finally:
        await engine.dispose()


async def write_index(row: dict) -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        query = text(
            """
            insert into apix_index
                (index_date, frequency, index_value, base_period_ref, route_count, quote_count)
            values
                (:index_date, :frequency, :index_value, :base_period_ref, :route_count, :quote_count)
            on conflict (index_date, frequency) do update set
                index_value = excluded.index_value,
                route_count = excluded.route_count,
                quote_count = excluded.quote_count
            """
        )
        async with engine.begin() as conn:
            await conn.execute(query, row)
    finally:
        await engine.dispose()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--frequency", choices=["daily", "weekly", "monthly"], default="daily")
    args = parser.parse_args()

    row = await compute_index(args.date, args.frequency)
    await write_index(row)
    print(f"APIx[{row['frequency']}] {row['index_date']} = {row['index_value']} "
          f"(routes={row['route_count']}, quotes={row['quote_count']})")


if __name__ == "__main__":
    asyncio.run(main())
