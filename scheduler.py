import argparse
import logging
import os
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from fetcher import fetch_all_routes
from index_engine import compute_index
from database import init_db

logger = logging.getLogger(__name__)
FETCH_INTERVAL_HOURS = int(os.environ.get("FETCH_INTERVAL_HOURS", "24"))

def scheduled_job():
    logger.info("Scheduled fetch triggered")
    try:
        result = fetch_all_routes()
        logger.info("Fetch result: %s", result)
    except Exception as e:
        logger.exception("Fetch job failed: %s", e)
    try:
        idx = compute_index(force_recompute=True)
        logger.info("Index computed: %s", idx)
    except Exception as e:
        logger.exception("Index job failed: %s", e)

def create_scheduler():
    sched = BlockingScheduler()
    sched.add_job(
        scheduled_job,
        trigger=IntervalTrigger(hours=FETCH_INTERVAL_HOURS),
        id="daily_fare_fetch",
        name="Daily airfare fetch and index compute",
        replace_existing=True,
    )
    return sched

def main():
    parser = argparse.ArgumentParser(
        description="Faresight background scheduler for airfare price index"
    )
    parser.add_argument("--run-once", action="store_true",
        help="Run fetch and index immediately once, then exit")
    parser.add_argument("--interval", type=int, default=FETCH_INTERVAL_HOURS,
        help=f"Interval hours between fetches (default: {FETCH_INTERVAL_HOURS})")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()

    if args.run_once:
        logger.info("Running --run-once mode")
        scheduled_job()
        logger.info("--run-once complete")
        return

    logger.info("Starting scheduler -- fetch every %d hour(s). Ctrl+C to stop.", args.interval)
    sched = create_scheduler()
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        sched.shutdown()

if __name__ == "__main__":
    main()