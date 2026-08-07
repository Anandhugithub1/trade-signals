-- =====================================================================
-- monthly_summary — one small row per (month, market)
--
-- WHY: every signals table has a 90-day TTL, so raw trades are deleted and
-- the long-run record is lost. This keeps a permanent, tiny rollup instead.
--
-- STORAGE: one row per month per market. Three markets = 36 rows/year,
-- ~100 bytes each => ~3.6 KB/year. Never needs its own TTL.
--
-- Run in Supabase -> SQL Editor. Safe to re-run.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.monthly_summary (
    month        date    NOT NULL,          -- first day of the month (UTC)
    market       text    NOT NULL,          -- 'crypto' | 'nifty' | 'stocks'

    trades       integer NOT NULL DEFAULT 0,  -- closed trades only
    wins         integer NOT NULL DEFAULT 0,
    losses       integer NOT NULL DEFAULT 0,
    expired      integer NOT NULL DEFAULT 0,  -- reached expiry unresolved
    win_rate     numeric,                     -- wins / (wins+losses), 0-100

    -- One P&L number, in that market's natural unit:
    --   crypto/stocks -> sum of per-trade % returns
    --   nifty         -> sum of rupee P&L
    pnl          numeric,
    pnl_unit     text,                        -- 'pct' | 'rs'

    best         numeric,                     -- best single trade
    worst        numeric,                     -- worst single trade

    updated_at   timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (month, market)
);

-- Dashboard reads newest-first.
CREATE INDEX IF NOT EXISTS monthly_summary_month_idx
    ON public.monthly_summary (month DESC);

-- RLS: public READ only; the backend writes with the SERVICE ROLE key.
ALTER TABLE public.monthly_summary ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read monthly_summary" ON public.monthly_summary;
CREATE POLICY "public read monthly_summary"
    ON public.monthly_summary FOR SELECT
    TO anon, authenticated USING (true);

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'monthly_summary'
ORDER BY ordinal_position;
