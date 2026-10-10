import os
import json
import csv
import random
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from database import (
    init_db,
    get_db,
    ROUTES_DEFINITIONS,
    insert_airfare_records,
    LEAD_TIMES,
    get_price_baseline,
    upsert_airfare_index,
    get_latest_index,
)
from config import LEAD_TIMES as CONFIG_LEAD_TIMES, INDEX_WEIGHTS

# ---------------------------------------------------------------------------
# Price dynamic constants (realistic Indian airfare behavior)
# T+1 fares are 45-65% higher than T+30 fares (advance purchase discount)
# ---------------------------------------------------------------------------
BASE_PRICE_RANGES = {
    "DEL-BOM": (3000, 8000),  # Delhi-Mumbai highest volume
    "BLR-DEL": (2500, 7000),
    "MAA-DEL": (2800, 7500),
    "CCU-BOM": (2200, 6500),
    "HYD-DEL": (2400, 6800),
}

# Airline carriers that operate these routes
CARRIERS = [
    "IndiGo",
    "Air India",
    "Vistara",
    "Akasa Air",
    "SpiceJet",
    "GoAir",
]


def _random_price(route_key: str, lead_time: int) -> float:
    """Generate a realistic price for a route+lead-time combo.

    Dynamics:
    - T+1: highest price (45-65% above T+30 baseline)
    - T+30, T+45: lowest prices (baseline)
    - Linear interpolation between extremes
    """
    min_price, max_price = BASE_PRICE_RANGES[route_key]

    # Base price decreases as lead time increases (advance purchase discount)
    # T+1 is ~50% higher than T+30 on average
    if lead_time <= 1:
        # T+1: 50-65% premium
        premium_factor = random.uniform(1.45, 1.65)
    elif lead_time <= 3:
        premium_factor = random.uniform(1.30, 1.50)
    elif lead_time <= 5:
        premium_factor = random.uniform(1.15, 1.35)
    elif lead_time <= 7:
        premium_factor = random.uniform(1.10, 1.25)
    elif lead_time <= 15:
        premium_factor = random.uniform(1.00, 1.15)
    elif lead_time <= 30:
        premium_factor = random.uniform(0.90, 1.00)
    else:  # T+30, T+45
        premium_factor = random.uniform(0.70, 0.90)

    # Apply some randomness within the factor band
    price = random.uniform(min_price, max_price) * premium_factor
    # Clamp to valid range
    price = max(min_price, min(max_price, price))
    return round(price, 2)


def _random_airline() -> str:
    """Select a random airline carrier."""
    return random.choice(CARRIERS)


