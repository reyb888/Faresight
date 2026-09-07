import os
import asyncio
import logging
import time
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple

import httpx

from database import (
    get_all_routes,
    get_route_id,
    insert_airfare_records,
    LEAD_TIMES,
    delete_old_records,
    upsert_airfare_index,
    get_latest_index,
)
from config import (
    SERP_API_KEYS,
    SERP_API_KEY_POINTER,
    SERPAPI_DEFAULT_TIMEOUT,
    SERPAPI_MAX_RETRIES,
    SERPAPI_FALLBACK_TO_CACHE,
    INDEX_WEIGHTS,
)
from index_engine import compute_index

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP client configuration
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = SERPAPI_DEFAULT_TIMEOUT  # seconds, from config
HTTP_CLIENT = httpx.AsyncClient(timeout=SERPAPI_DEFAULT_TIMEOUT)


# ---------------------------------------------------------------------------
# Multi-key management & round-robin rotation
# ---------------------------------------------------------------------------

_active_key_index = 0
_keys_healthy: List[bool] = [True] * len(SERP_API_KEYS) if SERP_API_KEYS else []


def get_active_key() -> Optional[str]:
    """Return the current active SerpApi key, rotating if necessary.

    Implements failover: if the active key recently returned 429/401,
    advance the pointer to the next key.
    """
    global _active_key_index, _keys_healthy

    if not SERP_API_KEYS:
        return None

    # Count healthy keys
    healthy_count = sum(1 for h in _keys_healthy if h)
    if healthy_count == 0:
        logger.warning("No healthy SERP API keys remaining")
        return None

    # Rotate until we find a healthy key, starting from current position
    start = _active_key_index
    for i in range(len(SERP_API_KEYS)):
        idx = (start + i) % len(SERP_API_KEYS)
        if _keys_healthy[idx]:
            _active_key_index = idx
            return SERP_API_KEYS[idx]

    # All keys exhausted, reset and try first
    _keys_healthy = [True] * len(SERP_API_KEYS)
    _active_key_index = 0
    return SERP_API_KEYS[0] if SERP_API_KEYS else None


def mark_key_exhausted(key_index: int, reason: str = "") -> None:
    """Mark an API key as exhausted/failing."""
    global _keys_healthy
    if 0 <= key_index < len(_keys_healthy):
        _keys_healthy[key_index] = False
        logger.warning(f"Marked SERP API key[{key_index}] as exhausted: {reason}")


# ---------------------------------------------------------------------------
# SerpApi async fetch helpers
# ---------------------------------------------------------------------------

GOOGLE_FLIGHTS_ENDPOINT = "https://serpapi.com/search"


