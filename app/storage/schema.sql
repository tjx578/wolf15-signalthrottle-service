-- Wolf15 SignalThrottle Service — Database Schema

CREATE SCHEMA IF NOT EXISTS signalthrottle;

CREATE TABLE IF NOT EXISTS signalthrottle.signal_events (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'SIGNAL_THROTTLE',
    timestamp_utc TIMESTAMPTZ NOT NULL,
    timestamp_wita TEXT,
    chart_time TEXT,
    raw_message TEXT NOT NULL,
    source_service TEXT DEFAULT 'wolf15-engine',
    event_hash TEXT,
    meta JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_events_symbol_time
ON signalthrottle.signal_events(symbol, timestamp_utc);

CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_events_event_hash
ON signalthrottle.signal_events(event_hash);

-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS signalthrottle.pressure_blocks (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,

    start_utc TIMESTAMPTZ NOT NULL,
    end_utc TIMESTAMPTZ NOT NULL,
    start_wita TEXT,
    end_wita TEXT,
    chart_start_time TEXT,
    chart_end_time TEXT,

    duration_minutes NUMERIC NOT NULL,
    event_count INT NOT NULL,
    density_per_minute NUMERIC NOT NULL,
    avg_gap_seconds NUMERIC,
    max_gap_seconds NUMERIC,

    pressure_grade TEXT NOT NULL,
    pressure_status TEXT,
    block_relation TEXT,
    previous_block_id BIGINT,
    finalize_mode TEXT,

    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pressure_blocks_symbol_time
ON signalthrottle.pressure_blocks(symbol, end_utc DESC);

CREATE INDEX IF NOT EXISTS idx_pressure_blocks_active
ON signalthrottle.pressure_blocks(is_active) WHERE is_active = TRUE;

-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS signalthrottle.market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    block_id BIGINT REFERENCES signalthrottle.pressure_blocks(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,

    signal_start_utc TIMESTAMPTZ,
    signal_end_utc TIMESTAMPTZ,

    price_at_start NUMERIC,
    price_at_end NUMERIC,
    spread_points NUMERIC,

    d1_bias TEXT,
    h4_structure TEXT,
    h1_phase TEXT,
    m15_phase TEXT,
    chart_bias TEXT,
    chart_phase TEXT,

    support_zone TEXT,
    resistance_zone TEXT,
    key_level TEXT,

    raw_ohlc JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_st_market_snapshots_symbol_time
ON signalthrottle.market_snapshots(symbol, created_at DESC);

-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS signalthrottle.trade_plans (
    id BIGSERIAL PRIMARY KEY,
    block_id BIGINT REFERENCES signalthrottle.pressure_blocks(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,

    pressure_grade TEXT NOT NULL,
    execution_grade TEXT NOT NULL,
    execution_side TEXT,
    action TEXT NOT NULL,

    entry_zone TEXT,
    breakout_level TEXT,
    reclaim_level TEXT,
    invalidation TEXT,
    tp1 TEXT,
    tp2 TEXT,
    tp3 TEXT,

    message TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_st_trade_plans_symbol_time
ON signalthrottle.trade_plans(symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_st_trade_plans_grade_time
ON signalthrottle.trade_plans(execution_grade, created_at DESC);

-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS signalthrottle.signal_outcomes (
    id BIGSERIAL PRIMARY KEY,
    trade_plan_id BIGINT REFERENCES signalthrottle.trade_plans(id) ON DELETE CASCADE,

    price_after_15m NUMERIC,
    price_after_30m NUMERIC,
    price_after_60m NUMERIC,

    mfe_15m NUMERIC,
    mae_15m NUMERIC,
    mfe_30m NUMERIC,
    mae_30m NUMERIC,
    mfe_60m NUMERIC,
    mae_60m NUMERIC,

    result_label TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
