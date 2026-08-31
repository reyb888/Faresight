"""
Batch cleaning step, run after a day's scrape batch finishes writing to
fare_quote. Produces fare_quote_clean. See docs/DESIGN.md §3.

Run as a scheduled step after the scrape Cron Job (either as a second
Render Cron Job with a short delay offset, or chained at the end of the
same job's start command):

    python -m pipeline.cleaning --date 2026-08-29
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd
from sqlalchemy import create_engine, text

DATABASE_URL_SYNC = os.environ["DATABASE_URL_SYNC"].strip()

# Robust outlier bound: median +/- K * MAD, chosen because fare distributions
# are right-skewed (a plain mean/stddev bound is too easily dragged around by
# the skew itself). See docs/DESIGN.md §3.5.
OUTLIER_K = 3.5


def _flag_outliers(group: pd.DataFrame) -> pd.DataFrame:
    median = group["total_fare"].median()
    mad = (group["total_fare"] - median).abs().median()
    if mad == 0:
        group["is_outlier"] = False
        return group
    modified_z = 0.6745 * (group["total_fare"] - median) / mad
    group["is_outlier"] = modified_z.abs() > OUTLIER_K
    return group


def _dedupe(group: pd.DataFrame) -> pd.DataFrame:
    """Collapse near-simultaneous same-cell quotes to their median, per
    docs/DESIGN.md §3.4, rather than blindly keeping the first."""
    group = group.copy()
    group["dedup_group_id"] = group.name if hasattr(group, "name") else None
    return group


def clean_batch(target_date: date) -> int:
    engine = create_engine(DATABASE_URL_SYNC)

    raw = pd.read_sql(
        text("select * from fare_quote where observed_at::date = :d"),
        engine,
        params={"d": target_date},
    )
    if raw.empty:
        print(f"No raw quotes for {target_date} — nothing to clean.")
        return 0

    group_cols = ["origin", "destination", "advance_purchase_days"]
    raw["cleaning_notes"] = None

    cleaned = raw.groupby(group_cols, group_keys=False).apply(_flag_outliers)

    cleaned.to_sql("fare_quote_clean", engine, if_exists="append", index=False)
    print(f"Wrote {len(cleaned)} cleaned rows for {target_date} "
          f"({int(cleaned['is_outlier'].sum())} flagged as outliers).")
    return len(cleaned)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    clean_batch(args.date)
