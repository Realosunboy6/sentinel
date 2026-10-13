# Sentinel — database design (v2: no accounts)

**Architecture decision (2026-10-12, user):** nobody logs in. There are no accounts,
no brokerage connections, and no user money in the system. Visitors enter tickers +
weights (the Portfolio Visualizer pattern) and get an analysis. That deletes the entire
user-data half of v1 — and with it the auth, password, and privacy burden.

## What the database actually is now

```
securities 1───* price_history          <- market data (the core asset)
securities 1───* corporate_actions
analyses (anonymous) ─── input_hash ─── analysis_results (cache)
presets (named example portfolios)
```

### securities (reference data)
One row per tradable instrument: symbol, name, asset_type, exchange, currency.

### price_history
Daily OHLCV + adjusted close per security, refreshed nightly. This table is the product's
engine room: analyses read from here, never from Yahoo at request time — fast, consistent,
and immune to a data-source outage mid-day.

### corporate_actions
Splits and dividends. Needed to keep long price histories honest (an unadjusted 10-year
series is wrong after every split).

### analyses (anonymous, optional storage)
One row per analysis a visitor chooses to share: a short random `slug` for the URL,
the inputs (symbols, weights, settings) as JSONB, and the engine version. **No identity
column exists** — a row cannot be tied to a person because nothing about a person is ever
collected. If we skip storing entirely, links can encode the weights in the URL instead
(see open questions).

### analysis_results (cache)
Keyed by (input_hash, data_asof): the computed metrics for one exact set of inputs
against one exact vintage of market data. Same weights + same data date = same result,
served instantly. Recompute only when the nightly price refresh lands.

### presets
Named example portfolios (60/40, K5 sample) shown on the analyzer page. Small enough
to live as rows here or as app config — your call.

## Key decisions (flagged for you)

1. **No user tables at all.** The strongest privacy property is structural: there is
   nowhere in this schema to put a person's money or identity.
2. **Market data is a cache, not a passthrough.** One nightly job refreshes
   price_history; requests never call the data source. (Same pattern as the pilot's
   RiskLens cron.)
3. **Analyses keyed by content hash.** Identical inputs dedupe to one row; the slug
   is just a friendly handle on it.
4. **Results are a pure function of (inputs, data vintage).** That invariant is what
   makes the cache safe — and it's the same discipline portlab already follows.
5. **NUMERIC for prices/weights, DATE for market days.** No floats anywhere near money
   math; market days are dates, not timestamps.

## Open questions

- Shareable links: store `analyses` rows, or encode weights in the URL (fully stateless,
  zero storage, but URLs get long and results can't be cached by slug)?
- Price depth: how far back do we cache — 10 years, 20, or max available (PV reaches 1985)?
- Data source: Yahoo only to start, or design the refresh job source-pluggable?
- Presets in the DB or in app config?
