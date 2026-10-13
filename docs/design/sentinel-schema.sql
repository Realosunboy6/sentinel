-- Sentinel schema v2 (PostgreSQL 15+) — NO ACCOUNTS architecture.
-- There is deliberately no users/portfolios/fills table: visitors enter
-- tickers + weights and get an analysis; nothing about their money or
-- identity is ever stored. Companion to sentinel-db-design.md.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- market data (refreshed nightly; requests never hit the source) ----------

CREATE TABLE securities (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol     TEXT NOT NULL,
    exchange   TEXT NOT NULL DEFAULT '',
    name       TEXT,
    asset_type TEXT NOT NULL DEFAULT 'stock',   -- stock | etf | fund
    currency   CHAR(3) NOT NULL DEFAULT 'USD',
    UNIQUE (symbol, exchange)
);

CREATE TABLE price_history (
    security_id UUID NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    open        NUMERIC(18,4), high NUMERIC(18,4),
    low         NUMERIC(18,4), close NUMERIC(18,4) NOT NULL,
    adj_close   NUMERIC(18,4) NOT NULL,
    volume      BIGINT,
    PRIMARY KEY (security_id, date)
);

CREATE TABLE corporate_actions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    ex_date     DATE NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('SPLIT','STOCK_DIVIDEND','CASH_DIVIDEND')),
    ratio       NUMERIC(18,6) NOT NULL,   -- new-per-old shares, or per-share cash
    UNIQUE (security_id, ex_date, action_type)
);

-- ---------- anonymous analyses (shareable links; no identity columns exist) ----------

-- inputs: {"holdings":[{"symbol":"MCK","weight":0.2998},...],
--          "settings":{"start":"2021-01-01","alpha":0.05}, ...}
CREATE TABLE analyses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          TEXT UNIQUE NOT NULL,        -- e.g. '7f3ka2' in /a/7f3ka2
    input_hash    TEXT NOT NULL,               -- sha256 of canonical inputs JSON
    inputs        JSONB NOT NULL,
    engine_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON analyses (input_hash);

-- Results are a pure function of (inputs, data vintage): cache them.
CREATE TABLE analysis_results (
    input_hash  TEXT NOT NULL,
    data_asof   DATE NOT NULL,               -- latest price_history date used
    metrics     JSONB NOT NULL,              -- return, vol, sharpe, var_95, es_95, ...
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (input_hash, data_asof)
);

-- ---------- presets (also fine as app config; table keeps them editable) ----------

CREATE TABLE presets (
    slug    TEXT PRIMARY KEY,                -- '60-40', 'k5-sample'
    name    TEXT NOT NULL,
    inputs  JSONB NOT NULL
);
