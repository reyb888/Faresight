"""
Item pipeline stage: write validated raw items into fare_quote (Supabase).

Writes to the RAW table only — cleaning (outlier flagging, dedup, fare
decomposition refinement) happens as a separate batch step in
pipeline/cleaning.py, run after a full scrape batch completes. Keeping
raw writes and cleaning as separate stages means a cleaning-rule bug never
touches the underlying evidence. See docs/DESIGN.md §2.2.
"""
import os

import psycopg2
import psycopg2.extras
import structlog

logger = structlog.get_logger()


class SupabaseLoaderPipeline:
    def open_spider(self, spider):
        # psycopg2 (sync) is used here deliberately: Scrapy's item pipeline
        # runs in the Twisted reactor thread, and a simple synchronous
        # insert-per-item is easier to reason about than bridging into
        # asyncio for this one write path. The async engine (api/db.py,
        # index/index_engine.py) is used everywhere else.
        self.conn = psycopg2.connect(os.environ["DATABASE_URL_SYNC"])
        self.conn.autocommit = True

    def close_spider(self, spider):
        self.conn.close()

    def process_item(self, item, spider):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into fare_quote
                    (source, source_type, origin, destination, carrier, flight_number,
                     fare_class, travel_date, advance_purchase_days, observed_at,
                     base_fare, taxes_fees, total_fare, currency, availability_status,
                     raw_payload)
                values
                    (%(source)s, %(source_type)s, %(origin)s, %(destination)s, %(carrier)s,
                     %(flight_number)s, %(fare_class)s, %(travel_date)s,
                     %(advance_purchase_days)s, %(observed_at)s, %(base_fare)s,
                     %(taxes_fees)s, %(total_fare)s, %(currency)s, %(availability_status)s,
                     %(raw_payload)s)
                """,
                item,
            )
        return item
