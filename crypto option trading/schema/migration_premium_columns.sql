-- =====================================================================
-- Migration — add real option premium columns to crypto_option_signals
--
-- Run in the Supabase SQL Editor. Safe to re-run (all IF NOT EXISTS).
--
-- WHY: the signal named a contract (instrument/strike) but never recorded
-- what it actually COSTS, so the app could only tell the user to "check
-- Deribit for the live premium" — not an actionable signal. These columns
-- carry the real USD premium at signal time.
--
-- Note on denomination: Deribit quotes BTC/ETH options in units of the
-- UNDERLYING (a BTC put at 0.0117 costs 0.0117 BTC ≈ $950 at 81k spot),
-- not in dollars. `premium_usd` below is already converted to USD by
-- live_signal.get_deribit_atm_context(); do not store the raw coin figure
-- in it.
-- =====================================================================

ALTER TABLE public.crypto_option_signals
    ADD COLUMN IF NOT EXISTS premium_usd      numeric,  -- premium per 1 contract, USD
    ADD COLUMN IF NOT EXISTS premium_cost_usd numeric,  -- premium_usd * size = total outlay
    ADD COLUMN IF NOT EXISTS mark_iv          numeric;  -- Deribit mark IV %, at signal time

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'crypto_option_signals'
  AND column_name IN ('premium_usd', 'premium_cost_usd', 'mark_iv')
ORDER BY column_name;
