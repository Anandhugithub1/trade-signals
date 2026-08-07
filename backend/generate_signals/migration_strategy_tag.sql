-- =====================================================================
-- Add the `strategy` tag to trade_signals
--
-- Two crypto engines now run side by side so live results can decide
-- between them:
--   'legacy'   — the original vote-based momentum model (1h bars)
--   'donchian' — 55-bar channel breakout (4h bars)
--
-- Backtested over 20 months of real 4h bars, 10 pairs, after 6bp fees:
--   legacy    1384 trades, 35.2% win, PF 1.09, +81.6R
--   donchian   783 trades, 30.0% win, PF 1.27, +151.1R
-- Donchian wins because of the ARITHMETIC, not better prediction: a 3R
-- target only needs a 25% win rate to break even, so 30% leaves a real
-- margin. The legacy 2R target needs 33.3% and only achieved 35.2% —
-- a 1.9-point margin that fees consumed entirely.
--
-- Run in Supabase -> SQL Editor. Safe to re-run.
-- =====================================================================

ALTER TABLE public.trade_signals
    ADD COLUMN IF NOT EXISTS strategy text NOT NULL DEFAULT 'legacy';

-- Existing rows predate the split and all came from the vote engine.
UPDATE public.trade_signals SET strategy = 'legacy' WHERE strategy IS NULL;

-- Per-engine performance queries hit this constantly.
CREATE INDEX IF NOT EXISTS trade_signals_strategy_idx
    ON public.trade_signals (strategy, result);

-- ---------------------------------------------------------------------
-- Verify: engine-by-engine scoreboard. This is the query that will
-- eventually settle which strategy to keep.
-- ---------------------------------------------------------------------
SELECT
    strategy,
    count(*)                                        AS total,
    count(*) FILTER (WHERE result = 'win')          AS wins,
    count(*) FILTER (WHERE result = 'loss')         AS losses,
    count(*) FILTER (WHERE result = 'pending')      AS open,
    round(100.0 * count(*) FILTER (WHERE result = 'win')
          / NULLIF(count(*) FILTER (WHERE result IN ('win','loss')), 0), 1)
                                                    AS win_rate
FROM public.trade_signals
GROUP BY strategy
ORDER BY strategy;
