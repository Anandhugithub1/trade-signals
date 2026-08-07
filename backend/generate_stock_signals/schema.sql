-- =====================================================================
-- stock_signals — swing signals for the top 50 US stocks
-- (backend/generate_stock_signals). Mirrors trade_signals so the app can
-- reuse the same patterns, with equity-specific fields.
--
-- Run in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Safe to re-run: every statement is IF NOT EXISTS.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.stock_signals (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    ticker           text        NOT NULL,          -- 'AAPL'
    direction        text        NOT NULL DEFAULT 'long',  -- long-only (see handler docstring)

    -- Price levels
    entry            numeric     NOT NULL,
    stop_loss        numeric     NOT NULL,
    take_profit      numeric     NOT NULL,
    latest_price     numeric,                        -- last close while open
    exit_price       numeric,                        -- fill level once closed

    -- Indicators (shown in the app for transparency)
    atr              numeric,
    adx              numeric,
    rsi              numeric,
    score            integer,                        -- net vote score
    rr_ratio         numeric,

    -- Lifecycle
    result           text        NOT NULL DEFAULT 'pending',  -- pending|win|loss|expired
    exit_reason      text,                           -- TARGET|STOP|TIME|NO_FILL
    pnl_pct          numeric,
    entry_confirmed  boolean     NOT NULL DEFAULT false,

    -- Timing
    timestamp        timestamptz NOT NULL DEFAULT now(),   -- created
    expires_at       timestamptz,                          -- max hold
    entry_at         timestamptz,                          -- fill time
    closed_at        timestamptz,                          -- actual exit

    note             text
);

CREATE INDEX IF NOT EXISTS stock_signals_timestamp_idx
    ON public.stock_signals (timestamp DESC);

CREATE INDEX IF NOT EXISTS stock_signals_pending_idx
    ON public.stock_signals (result) WHERE result = 'pending';

-- ---------------------------------------------------------------------
-- RLS: public READ only. The backend writes with the SERVICE ROLE key.
-- Matches the trade_signals / nifty_option_signals policy.
-- ---------------------------------------------------------------------
ALTER TABLE public.stock_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read stock_signals" ON public.stock_signals;
CREATE POLICY "public read stock_signals"
    ON public.stock_signals FOR SELECT
    TO anon, authenticated USING (true);

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'stock_signals'
ORDER BY ordinal_position;
