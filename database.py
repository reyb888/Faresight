import os
import sys
import json
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.exc import SQLAlchemyError

from dotenv import load_dotenv
load_dotenv()

Base = declarative_base()

# ---------------------------------------------------------------------------
# Database path configuration
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get(
    "AIRFARE_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "airfare.db"),
)

SQLITE_URL = f"sqlite:///{DB_PATH}"
POSTGRES_URL = os.environ.get("DATABASE_URL", "")
POSTGRES_SYNC_URL = os.environ.get("DATABASE_URL_SYNC", "")

# Detect if we should use PostgreSQL or SQLite.
# On Vercel serverless the filesystem is read-only except /tmp and there is
# no persistent disk, so always use an ephemeral SQLite DB there and ignore
# any stale DATABASE_URL env vars.
if os.environ.get("VERCEL") == "1":
    DB_PATH = "/tmp/airfare.db"
    SQLITE_URL = f"sqlite:///{DB_PATH}"
    _USE_SUPABASE = False
    _engine = create_engine(SQLITE_URL, echo=False, connect_args={"check_same_thread": False})
elif POSTGRES_SYNC_URL and POSTGRES_SYNC_URL.startswith("postgresql"):
    _USE_SUPABASE = True
    _engine = create_engine(POSTGRES_SYNC_URL, echo=False, future=True)
elif POSTGRES_URL and POSTGRES_URL.startswith("postgresql"):
    _USE_SUPABASE = True
    _engine = create_engine(POSTGRES_URL, echo=False, future=True)
