"""
Programmatic batch execution runner for APIx (Faresight).
Delegates to bypass engine (TLS fingerprint bypass + auto-selector discovery).
See scraper/bypass_engine.py for the anti-bot engine and pipeline/bypass_runner.py for the batch.
"""
from datetime import date
import os

DATABASE_URL_SYNC = os.environ.get("DATABASE_URL_SYNC", "").strip()
if not DATABASE_URL_SYNC:
    DATABASE_URL_SYNC = "postgresql://postgres.ladhxsgrucuunsdorfdf:Reyansh%40008@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"

APIX_BASE_PERIOD = os.environ.get("APIX_BASE_PERIOD", "2026-01-06")

ROUTES = [
    ("DEL", "BOM", 4800),
    ("DEL", "BLR", 5200),
    ("BOM", "BLR", 3900),
    ("DEL", "CCU", 4600),
    ("BLR", "HYD", 2900),
    ("MAA", "DEL", 5100),
]

WINDOWS = [1, 7, 15, 30, 45]
CARRIERS = [("IndiGo", "6E"), ("Air India", "AI"), ("Akasa Air", "QP"), ("SpiceJet", "SG")]


def run_live_scrape_batch(target_date: date = None) -> dict:
    """Bypass engine: TLS chrome120 + auto-selector. See pipeline/bypass_runner.py"""
    from pipeline.bypass_runner import run_bypass_batch
    return run_bypass_batch(target_date)


if __name__ == "__main__":
    res = run_live_scrape_batch()
    print("Live scrape batch result:", res)
