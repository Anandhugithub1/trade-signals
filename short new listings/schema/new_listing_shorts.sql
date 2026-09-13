-- =====================================================================
-- new_listing_shorts — signals produced by "short new listings" algo
-- ("short new listings/src"). Replaces public.stock_signals as the app's
-- 4th tab. Mirrors the shape of public.trade_signals so the app can reuse
-- the same patterns; this is a plain perp SHORT, not an option, so there's
-- no premium/strike complexity.
--
-- Run ONCE in the Supabase SQL editor (Dashboard -> SQL Editor).
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.new_listing_shorts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    symbol              text        NOT NULL,           -- e.g. 'XYZUSDT'
    listing_date        date        NOT NULL,            -- when Binance listed the perp
    days_since_listing  numeric,                          -- age at signal time (~27-33)

    -- Price levels the trade is based on (all in the underlying's price)
    entry               numeric     NOT NULL,
    stop_price          numeric     NOT NULL,            -- +30% adverse -> stopped out
    lock_price          numeric     NOT NULL,            -- -50% favourable -> profit locked

    -- Lifecycle
    result              text        NOT NULL DEFAULT 'pending',  -- pending | win | loss | expired
    pnl_pct             numeric,                          -- realised % move once closed
    exit_reason         text,                             -- STOP | LOCK | TIME (null while open)

    -- Timing (max_hold_days from strategy.py; no session close -- crypto is 24/7)
    timestamp           timestamptz NOT NULL DEFAULT now(),   -- when the trade was CREATED
    expires_at          timestamptz,                          -- when it force-closes (TIME exit)
    closed_at           timestamptz,                          -- when it actually exited

    exit_price          numeric,                          -- price the trade exited at
    latest_price        numeric,                          -- last seen price (live, while pending)

    note                text                              -- main reason for the signal
);

-- Newest-first queries by time (the app fetches last 90 days ordered desc).
CREATE INDEX IF NOT EXISTS new_listing_shorts_timestamp_idx
    ON public.new_listing_shorts (timestamp DESC);

-- check_signals.py scans open rows every run.
CREATE INDEX IF NOT EXISTS new_listing_shorts_pending_idx
    ON public.new_listing_shorts (result)
    WHERE result = 'pending';

-- Prevent re-signaling a symbol that already has a row (run_signal.py also
-- checks this before inserting, but the constraint is the real guarantee).
CREATE UNIQUE INDEX IF NOT EXISTS new_listing_shorts_symbol_unique
    ON public.new_listing_shorts (symbol);

-- ---------------------------------------------------------------------
-- Row-Level Security: public READ only. The backend writes with the
-- SERVICE ROLE key (bypasses RLS). Matches every other signals table.
-- ---------------------------------------------------------------------
ALTER TABLE public.new_listing_shorts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read new_listing_shorts" ON public.new_listing_shorts;
CREATE POLICY "public read new_listing_shorts"
    ON public.new_listing_shorts
    FOR SELECT
    TO anon, authenticated
    USING (true);

-- Verify
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'new_listing_shorts';
