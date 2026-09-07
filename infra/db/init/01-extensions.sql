-- Extensions required by AirWatch.
-- Runs once on first container start, before the application migrations.

-- Spatial types, indexes and ST_* functions. The repository layer is the only
-- layer permitted to call these.
CREATE EXTENSION IF NOT EXISTS postgis;

-- Hypertables for the measurement and weather time-series.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- gen_random_uuid() for primary keys.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Trigram index support for station and source-registry name lookups.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
