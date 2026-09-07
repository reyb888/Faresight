from datetime import date, datetime
from typing import Dict, Any, Optional, List
from database import (
    get_prices_by_lead_time_bucket,
    get_price_baseline,
    upsert_airfare_index,
    get_latest_index,
    get_indices,
    get_record_count,
    SessionLocal,
    AirfareRecords,
    Routes,
    AirfareIndices,
    and_,
)

WEIGHTS = {
    "short": 0.40,
    "medium": 0.35,
    "long": 0.25,
}

SHORT_LEAD_TIMES = [1, 3]
MEDIUM_LEAD_TIMES = [5, 7, 15]
LONG_LEAD_TIMES = [30, 45]


def _bucket_average(prices: List[float]) -> Optional[float]:
    if not prices:
        return None
    return sum(prices) / len(prices)


def _compute_bucket_index(
    current_prices: List[float],
    base_prices: List[float],
) -> Optional[float]:
    """Compute a Laspeyres sub-index for a single bucket.

    Formula: I_bucket = (avg(current_prices) / avg(base_prices)) * 100
    """
    if not current_prices or not base_prices:
        return None

    current_avg = _bucket_average(current_prices)
    base_avg = _bucket_average(base_prices)

    if current_avg is None or base_avg is None or base_avg == 0:
        return None

    return round((current_avg / base_avg) * 100, 2)


def _get_base_prices_for_bucket(
    session,
    bucket_lead_times: List[int],
    capture_date: Optional[str] = None,
) -> Optional[List[float]]:
    """Get average base period prices for a given lead-time bucket.

    The base period is the earliest capture_date in the database.
    """
    from sqlalchemy import func

    conditions = [AirfareRecords.price.isnot(None)]

    if capture_date is not None:
        conditions.append(AirfareRecords.capture_date == capture_date)
    else:
        # Use the earliest capture_date as base period
        subq = (
            session.query(func.min(AirfareRecords.capture_date))
            .select_from(AirfareRecords)
            .scalar()
        )
        if subq:
            conditions.append(AirfareRecords.capture_date == str(subq))

    # Get prices for the specific lead times in this bucket
    prices = []
    for lt in bucket_lead_times:
        row = (
            session.query(AirfareRecords.price)
            .filter(and_(*conditions, AirfareRecords.lead_time_days == lt))
            .limit(1)
            .scalar()
        )
        if row is not None:
            prices.append(float(row))

    return prices if prices else None


