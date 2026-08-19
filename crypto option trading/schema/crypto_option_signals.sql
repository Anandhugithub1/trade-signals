-- =====================================================================
-- crypto_option_signals — signals produced by the BTC/ETH options algo
-- ("crypto option trading/src"). Replaces public.nifty_option_signals as
-- the app's Options tab data source. Mirrors the shape of public.trade_signals
-- so the Flutter app can reuse the same patterns, but adds option-specific
-- columns (side, USD stop, size).
--
-- Run ONCE in the Supabase SQL editor (Dashboard -> SQL Editor).
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.crypto_option_signals (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What to trade
    symbol            text        NOT NULL,          -- 'BTCUSDT' | 'ETHUSDT'
    side              text        NOT NULL,          -- 'CALL' (bullish) or 'PUT' (bearish)
    strike            numeric,                        -- nearest ATM strike from Deribit, if resolved
    option_expiry     date,                            -- nearest Deribit expiry
    instrument        text,                            -- ready-to-trade label, e.g. 'BTC-29AUG26-70000-C'
    size              numeric     DEFAULT 0,           -- underlying units (e.g. 0.05 BTC) sized to max_loss_usd

    -- Underlying (perp) price levels the signal is based on
    spot              numeric     NOT NULL,           -- underlying price at signal time
    entry             numeric     NOT NULL,
    stop_price        numeric     NOT NULL,           -- USD-stop mapped to an underlying price level
    target_price      numeric,                         -- ATR target level

    -- Risk / sizing
    max_loss_usd      numeric     NOT NULL,           -- USD stop budget per trade (e.g. 200)

    -- Indicators (for transparency in the app)
    rsi               numeric,
    atr               numeric,

    -- Lifecycle
    result            text        NOT NULL DEFAULT 'pending',  -- pending | win | loss | expired
    pnl_usd           numeric,                         -- realised P&L in USD once closed
    entry_confirmed   boolean     NOT NULL DEFAULT false,
    exit_reason       text,                            -- TARGET | STOP | TRAIL | TIMEOUT (null while open)

    -- Timing (24/7 market — no session square-off; expires after max_hold_bars)
    timestamp         timestamptz NOT NULL DEFAULT now(),   -- when the trade was CREATED
    expires_at        timestamptz,                          -- when it will be force-closed (timeout)
    entry_at          timestamptz,                          -- when entry was actually filled
    closed_at         timestamptz,                          -- when it actually EXITED / expired

    -- Exit detail (mirrors trade_signals.close_price / latest_price)
    exit_price        numeric,                         -- underlying price the trade exited at
    latest_price      numeric,                         -- last seen underlying price (live, while pending)

    note              text                             -- main reason for the signal
);

-- Newest-first queries by time (the app fetches last 90 days ordered desc).
CREATE INDEX IF NOT EXISTS crypto_option_signals_timestamp_idx
    ON public.crypto_option_signals (timestamp DESC);

-- check_signals.py scans open rows every run.
CREATE INDEX IF NOT EXISTS crypto_option_signals_pending_idx
    ON public.crypto_option_signals (result)
    WHERE result = 'pending';

-- ---------------------------------------------------------------------
-- Row-Level Security: public READ only. The backend writes with the
-- SERVICE ROLE key (bypasses RLS). Matches the trade_signals policy.
-- ---------------------------------------------------------------------
ALTER TABLE public.crypto_option_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read crypto_option_signals" ON public.crypto_option_signals;
CREATE POLICY "public read crypto_option_signals"
    ON public.crypto_option_signals
    FOR SELECT
    TO anon, authenticated
    USING (true);
-- (No INSERT/UPDATE/DELETE policy => anon key cannot write. Service key can.)

-- Verify
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'crypto_option_signals';
