-- =====================================================================
-- mean_reversion joins donchian as the two live engines on trade_signals
--
-- No schema change needed — `strategy` is already a free-text column
-- with no CHECK constraint (see migration_strategy_tag.sql), so the new
-- 'mean_reversion' value just starts appearing once handler.py inserts
-- it. This migration exists only to document the addition and extend
-- the scoreboard query, same convention as the original migration.
--
-- UPDATE: the original third engine, 'legacy' (vote-based momentum,
-- 1h bars), has since been RETIRED — its own backtest showed a thin,
-- largely fee-consumed edge (35.2% win rate, PF 1.09) and it was
-- removed from backend/generate_signals/handler.py. All of its
-- historical trade_signals rows were exported to CSV
-- (test_scripts/_exports/) and then DELETED from this table. Only
-- 'donchian' and 'mean_reversion' write new rows now.
--
-- Two engines run side by side so live results can decide between them:
--   'donchian'       — 55-bar channel breakout (4h bars)
--   'mean_reversion' — range-fade: RSI+Bollinger entry, ADX<20 gate
--                      (ranging, not trending), target the mid-band
--
-- Backtested, 36 months, 15 pairs (see mean_reversion.py's own HONEST
-- LIMITS section for the full frequency-vs-quality tradeoff that was
-- tested before picking these numbers):
--   donchian        ~30.0% win, PF 1.27  (3R target, wins less often)
--   mean_reversion  ~52.5% win, PF 1.11  (~1:1 target, wins more often,
--                                         ~73 trades/yr across 15 pairs)
--
-- Run in Supabase -> SQL Editor. Safe to re-run.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Verify: engine scoreboard. Extends the original two-engine query
-- from migration_strategy_tag.sql; will show zero rows for 'legacy'
-- now that its history has been deleted.
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