async def _fetch_single_route_async(
    origin: str,
    destination: str,
    departure_date: date,
    lead_time_days: int,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    """Async fetch a single route + lead time from SerpApi.

    Returns dict with fare data or None on failure.
    """
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date.isoformat(),
        "type": "2",
        "currency": "INR",
        "hl": "en",
        "api_key": api_key,
    }

    last_error = None

    for attempt in range(1 + SERPAPI_MAX_RETRIES):
        try:
            response = await HTTP_CLIENT.get(GOOGLE_FLIGHTS_ENDPOINT, params=params, timeout=HTTP_TIMEOUT)

            # Handle HTTP status codes
            if response.status_code == 429:
                # Quota hit - mark key as exhausted and fail over
                mark_key_exhausted(_active_key_index, f"HTTP 429 quota hit (attempt {attempt + 1})")
                # Rotate to next key
                active_key = get_active_key()
                if active_key:
                    params["api_key"] = active_key
                    response = await HTTP_CLIENT.get(GOOGLE_FLIGHTS_ENDPOINT, params=params, timeout=HTTP_TIMEOUT)
                else:
                    logger.error("No alternative API keys available after quota hit")
                    return None

            if response.status_code == 401:
                mark_key_exhausted(_active_key_index, f"HTTP 401 unauthorized")
                active_key = get_active_key()
                if active_key:
                    params["api_key"] = active_key
                    response = await HTTP_CLIENT.get(GOOGLE_FLIGHTS_ENDPOINT, params=params, timeout=HTTP_TIMEOUT)
                else:
                    return None

            if response.status_code != 200:
                logger.error(f"SerpApi HTTP {response.status_code} for {origin}->{destination} T+{lead_time_days}: {response.text[:300]}")
                return None

            results = response.json()

            if "error" in results:
                logger.error(f"SerpApi returned error: {results['error']}")
                if attempt < SERPAPI_MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None

            price, airline, duration = _extract_lowest_flight(results)

            if price is None:
                if attempt < SERPAPI_MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {
                    "origin_code": origin,
                    "destination_code": destination,
                    "capture_date": date.today().isoformat(),
                    "flight_date": departure_date.isoformat(),
                    "lead_time_days": lead_time_days,
                    "airline_name": None,
                    "price": None,
                    "currency": "INR",
                    "data_source": "SERPAPI",
                    "fetched_at": time.time(),
                }

            return {
                "origin_code": origin,
                "destination_code": destination,
                "capture_date": date.today().isoformat(),
                "flight_date": departure_date.isoformat(),
                "lead_time_days": lead_time_days,
                "airline_name": airline,
                "price": price,
                "currency": "INR",
                "data_source": "SERPAPI",
                "fetched_at": time.time(),
            }

        except httpx.TimeoutException:
            last_error = "Request timeout"
            logger.warning(f"SerpApi timeout for {origin}->{destination} T+{lead_time_days} (attempt {attempt + 1})")
            if attempt < SERPAPI_MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                # Rotate key on timeout
                active_key = get_active_key()
                if active_key:
                    params["api_key"] = active_key
            continue

        except Exception as e:
            last_error = str(e)
            logger.warning(f"SerpApi request failed for {origin}->{destination} T+{lead_time_days} (attempt {attempt + 1}): {e}")
            if attempt < SERPAPI_MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                # Rotate key on error
                active_key = get_active_key()
                if active_key:
                    params["api_key"] = active_key
            continue

    logger.error("All retries exhausted for %s->%s T+%d: %s", origin, destination, lead_time_days, last_error)
    return None


def _extract_lowest_flight(results: Dict[str, Any]) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """Extract lowest price, airline name, and flight duration from SerpApi response."""
    lowest_price = None
    lowest_airline = None
    lowest_duration = None

    try:
        flights_data = results.get("flights", [])
        for flight_group in flights_data:
            routes = flight_group.get("routes", [])
            for route in routes:
                fare_groups = route.get("fare_groups", [])
                for fare_group in fare_groups:
                    flights = fare_group.get("flights", [])
                    for flight in flights:
                        price_str = flight.get("price")
                        if price_str:
                            try:
                                price = float(str(price_str).replace(",", ""))
                            except (ValueError, TypeError):
                                continue
                            if lowest_price is None or price < lowest_price:
                                lowest_price = price
                                lowest_airline = flight.get("airline") or route.get("airline")
                                lowest_duration = flight.get("duration") or route.get("duration")
    except Exception as e:
        logger.warning("Failed to extract fare from response: %s", e)

    return lowest_price, lowest_airline, lowest_duration


# ---------------------------------------------------------------------------
# Core fetcher functions
# ---------------------------------------------------------------------------