def compute_index(
    capture_date: Optional[str] = None,
    force_recompute: bool = False,
) -> Dict[str, Any]:
    """Compute weighted Airfare Price Index using Laspeyres formula.

    $$I = \left( \sum (W_i \times \frac{P_{current, i}}{P_{base, i}}) \right) \times 100$$

    Short-Lead Bucket (T+1, T+3):  weight 0.40
    Medium-Lead Bucket (T+5, T+7, T+15): weight 0.35
    Long-Lead Bucket (T+30, T+45): weight 0.25

    Each sub-index = (bucket_avg_current_price / bucket_avg_base_price) * 100
    Composite = short_index * 0.40 + medium_index * 0.35 + long_index * 0.25

    Results are saved to airfare_indices table.
    """
    from index_engine import WEIGHTS as BASE_WEIGHTS

    if capture_date is None:
        capture_date = date.today().isoformat()

    # Use provided session
    session = SessionLocal()
    try:
        latest = get_latest_index.__func__(session) if hasattr(get_latest_index, "__func__") else None
        # Check if index already computed for today
        if latest and not force_recompute:
            row = session.query(AirfareIndices).filter_by(id=latest['id']).first()
            if row:
                return {
                    "computed": False,
                    "reason": "Latest index already exists for today. Use force_recompute=True to override.",
                    "index": {
                        "short_term_index": row.short_term_index,
                        "medium_term_index": row.medium_term_index,
                        "long_term_index": row.long_term_index,
                        "composite_index": row.composite_index,
                    },
                }

        # Actually, let's query the DB directly
        from sqlalchemy import desc, text
        row = session.query(AirfareIndices).filter(
            AirfareIndices.calculated_at >= capture_date
        ).order_by(desc(AirfareIndices.calculated_at)).limit(1).first()

        # Simpler approach: just always compute and upsert
        buckets = get_prices_by_lead_time_bucket(session=session, capture_date=capture_date)
        if not any(buckets.values()):
            return {
                "computed": False,
                "reason": "No price data available for index computation",
                "buckets": buckets,
            }

        # Get baseline price (average from base period)
        baseline = get_price_baseline(session=session, capture_date=None)
        if baseline is None or baseline == 0:
            baseline = 100.0

        # Compute bucket indices using Laspeyres formula
        # Short bucket: T+1, T+3
        short_current = buckets.get("short", [])
        # For base period, we need prices from the earliest data
        short_base = _get_base_prices_for_bucket(session, SHORT_LEAD_TIMES, capture_date=None)

        # Medium bucket: T+5, T+7, T+15
        medium_current = buckets.get("medium", [])
        medium_base = _get_base_prices_for_bucket(session, MEDIUM_LEAD_TIMES, capture_date=None)

        # Long bucket: T+30, T+45
        long_current = buckets.get("long", [])
        long_base = _get_base_prices_for_bucket(session, LONG_LEAD_TIMES, capture_date=None)

        short_index = _compute_bucket_index(short_current, short_base)
        medium_index = _compute_bucket_index(medium_current, medium_base)
        long_index = _compute_bucket_index(long_current, long_base)

        # Compute composite index using weights
        w = WEIGHTS
        composite = None
        indices_present = [i for i in [short_index, medium_index, long_index] if i is not None]

        if len(indices_present) >= 1:
            # Weighted average present - normalize weights proportionally
            if short_index is not None and medium_index is not None and long_index is not None:
                composite = round(
                    w["short"] * short_index + w["medium"] * medium_index + w["long"] * long_index,
                    2,
                )
            elif short_index is not None and medium_index is not None:
                # Normalize: divide by sum of applicable weights
                composite = round(
                    (w["short"] * short_index + w["medium"] * medium_index) / (w["short"] + w["medium"]),
                    2,
                )
            elif short_index is not None:
                composite = short_index

        # Upsert the index row
        index_row = {
            "date": capture_date,
            "short_term_index": short_index,
            "medium_term_index": medium_index,
            "long_term_index": long_index,
            "composite_index": composite,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Use raw SQL upsert
        from sqlalchemy import text
        date_val = capture_date

        session.execute(
            text(
                """INSERT INTO airfare_indices
                   (date, short_term_index, medium_term_index, long_term_index, composite_index, created_at)
                   VALUES (:date, :short_term_index, :medium_term_index, :long_term_index, :composite_index, :created_at)
                   ON CONFLICT(date) DO UPDATE SET
                       short_term_index = EXCLUDED.short_term_index,
                       medium_term_index = EXCLUDED.medium_term_index,
                       long_term_index = EXCLUDED.long_term_index,
                       composite_index = EXCLUDED.composite_index,
                       created_at = EXCLUDED.created_at"""
            ),
            {
                "date": date_val,
                "short_term_index": short_index,
                "medium_term_index": medium_index,
                "long_term_index": long_index,
                "composite_index": composite,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        session.commit()

        summary = {
            "computed": True,
            "date": capture_date,
            "baseline_price": round(baseline, 2),
            "bucket_averages": {
                "short": round(_bucket_average(short_current), 2) if short_current else None,
                "medium": round(_bucket_average(medium_current), 2) if medium_current else None,
                "long": round(_bucket_average(long_current), 2) if long_current else None,
            },
            "short_term_index": short_index,
            "medium_term_index": medium_index,
            "long_term_index": long_index,
            "composite_index": composite,
            "weights": w,
            "record_count": get_record_count.__func__(session) if hasattr(get_record_count, "__func__") else {},
        }
        return summary

    except Exception as e:
        session.rollback()
        import logging
        logging.error(f"Index computation error: {e}")
        return {
            "computed": False,
            "reason": f"Index computation failed: {e}",
        }
    finally:
        session.close()


def get_index_history(days: int = 30) -> List[Dict[str, Any]]:
    """Return recent index history for dashboard charts/tables."""
    session = SessionLocal()
    try:
        from sqlalchemy import desc
        rows = (
            session.query(AirfareIndices)
            .order_by(desc(AirfareIndices.calculated_at))
            .limit(days)
            .all()
        )
        return [
            {
                "id": r.id,
                "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
                "short_term_index": r.short_term_index,
                "medium_term_index": r.medium_term_index,
                "long_term_index": r.long_term_index,
                "composite_index": r.composite_index,
            }
            for r in rows
        ]
    finally:
        session.close()


def get_current_index() -> Optional[Dict[str, Any]]:
    """Return the most recent index."""
    session = SessionLocal()
    try:
        from sqlalchemy import desc
        row = (
            session.query(AirfareIndices)
            .order_by(desc(AirfareIndices.calculated_at))
            .limit(1)
            .first()
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "calculated_at": row.calculated_at.isoformat() if row.calculated_at else None,
            "short_term_index": row.short_term_index,
            "medium_term_index": row.medium_term_index,
            "long_term_index": row.long_term_index,
            "composite_index": row.composite_index,
        }
    finally:
        session.close()


if __name__ == "__main__":
    import logging
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    result = compute_index(force_recompute=True)
    print(json.dumps(result, indent=2, default=str))