"""
Background Scraper Task - Runs in background, errors buried, results stored in DB
"""
import asyncio
import logging
import os
from datetime import date, timedelta
from typing import List, Dict, Any
from fastapi import BackgroundTasks

from database import SessionLocal, init_db
from flight_scraper import run_scraper_pipeline
from database import insert_airfare_records, upsert_airfare_index, get_record_count
from index_engine import compute_index

logger = logging.getLogger(__name__)

class ScraperTask:
    """Background scraper task - runs independently, errors buried"""
    
    def __init__(self):
        self.running = False
        self.last_run = None
        self.last_error = None
        self.last_result_count = 0
    
    async def run_scraper(self) -> dict:
        """Main scraper entry point - runs in background"""
        from flight_scraper import run_scraper_pipeline
        from database import SessionLocal, insert_airfare_records, get_record_count
        from index_engine import compute_index
        
        logger.info("Starting background scraper task")
        
        # Get SerpApi keys from env
        serpapi_keys = [
            os.getenv("SERP_API_KEY_1"),
            os.getenv("SERP_API_KEY_2"),
            os.getenv("SERP_API_KEY_3"),
            os.getenv("SERP_API_KEY_4"),
            os.getenv("SERP_API_KEY_5"),
        ]
        keys = [k for k in [os.getenv(f"SERP_API_KEY_{i}") for i in range(1, 6)] if k]
        
        if not keys:
            return {"status": "skipped", "reason": "No SerpApi keys configured"}
        
        routes = [
            ("DEL", "BOM"),
            ("BLR", "DEL"),
            ("MAA", "DEL"),
            ("CCU", "BOM"),
            ("HYD", "DEL"),
        ]
        
        lead_times = [1, 3, 5, 7, 15, 30, 45]
        
        try:
            # Import here to avoid circular imports
            from flight_scraper import run_scraper_pipeline
            from database import SessionLocal, insert_airfare_records
            from index_engine import compute_index
            
            # Run scraper
            results = await run_scraper_pipeline(
                serpapi_keys=[k for k in [
                    os.getenv("SERP_API_KEY_1"),
                    os.getenv("SERP_API_KEY_2"),
                    os.getenv("SERP_API_KEY_3"),
                    os.getenv("SERP_API_KEY_4"),
                    os.getenv("SERP_API_KEY_5"),
                ] if k],
                max_concurrent=2
            )
            
            # Store results in DB
            if results:
                session = None
                try:
                    from database import SessionLocal, insert_airfare_records
                    session = SessionLocal()
                    inserted = insert_airfare_records(session, results)
                    session.commit()
                    logger.info(f"Inserted {inserted} new fare records")
                except Exception as e:
                    if session:
                        session.rollback()
                    logger.error(f"DB insert failed: {e}")
                finally:
                    if session:
                        session.close()
            
            # Recompute index
            try:
                from index_engine import compute_index
                compute_index(force_recompute=True)
            except Exception as e:
                logger.warning(f"Index recompute failed: {e}")
            
            # Get final count
            from database import SessionLocal, get_record_count
            session = None
            try:
                session = SessionLocal()
                count = get_record_count(None)
                total = count.get("total", 0) if count else 0
            finally:
                if 'session' in locals():
                    session.close()
            
            return {
                "status": "success",
                "records_fetched": len(results) if 'results' in locals() else 0,
                "total_records": total,
                "message": "Scraper completed successfully"
            }
            
        except Exception as e:
            logger.error(f"Scraper task failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": "Scraper failed but errors buried"
            }


# Singleton instance
scraper_task = BackgroundScraper()

# Background task function for FastAPI
async def run_scraper_background():
    """Background task entry point for FastAPI"""
    task = ScraperTask()
    result = await task.run_scraper()
    logger.info(f"Scraper task completed: {result}")
    return result


# FastAPI background task wrapper
async def trigger_scraper(background_tasks: BackgroundTasks):
    """FastAPI background task trigger"""
    background_tasks.add_task(run_scraper_background)
    return {"status": "scheduled", "message": "Scraper queued in background"}