def seed_historical_data(
    db_session=None,
    days_back: int = 60,
    routes: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Seed the SQLite database with 60 days of historical fare data.

    Populates airfare_records with realistic synthetic data across all
    5 SIH26056 corridors and 7 lead-time windows (T+1 through T+45).

    Returns a summary dict with insertion statistics.
    """
    if routes is None:
        routes = ROUTES_DEFINITIONS()

    # Use provided session or create one
    if db_session is None:
        from database import SessionLocal
        db_session = SessionLocal()

    try:
        # Determine base period (first capture_date we'll use)
        base_date = date.today() - timedelta(days=days_back)

        records_created = 0
        routes_processed = 0
        records: List[Dict[str, Any]] = []

        for route in routes:
            origin = route["origin_code"]
            destination = route["destination_code"]
            route_key = f"{origin}-{destination}"

            # For each lead time, generate records for each day over the period
            for day_offset in range(days_back):
                capture_date = base_date + timedelta(days=day_offset)

                # Generate one record per lead time for this capture date
                for lt in LEAD_TIMES:
                    # Flight date is capture_date + lead_time_days (the date the flight is for)
                    flight_date = capture_date + timedelta(days=lt)

                    price = _random_price(route_key, lt)
                    airline = _random_airline()

                    record = {
                        "route_id": None,  # Will be resolved by insert_airfare_records
                        "origin_code": origin,
                        "destination_code": destination,
                        "capture_date": capture_date.isoformat(),
                        "flight_date": flight_date.isoformat(),
                        "lead_time_days": lt,
                        "airline_name": airline,
                        "price": price,
                        "currency": "INR",
                        "data_source": "HISTORICAL_BASELINE",
                    }

                    records.append(record)

            routes_processed += 1

        # Bulk-insert via the ORM helper (resolves route_ids, commits)
        records_created = insert_airfare_records(db_session, records)

        # Now compute and store the initial index
        from index_engine import compute_index
        compute_result = compute_index(force_recompute=True)

        return {
            "status": "success",
            "records_created": records_created,
            "routes_processed": routes_processed,
            "index_computed": compute_result.get("computed", False),
            "composite_index": compute_result.get("composite_index"),
            "message": f"Seeded {records_created} historical records across {routes_processed} routes",
        }

    except Exception as e:
        db_session.rollback()
        import logging
        logging.error(f"Seeder error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db_session.close()


def load_local_datafile(filepath: str, db_session=None) -> Dict[str, Any]:
    """Load fare data from a local JSON or CSV file.

    Supported formats:
    - happyfares_snapshot.json: [{origin, destination, capture_date, flight_date, lead_time_days, airline_name, price, data_source}, ...]
    - baseline_fares.csv: same columns as CSV

    Returns a summary dict with insertion statistics.
    """
    if not os.path.exists(filepath):
        return {"status": "error", "message": f"File not found: {filepath}"}

    # Use provided session or create one
    if db_session is None:
        from database import SessionLocal
        db_session = SessionLocal()

    try:
        ext = filepath.rsplit(".", 1)[-1].lower()
        records_imported = 0

        if ext == "json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                # Validate expected columns
                required = {"origin_code", "destination_code", "capture_date", "flight_date", "lead_time_days", "airline_name", "price"}
                valid_records = []
                for row in data:
                    if all(k in row for k in required):
                        # Ensure lead_time_days is int
                        row["lead_time_days"] = int(row["lead_time_days"])
                        row["price"] = float(row["price"])
                        valid_records.append(row)
                    else:
                        import logging
                        logging.warning(f"Skipping JSON row missing required keys: {row}")
                records_imported = insert_airfare_records(db_session, valid_records)
            else:
                return {"status": "error", "message": "JSON file is empty or not a list"}

        elif ext == "csv":
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                required = {"origin_code", "destination_code", "capture_date", "flight_date", "lead_time_days", "airline_name", "price"}
                if not required.issubset(set(fieldnames)):
                    return {
                        "status": "error",
                        "message": f"CSV missing required columns. Found: {fieldnames}",
                    }
                csv_rows = []
                for row in reader:
                    try:
                        row["lead_time_days"] = int(row["lead_time_days"])
                        row["price"] = float(row["price"])
                        csv_rows.append(row)
                    except (ValueError, KeyError) as e:
                        import logging
                        logging.warning(f"Skipping CSV row due to error: {e} / row={row}")
                records_imported = insert_airfare_records(db_session, csv_rows)
        else:
            return {"status": "error", "message": f"Unsupported file extension: {ext}"}

        db_session.commit()

        # Recompute index after loading local data
        from index_engine import compute_index
        compute_result = compute_index(force_recompute=True)

        return {
            "status": "success",
            "records_imported": records_imported,
            "index_computed": compute_result.get("computed", False),
            "composite_index": compute_result.get("composite_index"),
            "message": f"Imported {records_imported} records from {filepath}",
        }

    except Exception as e:
        db_session.rollback()
        import logging
        logging.error(f"Local datafile loader error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db_session.close()


def generate_price_dynamics_report(session) -> Dict[str, Any]:
    """Generate a report verifying price dynamics: T+1 should be 45-65% higher than T+30.

    Returns a dict with bucket averages and compliance status.
    """
    from index_engine import get_prices_by_lead_time_bucket

    # Get latest capture date data
    buckets = get_prices_by_lead_time_bucket(session=session)

    report = {
        "buckets": {
            "short": {"count": len(buckets["short"]), "avg": round(sum(buckets["short"]) / len(buckets["short"]), 2) if buckets["short"] else None},
            "medium": {"count": len(buckets["medium"]), "avg": round(sum(buckets["medium"]) / len(buckets["medium"]), 2) if buckets["medium"] else None},
            "long": {"count": len(buckets["long"]), "avg": round(sum(buckets["long"]) / len(buckets["long"]), 2) if buckets["long"] else None},
        },
        "dynamics_compliant": False,
    }

    # Check: short (T+1, T+3) should be 45-65% higher than long (T+30, T+45)
    short_avg = report["buckets"]["short"]["avg"]
    long_avg = report["buckets"]["long"]["avg"]

    if short_avg is not None and long_avg is not None and long_avg > 0:
        ratio = short_avg / long_avg
        # Expected: 1.45 <= ratio <= 1.65
        report["dynamics_compliant"] = 1.45 <= ratio <= 1.65
        report["short_long_ratio"] = round(ratio, 3)
        report["expected_range"] = {"min": 1.45, "max": 1.65}

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Initialize database
    init_db()

    # Seed historical data
    result = seed_historical_data(days_back=60)
    print(json.dumps(result, indent=2, default=str))

    # Generate dynamics report
    from database import SessionLocal
    db = SessionLocal()
    report = generate_price_dynamics_report(db)
    print("\n--- Price Dynamics Report ---")
    print(json.dumps(report, indent=2, default=str))
    db.close()