async def fetch_live_route(
    origin: str,
    destination: str,
    lead_times: Optional[List[int]] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Async fetch fares for a route across all lead times.

    If SerpApi exceeds timeout during live demo, falls back to SQLite cached data.
    """
    if lead_times is None:
        lead_times = LEAD_TIMES

    today = date.today()
    records = []
    fallback_records = []  # Records from SQLite cache

    active_key = api_key or get_active_key()

    for lt in lead_times:
        departure_date = today + timedelta(days=lt)

        # Attempt async fetch with timeout
        try:
            fetch_result = await asyncio.wait_for(
                _fetch_single_route_async(origin, destination, departure_date, lt, active_key or get_active_key()),
                timeout=HTTP_TIMEOUT,
            )

            if fetch_result is not None:
                records.append(fetch_result)
            else:
                # Fallback to SQLite cache
                if SERPAPI_FALLBACK_TO_CACHE:
                    cached = _fetch_cached_fare(origin, destination, lt)
                    if cached:
                        fallback_records.append(cached)
                        logger.info(f"Fallback to cached data for {origin}->{destination} T+{lt}")

        except asyncio.TimeoutError:
            # Timeout exceeded - fall back to cached data
            logger.warning(f"SerpApi timeout for {origin}->{destination} T+{lt}, falling back to SQLite cache")
            if SERPAPI_FALLBACK_TO_CACHE:
                cached = _fetch_cached_fare(origin, destination, lt)
                if cached:
                    fallback_records.append(cached)

    # Combine live + fallback records
    all_records = records + fallback_records

    # Insert records into database
    if all_records:
        # Resolve route_ids
        for rec in all_records:
            if rec.get("route_id") is None:
                rid = get_route_id_by_codes(origin, destination)
                rec["route_id"] = rid

        inserted = insert_airfare_records_by_dict(all_records)
        logger.info(f"Inserted {inserted} fare records from {'live' if records else 'fallback'} fetch for {origin}->{destination}")

    return all_records


def _fetch_cached_fare(origin: str, destination: str, lead_time_days: int) -> Optional[Dict[str, Any]]:
    """Fetch a cached fare from SQLite by route + lead time."""
    from database import SessionLocal, AirfareRecords, get_latest_prices

    db = SessionLocal()
    try:
        # Try to find the most recent record for this route + lead time
        prices = get_latest_prices(db, lead_time_days=lead_time_days)
        # Filter by origin/destination match
        for p in prices:
            if p.get("origin_code") == origin and p.get("destination_code") == destination:
                # Reformat to match expected output schema
                return {
                    "origin_code": p.get("origin_code"),
                    "destination_code": p.get("destination_code"),
                    "capture_date": p.get("capture_date"),
                    "flight_date": p.get("flight_date"),
                    "lead_time_days": p.get("lead_time_days"),
                    "airline_name": p.get("airline_name"),
                    "price": p.get("price"),
                    "currency": p.get("currency", "INR"),
                    "data_source": p.get("data_source", "HISTORICAL_BASELINE"),
                    "fetched_at": p.get("fetched_at"),
                }
        return None
    finally:
        db.close()


# Helper functions for database operations
def get_route_id_by_codes(origin: str, destination: str) -> Optional[int]:
    """Look up route ID by origin/destination codes."""
    from database import SessionLocal, Routes, get_all_routes

    db = SessionLocal()
    try:
        row = db.query(Routes.id).filter(
            Routes.origin_code == origin.upper(),
            Routes.destination_code == destination.upper(),
        ).first()
        return row[0] if row else None
    finally:
        db.close()


def insert_airfare_records_by_dict(records: List[Dict[str, Any]]) -> int:
    """Insert airfare records dict using database module functions."""
    from database import SessionLocal, insert_airfare_records

    # Extract just the fields we need (keep origin/destination for route_id resolution)
    simplified = []
    for rec in records:
        simplified.append({
            "route_id": rec.get("route_id"),
            "origin_code": rec.get("origin_code"),
            "destination_code": rec.get("destination_code"),
            "capture_date": rec.get("capture_date"),
            "flight_date": rec.get("flight_date"),
            "lead_time_days": rec.get("lead_time_days"),
            "airline_name": rec.get("airline_name"),
            "price": rec.get("price"),
            "currency": rec.get("currency", "INR"),
            "data_source": rec.get("data_source", "SERPAPI"),
        })
    db = SessionLocal()
    try:
        return insert_airfare_records(db, simplified)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pipeline status & logging helpers
# ---------------------------------------------------------------------------

def update_pipeline_status(
    records_fetched: int,
    active_key_index: int,
    status_message: str = "",
) -> None:
    """Update pipeline status table."""
    from database import SessionLocal, PipelineStatus, SystemLogs, init_db

    init_db()
    db = SessionLocal()
    try:
        # Get or create pipeline status row
        status_row = db.query(PipelineStatus).order_by(PipelineStatus.id.desc()).first()

        if status_row is None:
            status_row = PipelineStatus()

        status_row.last_run_timestamp = time.time()
        status_row.records_fetched = records_fetched
        status_row.active_key_index = active_key_index
        if status_message:
            status_row.status_message = status_message

        db.add(status_row)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update pipeline status: {e}")
    finally:
        db.close()


def log_system_event(
    level: str,
    message: str,
) -> None:
    """Write a system log entry."""
    from database import SessionLocal, SystemLogs, init_db

    init_db()
    db = SessionLocal()
    try:
        log_entry = SystemLogs(
            log_level=level,
            message=message,
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to write system log: {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Batch fetch for all routes
# ---------------------------------------------------------------------------

async def fetch_all_routes_async() -> Dict[str, Any]:
    """Async fetch fares for all monitored routes across all lead times.

    Implements multi-key rotator and timeout failovers.
    """
    if not SERP_API_KEYS:
        return {"success": False, "error": "No SERP API keys configured"}

    routes = get_all_routes_db()
    if not routes:
        return {"success": False, "error": "No routes found in database"}

    all_records = []
    errors = []
    total_fetched = 0
    total_no_price = 0
    routes_processed = 0

    for route in routes:
        origin = route["origin_code"]
        destination = route["destination_code"]
        routes_processed += 1

        try:
            # Fetch with timeout and key rotation
            records = await fetch_live_route(origin, destination, lead_times=LEAD_TIMES)

            all_records.extend(records)
            for r in records:
                if r.get("price") is not None:
                    total_fetched += 1
                else:
                    total_no_price += 1

        except Exception as e:
            error_msg = f"Error fetching {origin}->{destination}: {e}"
            errors.append(error_msg)
            logger.exception(error_msg)

    # Insert all records
    inserted = 0
    if all_records:
        try:
            inserted = insert_airfare_records_by_dict(all_records)
        except Exception as e:
            errors.append(f"DB insert error: {e}")
            logger.exception("Failed to insert airfare records")

    # Prune old records
    try:
        delete_count = delete_old_records_db(older_than_days=90)
    except Exception as e:
        logger.warning(f"Failed to prune old records: {e}")
        delete_count = 0

    # Compute index
    try:
        compute_result = compute_index(force_recompute=True)
    except Exception as e:
        logger.error(f"Index computation failed: {e}")
        compute_result = {"computed": False, "error": str(e)}

    # Update pipeline status
    active_key_idx = _active_key_index if SERP_API_KEYS else 0
    update_pipeline_status(
        records_fetched=total_fetched,
        active_key_index=active_key_idx,
        status_message=f"Processed {routes_processed} routes, found {total_fetched} prices",
    )

    summary = {
        "success": True,
        "routes_processed": routes_processed,
        "records_generated": len(all_records),
        "prices_found": total_fetched,
        "no_price": total_no_price,
        "errors": errors,
        "index_computed": compute_result.get("computed", False),
        "composite_index": compute_result.get("composite_index"),
    }
    logger.info("Async fetch complete: %s", summary)
    return summary


# Database helper wrappers
def get_all_routes_db():
    """Wrapper to get all routes from database."""
    from database import SessionLocal, get_all_routes as _get_all_routes

    db = SessionLocal()
    try:
        return _get_all_routes(db)
    finally:
        db.close()


def delete_old_records_db(older_than_days: int = 90) -> int:
    """Wrapper to delete old records."""
    from database import delete_old_records, SessionLocal

    db = SessionLocal()
    try:
        return delete_old_records(db, older_than_days=older_than_days)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print(f"SERP_API_KEYS configured: {len(SERP_API_KEYS) if SERP_API_KEYS else 0} keys")
    print(f"Active key index: {_active_key_index}")
    print(f"Healthy keys: {sum(1 for h in _keys_healthy if h) if _keys_healthy else 0}")

    # Demo: fetch a single route
    import asyncio

    async def demo():
        result = await fetch_live_route("DEL", "BOM", lead_times=[1, 3, 5])
        print(f"\nFetched {len(result)} records for DEL-BOM T+1, T+3, T+5:")
        for r in result:
            print(f"  T+{r['lead_time_days']}: {r.get('airline_name')} - {r.get('price')} INR (source: {r.get('data_source')})")

    asyncio.run(demo())