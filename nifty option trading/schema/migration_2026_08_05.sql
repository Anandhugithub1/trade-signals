-- =====================================================================
-- Migration — 2026-08-05
--
-- Run this in the Supabase SQL Editor:
--   Dashboard -> SQL Editor -> New query -> paste -> Run
--
-- Safe to re-run: every statement is IF NOT EXISTS or an idempotent
-- UPDATE/DELETE. Adding nullable columns does not rewrite the table and
-- does not touch existing data.
--
-- STEP 3 DELETES ROWS. Read the comment there before running it; if you
-- would rather keep the history, run only steps 1 and 2.
-- =====================================================================


-- ---------------------------------------------------------------------
-- STEP 1 — columns for the exact option contract
--
-- Signals used to be written with strike/premium NULL, because NSE blocks
-- its option-chain endpoint from GitHub Actions IPs. The app then showed
-- "NIFTY CE (ATM)" — a direction with no contract to actually buy. The
-- strike grid is deterministic (50-pt steps), so the backend now derives
-- the strike from spot and records a broker-ready label here.
-- ---------------------------------------------------------------------
ALTER TABLE public.nifty_option_signals
    ADD COLUMN IF NOT EXISTS option_expiry date,   -- weekly expiry (Tuesday)
    ADD COLUMN IF NOT EXISTS instrument    text;   -- 'NIFTY 24400 CE 11 Aug'


-- ---------------------------------------------------------------------
-- STEP 2 — exit / lifecycle tracking columns
--
-- Included again for safety: if you already ran the earlier migration,
-- these are no-ops. Without them check_nifty_signals.py cannot close a
-- trade out, so every signal stays 'pending' forever and the app's
-- win-rate and P&L cards are computed over an empty set.
-- ---------------------------------------------------------------------
ALTER TABLE public.nifty_option_signals
    ADD COLUMN IF NOT EXISTS exit_reason   text,          -- TARGET|STOP|REVERSAL|EOD
    ADD COLUMN IF NOT EXISTS entry_at      timestamptz,   -- when entry filled
    ADD COLUMN IF NOT EXISTS closed_at     timestamptz,   -- when it actually exited
    ADD COLUMN IF NOT EXISTS exit_index    numeric,       -- index level at exit
    ADD COLUMN IF NOT EXISTS latest_index  numeric;       -- last seen index (while open)

-- check_nifty_signals scans open rows every 15 minutes.
CREATE INDEX IF NOT EXISTS nifty_option_signals_pending_idx
    ON public.nifty_option_signals (result)
    WHERE result = 'pending';


-- ---------------------------------------------------------------------
-- STEP 3 — remove the 8 legacy rows  ** THIS DELETES DATA **
--
-- Every row written before today is unusable, for one of two reasons:
--
--   a) Created after the 15:30 close by a delayed CI run, so expires_at
--      landed BEFORE timestamp — dead on arrival, never tradeable.
--      (6 rows, all result='expired', entry_confirmed=false.)
--
--   b) Closed by the first version of check_nifty_signals.py, which did
--      not bound its scan to the trading session and so booked exits from
--      LATER sessions. Both recorded "wins" are inflated this way — one
--      logged +Rs.7,841 on a Monday gap when its honest same-day result
--      was +Rs.351.
--
-- Keeping them means the app reports a fabricated win rate and P&L. The
-- deletes below are narrow: they only remove rows matching those exact
-- defects, not the whole table.
--
-- To inspect before deleting, run this first:
--     SELECT id, timestamp, expires_at, closed_at, result, pnl_rs
--     FROM public.nifty_option_signals ORDER BY timestamp DESC;
-- ---------------------------------------------------------------------

-- (a) born already expired
DELETE FROM public.nifty_option_signals
WHERE expires_at IS NOT NULL
  AND expires_at <= timestamp;

-- (b) closed outside their own session (multi-day scan bug)
DELETE FROM public.nifty_option_signals
WHERE closed_at IS NOT NULL
  AND expires_at IS NOT NULL
  AND closed_at > expires_at;


-- ---------------------------------------------------------------------
-- VERIFY
--   First query : expect 7 rows (the 7 columns added above).
--   Second query: expect rows_left = 0, born_expired = 0, closed_late = 0.
--
-- Yes, ZERO rows left — a dry run against your live table matched all 8
-- existing rows (6 born-expired + 2 closed-late). Every signal recorded so
-- far is defective, so the table starts clean and refills from the next
-- market-hours run. Nothing valid is being discarded.
-- ---------------------------------------------------------------------
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'nifty_option_signals'
  AND column_name IN ('option_expiry', 'instrument', 'exit_reason',
                      'entry_at', 'closed_at', 'exit_index', 'latest_index')
ORDER BY column_name;

SELECT
    count(*)                                                       AS rows_left,
    count(*) FILTER (WHERE expires_at <= timestamp)                AS born_expired,
    count(*) FILTER (WHERE closed_at  >  expires_at)               AS closed_late
FROM public.nifty_option_signals;
