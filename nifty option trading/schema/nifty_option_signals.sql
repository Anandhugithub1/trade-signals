-- =====================================================================
-- nifty_option_signals — signals produced by the NIFTY 50 options algo
-- (nifty option trading/src). Mirrors the shape of public.trade_signals
-- so the Flutter app can reuse the same patterns, but adds option-specific
-- columns (strike, option type, premium, lots, rupee stop).
--
-- Run ONCE in the Supabase SQL editor (Dashboard -> SQL Editor), OR apply
-- it programmatically with:  python src/apply_schema.py
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.nifty_option_signals (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What to trade
    side              text        NOT NULL,          -- 'CE' (bullish) or 'PE' (bearish)
    strike            integer,                        -- e.g. 24000 (null until chain resolves)
    strike_style      text        DEFAULT 'ATM',      -- 'ITM' | 'ATM' | 'OTM'
    premium           numeric,                        -- entry premium per unit (LTP)
    lots              integer     DEFAULT 1,

    -- Index levels the signal is based on (NIFTY spot)
    spot              numeric     NOT NULL,           -- index level at signal time
    index_entry       numeric     NOT NULL,
    index_stop        numeric     NOT NULL,           -- rupee-stop mapped to an index level
    index_target      numeric,                        -- reversal-exit has no fixed target -> null

    -- Risk / sizing
    max_loss_rs       numeric     NOT NULL,           -- rupee stop budget per trade (e.g. 3000)

    -- Indicators (for transparency in the app)
    rsi               numeric,
    atr               numeric,

    -- Lifecycle
    result            text        NOT NULL DEFAULT 'pending',  -- pending | win | loss | expired
    pnl_rs            numeric,                         -- realised P&L in rupees once closed
    entry_confirmed   boolean     NOT NULL DEFAULT false,

    -- Timing (intraday: expires end of the same trading day)
    timestamp         timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz,

    note              text                             -- main reason for the signal
);

-- Newest-first queries by time (the app fetches last 90 days ordered desc).
CREATE INDEX IF NOT EXISTS nifty_option_signals_timestamp_idx
    ON public.nifty_option_signals (timestamp DESC);

-- ---------------------------------------------------------------------
-- Row-Level Security: public READ only. The backend writes with the
-- SERVICE ROLE key (bypasses RLS). Matches the trade_signals policy.
-- ---------------------------------------------------------------------
ALTER TABLE public.nifty_option_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read nifty_option_signals" ON public.nifty_option_signals;
CREATE POLICY "public read nifty_option_signals"
    ON public.nifty_option_signals
    FOR SELECT
    TO anon, authenticated
    USING (true);
-- (No INSERT/UPDATE/DELETE policy => anon key cannot write. Service key can.)

-- Verify
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'nifty_option_signals';
