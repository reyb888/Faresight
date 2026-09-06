-- Faresight — Airfare Price Index Schema for Supabase (PostgreSQL)
-- Migration 001: Core tables, indexes, and functions

-- ============================================================
-- ROUTES
-- ============================================================

CREATE TABLE IF NOT EXISTS routes (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_code         TEXT NOT NULL,
    destination_code    TEXT NOT NULL,
    route_name          TEXT NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (origin_code, destination_code)
);

-- ============================================================
-- AIRFARE RECORDS
-- ============================================================

CREATE TABLE IF NOT EXISTS airfare_records (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id            INTEGER NOT NULL REFERENCES routes (id) ON DELETE CASCADE,
    capture_date        TEXT NOT NULL,
    flight_date         TEXT NOT NULL,
    lead_time_days      INTEGER NOT NULL,
    airline_name        TEXT,
    price               REAL,
    currency            TEXT DEFAULT 'INR',
    fetched_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_airfare_records_route
    ON airfare_records (route_id, capture_date, lead_time_days);

CREATE INDEX IF NOT EXISTS idx_airfare_records_flight_date
    ON airfare_records (flight_date, lead_time_days);

-- ============================================================
-- AIRFARE INDICES
-- ============================================================

CREATE TABLE IF NOT EXISTS airfare_indices (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date                TEXT NOT NULL,
    short_term_index    REAL,
    medium_term_index   REAL,
    long_term_index     REAL,
    composite_index     REAL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (date)
);

CREATE INDEX IF NOT EXISTS idx_airfare_indices_date
    ON airfare_indices (date);

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Insert or ignore routes (mimics INSERT OR IGNORE from SQLite)
CREATE OR REPLACE FUNCTION upsert_route(
    p_origin_code TEXT,
    p_destination_code TEXT,
    p_route_name TEXT
) RETURNS VOID AS $$
BEGIN
    INSERT INTO routes (origin_code, destination_code, route_name)
    VALUES (p_origin_code, p_destination_code, p_route_name)
    ON CONFLICT (origin_code, destination_code) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- Insert or update airfare index (mimics ON CONFLICT DO UPDATE from SQLite)
CREATE OR REPLACE FUNCTION upsert_airfare_index(
    p_date TEXT,
    p_short_term_index REAL,
    p_medium_term_index REAL,
    p_long_term_index REAL,
    p_composite_index REAL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO airfare_indices (date, short_term_index, medium_term_index, long_term_index, composite_index)
    VALUES (p_date, p_short_term_index, p_medium_term_index, p_long_term_index, p_composite_index)
    ON CONFLICT (date) DO UPDATE SET
        short_term_index = EXCLUDED.short_term_index,
        medium_term_index = EXCLUDED.medium_term_index,
        long_term_index = EXCLUDED.long_term_index,
        composite_index = EXCLUDED.composite_index,
        created_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Prune records older than N days
CREATE OR REPLACE FUNCTION delete_old_records(p_older_than_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted INTEGER;
BEGIN
    DELETE FROM airfare_records
    WHERE capture_date < (CURRENT_DATE - (p_older_than_days || ' days')::INTERVAL)::TEXT;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$ LANGUAGE plpgsql;

-- Get baseline average price (earliest capture date)
CREATE OR REPLACE FUNCTION get_price_baseline(p_capture_date TEXT DEFAULT NULL)
RETURNS REAL AS $$
DECLARE
    result REAL;
BEGIN
    IF p_capture_date IS NOT NULL THEN
        SELECT AVG(price) INTO result
        FROM airfare_records
        WHERE capture_date = p_capture_date;
    ELSE
        SELECT AVG(price) INTO result
        FROM airfare_records
        WHERE capture_date = (SELECT MIN(capture_date) FROM airfare_records);
    END IF;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Get prices grouped by lead-time bucket
CREATE OR REPLACE FUNCTION get_prices_by_lead_time_bucket(p_capture_date TEXT DEFAULT NULL)
RETURNS TABLE (bucket TEXT, prices REAL[]) AS $$
BEGIN
    RETURN QUERY
    WITH base AS (
        SELECT lead_time_days, price
        FROM airfare_records
        WHERE price IS NOT NULL
          AND capture_date = COALESCE(p_capture_date, (SELECT MAX(capture_date) FROM airfare_records))
    )
    SELECT 'short'::TEXT, ARRAY_AGG(price) FROM base WHERE lead_time_days <= 3
    UNION ALL
    SELECT 'medium'::TEXT, ARRAY_AGG(price) FROM base WHERE lead_time_days > 3 AND lead_time_days <= 15
    UNION ALL
    SELECT 'long'::TEXT, ARRAY_AGG(price) FROM base WHERE lead_time_days > 15;
END;
$$ LANGUAGE plpgsql;

-- Get record count
CREATE OR REPLACE FUNCTION get_record_count()
RETURNS INTEGER AS $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM airfare_records;
    RETURN cnt;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- SEED DEFAULT ROUTES
-- ============================================================

INSERT INTO routes (origin_code, destination_code, route_name) VALUES
    ('DEL', 'BOM', 'DEL → BOM'),
    ('BLR', 'DEL', 'BLR → DEL'),
    ('MAA', 'DEL', 'MAA → DEL'),
    ('CCU', 'BOM', 'CCU → BOM'),
    ('HYD', 'DEL', 'HYD → DEL')
ON CONFLICT (origin_code, destination_code) DO NOTHING;