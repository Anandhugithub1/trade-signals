-- =====================================================================
-- executed_orders — tracks which trade_signals rows have had a real (or
-- dry-run) CoinDCX order attempt, so execute_signals/handler.py never
-- double-executes the same signal on a re-run.
--
-- Run in Supabase -> SQL Editor before running execute_signals/handler.py
-- for the first time.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.executed_orders (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- trade_signals.id is `text` (application-generated UUID strings, not
    -- a native Postgres uuid column) — matched here, not `uuid`, or the
    -- foreign key fails with "incompatible types: uuid and text".
    signal_id       text NOT NULL REFERENCES public.trade_signals(id),
    pair            text NOT NULL,
    direction       text NOT NULL,
    dry_run         boolean NOT NULL DEFAULT true,
    order_response  jsonb,
    tp_sl_response  jsonb,
    executed_at     timestamptz NOT NULL DEFAULT now()
);

-- One execution attempt per signal — enforced at the DB level too, not
-- just the application-side already_executed() check, so a race between
-- two concurrent runs can't double-fire an order.
CREATE UNIQUE INDEX IF NOT EXISTS executed_orders_signal_id_idx
    ON public.executed_orders (signal_id);

CREATE INDEX IF NOT EXISTS executed_orders_pair_idx
    ON public.executed_orders (pair, executed_at);