else:
    _USE_SUPABASE = False
    _engine = create_engine(SQLITE_URL, echo=False, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

# Lead-time buckets (days in advance) shared by seeder / fetcher / API.
LEAD_TIMES = [1, 3, 5, 7, 15, 30, 45]


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class Routes(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    origin_code = Column(String(10), nullable=False, index=True)
    destination_code = Column(String(10), nullable=False, index=True)
    route_name = Column(String(100), nullable=False)

    __table_args__ = (UniqueConstraint("origin_code", "destination_code", name="uq_route_code"),)


class AirfareRecords(Base):
    __tablename__ = "airfare_records"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False, index=True)
    capture_date = Column(Text, nullable=False)
    flight_date = Column(Text, nullable=False)
    lead_time_days = Column(Integer, nullable=False)
    airline_name = Column(String(100))
    price = Column(Text)
    currency = Column(String(3), default="INR", nullable=False)
    data_source = Column(String(20), nullable=False, default="HISTORICAL_BASELINE")
    fetched_at = Column(DateTime, default=datetime.utcnow)

    # Relationship back to route
    route = relationship("Routes", lazy="select")


class AirfareIndices(Base):
    __tablename__ = "airfare_indices"

    id = Column(Integer, primary_key=True, index=True)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    short_term_index = Column(Text, nullable=True)
    medium_term_index = Column(Text, nullable=True)
    long_term_index = Column(Text, nullable=True)
    composite_index = Column(Text, nullable=True)

    __table_args__ = (Index("ix_airfare_indices_calculated_at", "calculated_at"),)


class SystemLogs(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    log_level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)


class PipelineStatus(Base):
    __tablename__ = "pipeline_status"

    id = Column(Integer, primary_key=True, index=True)
    last_run_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    records_fetched = Column(Integer, default=0, nullable=False)
    active_key_index = Column(Integer, default=0, nullable=False)
    status_message = Column(Text, nullable=True, default="")


# ---------------------------------------------------------------------------
# Engine initialization
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables and insert default routes if using SQLite."""
    try:
        Base.metadata.create_all(_engine)

        if not _USE_SUPABASE:
            conn = _engine.connect()
            try:
                # Insert default routes using INSERT OR IGNORE
                for r in ROUTES_DEFINITIONS():
                    conn.execute(
                        text(
                            """INSERT OR IGNORE INTO routes
                               (origin_code, destination_code, route_name)
                               VALUES (:o, :d, :n)"""
                        ),
                        {"o": r["origin_code"], "d": r["destination_code"], "n": r["route_name"]},
                    )
                conn.commit()
            finally:
                conn.close()
    except SQLAlchemyError as e:
        print(f"Database init error: {e}", file=sys.stderr)


def ROUTES_DEFINITIONS() -> List[Dict[str, str]]:
    """Return route definitions matching the SIH26056 corridors."""
    return [
        {"origin_code": "DEL", "destination_code": "BOM", "route_name": "DEL → BOM"},
        {"origin_code": "BLR", "destination_code": "DEL", "route_name": "BLR → DEL"},
        {"origin_code": "MAA", "destination_code": "DEL", "route_name": "MAA → DEL"},
        {"origin_code": "CCU", "destination_code": "BOM", "route_name": "CCU → BOM"},
        {"origin_code": "HYD", "destination_code": "DEL", "route_name": "HYD → DEL"},
    ]


# ---------------------------------------------------------------------------
# Dependency-style helpers (mimic FastAPI Depends)
# ---------------------------------------------------------------------------

def get_db() -> Session:
    """Yield a SQLAlchemy session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Route lookup helpers
# ---------------------------------------------------------------------------

def get_route_id(session: Session, origin_code: str, destination_code: str) -> Optional[int]:
    """Look up route ID by origin/destination codes."""
    row = session.query(Routes.id).filter(
        Routes.origin_code == origin_code.upper(),
        Routes.destination_code == destination_code.upper(),
    ).first()
    return row[0] if row else None


def get_all_routes(session: Session) -> List[Dict[str, Any]]:
    """Return all routes with their IDs."""
    rows = session.query(Routes).order_by(Routes.route_name).all()
    return [
        {"id": r.id, "origin_code": r.origin_code, "destination_code": r.destination_code, "route_name": r.route_name}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Airfare record helpers
# ---------------------------------------------------------------------------

def insert_airfare_records(session: Session, records: List[Dict[str, Any]]) -> int:
    """Insert multiple airfare records. Returns count inserted."""
    inserted = 0
    for rec in records:
        route_id = rec.get("route_id")
        if route_id is None:
            route_id = get_route_id(session, rec["origin_code"], rec["destination_code"])
        if route_id is None:
            continue
        record = AirfareRecords(
            route_id=route_id,
            capture_date=rec.get("capture_date", date.today().isoformat()),
            flight_date=rec.get("flight_date", ""),
            lead_time_days=rec.get("lead_time_days", 1),
            airline_name=rec.get("airline_name"),
            price=rec.get("price"),
            currency=rec.get("currency", "INR"),
            data_source=rec.get("data_source", "HISTORICAL_BASELINE"),
            fetched_at=datetime.utcnow(),
        )
        session.add(record)
        inserted += 1
    try:
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logging.error(f"Failed to insert airfare records: {e}")
        return 0
    return inserted


def get_latest_prices(
    session: Session,
    route_id: Optional[int] = None,
    lead_time_days: Optional[int] = None,
    capture_date: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Query latest airfare prices with optional filters."""
    from sqlalchemy import desc

    query = session.query(AirfareRecords).join(Routes)

    if route_id is not None:
        query = query.filter(AirfareRecords.route_id == route_id)
    if lead_time_days is not None:
        query = query.filter(AirfareRecords.lead_time_days == lead_time_days)
    if capture_date is not None:
        query = query.filter(AirfareRecords.capture_date == capture_date)

    results = (
        query.order_by(AirfareRecords.flight_date.asc(), AirfareRecords.lead_time_days.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": r.id,
            "route_id": r.route_id,
            "origin_code": r.route.origin_code if r.route else None,
            "destination_code": r.route.destination_code if r.route else None,
            "route_name": r.route.route_name if r.route else None,
            "capture_date": r.capture_date,
            "flight_date": r.flight_date,
            "lead_time_days": r.lead_time_days,
            "airline_name": r.airline_name,
            "price": float(r.price) if r.price is not None else None,
            "currency": r.currency,
            "data_source": r.data_source,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in results
    ]


def delete_old_records(session: Session, older_than_days: int = 90) -> int:
    """Delete records older than N days based on capture_date."""
    from sqlalchemy import func

    cutoff = func.date_sub(func.current_date(), func.text(f"INTERVAL {older_than_days} DAY"))
    # SQLite compatible
    if "sqlite" in str(_engine.url):
        cutoff_date = func.date("now", f"-{older_than_days} days")
        rows = session.query(AirfareRecords).filter(
            AirfareRecords.capture_date < cutoff_date
        ).delete(synchronize_session=False)
    else:
        rows = session.query(AirfareRecords).filter(
            AirfareRecords.capture_date < cutoff
        ).delete(synchronize_session=False)
    try:
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logging.error(f"Failed to delete old records: {e}")
        return 0
    return rows


# ---------------------------------------------------------------------------
# Airfare index helpers
# ---------------------------------------------------------------------------

def upsert_airfare_index(
    session: Session,
    *,
    calculated_at: datetime,
    short_term_index: Optional[float],
    medium_term_index: Optional[float],
    long_term_index: Optional[float],
    composite_index: Optional[float],
) -> AirfareIndices:
    """Upsert an airfare index row keyed on calculated_at date."""
    # Use date portion only for UNIQUE constraint
    date_str = calculated_at.date().isoformat()

    row = session.query(AirfareIndices).filter(
        AirfareIndices.calculated_at.like(f"{date_str}%")
    ).first()

    if row is None:
        row = AirfareIndices(
            calculated_at=calculated_at,
            short_term_index=short_term_index,
            medium_term_index=medium_term_index,
            long_term_index=long_term_index,
            composite_index=composite_index,
        )
        session.add(row)
    else:
        row.short_term_index = short_term_index
        row.medium_term_index = medium_term_index
        row.long_term_index = long_term_index
        row.composite_index = composite_index
        row.calculated_at = calculated_at

    try:
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logging.error(f"Failed to upsert airfare index: {e}")

    return row


def get_indices(
    session: Session,
    since: Optional[str] = None,
    limit: int = 365,
) -> List[Dict[str, Any]]:
    """Return recent airfare index records."""
    from sqlalchemy import desc

    query = session.query(AirfareIndices).order_by(desc(AirfareIndices.calculated_at))

    if since is not None:
        query = query.filter(AirfareIndices.calculated_at >= since)

    results = query.limit(limit).all()

    return [
        {
            "id": r.id,
            "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
            "short_term_index": r.short_term_index,
            "medium_term_index": r.medium_term_index,
            "long_term_index": r.long_term_index,
            "composite_index": r.composite_index,
        }
        for r in results
    ]


def get_latest_index(session: Session) -> Optional[Dict[str, Any]]:
    """Return the most recent airfare index."""
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


# ---------------------------------------------------------------------------
# Baseline / price helpers
# ---------------------------------------------------------------------------

def get_price_baseline(session: Session, capture_date: Optional[str] = None) -> Optional[float]:
    """Compute the average price from the base period (earliest capture_date)."""
    from sqlalchemy import func

    if capture_date is not None:
        row = (
            session.query(func.avg(AirfareRecords.price))
            .filter(AirfareRecords.capture_date == capture_date)
            .scalar()
        )
    else:
        # Baseline = earliest capture_date in the DB
        subq = (
            session.query(func.min(AirfareRecords.capture_date))
            .select_from(AirfareRecords)
            .scalar()
        )
        if subq is None:
            return None
        row = (
            session.query(func.avg(AirfareRecords.price))
            .filter(AirfareRecords.capture_date == str(subq))
            .scalar()
        )

    result = row if row is not None else None
    return float(result) if result is not None and result != 0 else None


def get_prices_by_lead_time_bucket(
    session: Session,
    capture_date: Optional[str] = None,
) -> Dict[str, List[float]]:
    """Bucket prices by lead time: short (<=3), medium (<=15), long (>15)."""
    from sqlalchemy import func

    conditions = [AirfareRecords.price.isnot(None)]
    params = {}

    if capture_date is not None:
        conditions.append(AirfareRecords.capture_date == capture_date)
        params["cd"] = capture_date
    else:
        # Latest capture date
        subq = (
            session.query(func.max(AirfareRecords.capture_date))
            .select_from(AirfareRecords)
            .scalar()
        )
        if subq:
            conditions.append(AirfareRecords.capture_date == str(subq))

    query = (
        session.query(AirfareRecords.lead_time_days, AirfareRecords.price)
        .filter(and_(*conditions))
    )

    rows = query.all()

    buckets = {"short": [], "medium": [], "long": []}
    for lt, price in rows:
        if lt is not None and price is not None:
            lt = int(lt)
            if lt <= 3:
                buckets["short"].append(float(price))
            elif lt <= 15:
                buckets["medium"].append(float(price))
            else:
                buckets["long"].append(float(price))
    return buckets


def get_record_count(session: Session) -> Dict[str, int]:
    """Return total record count."""
    from sqlalchemy import func

    row = session.query(func.count(AirfareRecords.id)).scalar()
    return {"total": int(row)}


# Convenience import for get_prices_by_lead_time_bucket
from sqlalchemy import and_