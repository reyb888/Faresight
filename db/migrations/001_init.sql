-- APIx initial schema
-- Run this in the Supabase SQL editor, or via `supabase db push` / your migration tool of choice.
-- Mirrors the data model in docs/DESIGN.md §2.

-- Extensions (enable from Supabase dashboard first if this errors: Database > Extensions)
create extension if not exists "timescaledb";
create extension if not exists "pgcrypto";  -- for gen_random_uuid()

-- ---------------------------------------------------------------------------
-- fare_quote: raw, immutable — one row per observed price
-- ---------------------------------------------------------------------------
create table if not exists fare_quote (
    quote_id            uuid primary key default gen_random_uuid(),
    source              text not null,                 -- e.g. 'indigo', 'makemytrip'
    source_type         text not null check (source_type in ('airline_direct', 'ota')),
    origin              text not null,                  -- IATA code, e.g. 'DEL'
    destination         text not null,                  -- IATA code, e.g. 'BOM'
    carrier             text not null,                   -- operating airline
    flight_number       text,
    fare_class          text,                            -- e.g. 'economy-saver'
    travel_date         date not null,
    advance_purchase_days int not null check (advance_purchase_days >= 0),
    observed_at         timestamptz not null default now(),
    base_fare           numeric(10, 2),
    taxes_fees          numeric(10, 2),
    total_fare          numeric(10, 2),
    currency            text not null default 'INR',
    availability_status text not null default 'available'
                         check (availability_status in ('available', 'sold_out', 'not_found')),
    raw_payload          jsonb
);

-- Convert to a TimescaleDB hypertable partitioned on observed_at
select create_hypertable('fare_quote', 'observed_at', if_not_exists => true);

create index if not exists idx_fare_quote_route
    on fare_quote (origin, destination, advance_purchase_days, observed_at desc);

-- ---------------------------------------------------------------------------
-- fare_quote_clean: derived — output of the cleaning pipeline
-- ---------------------------------------------------------------------------
create table if not exists fare_quote_clean (
    like fare_quote including defaults,
    is_outlier        boolean not null default false,
    dedup_group_id    uuid,
    cleaning_notes     text
);

select create_hypertable('fare_quote_clean', 'observed_at', if_not_exists => true);

create index if not exists idx_fare_quote_clean_route
    on fare_quote_clean (origin, destination, advance_purchase_days, observed_at desc);

-- ---------------------------------------------------------------------------
-- route_weight: DGCA-traffic-derived weights
-- ---------------------------------------------------------------------------
create table if not exists route_weight (
    id               uuid primary key default gen_random_uuid(),
    origin           text not null,
    destination      text not null,
    weight           numeric(6, 5) not null check (weight >= 0 and weight <= 1),
    effective_period date not null,     -- month this weight table was derived from
    created_at       timestamptz not null default now(),
    unique (origin, destination, effective_period)
);

-- ---------------------------------------------------------------------------
-- apix_index: computed index values
-- ---------------------------------------------------------------------------
create table if not exists apix_index (
    id              uuid primary key default gen_random_uuid(),
    index_date      date not null,
    frequency       text not null check (frequency in ('daily', 'weekly', 'monthly')),
    index_value     numeric(10, 4) not null,
    base_period_ref date not null,
    route_count     int not null default 0,
    quote_count     int not null default 0,
    created_at      timestamptz not null default now(),
    unique (index_date, frequency)
);

create index if not exists idx_apix_index_freq_date
    on apix_index (frequency, index_date desc);

-- ---------------------------------------------------------------------------
-- backtest_result: validation against DGCA published averages
-- ---------------------------------------------------------------------------
create table if not exists backtest_result (
    id             uuid primary key default gen_random_uuid(),
    period         date not null,          -- month being validated
    apix_value     numeric(10, 4) not null,
    dgca_avg_fare  numeric(10, 2) not null,
    pct_deviation  numeric(6, 3) not null,
    created_at     timestamptz not null default now(),
    unique (period)
);

-- ---------------------------------------------------------------------------
-- Continuous aggregates for fast weekly/monthly dashboard queries
-- (optional but recommended once timescaledb is confirmed enabled on your plan)
-- ---------------------------------------------------------------------------
create materialized view if not exists apix_index_weekly
with (timescaledb.continuous) as
select
    time_bucket('7 days', index_date::timestamptz) as week_start,
    avg(index_value) as avg_index_value,
    sum(quote_count) as total_quotes
from apix_index
where frequency = 'daily'
group by week_start;
