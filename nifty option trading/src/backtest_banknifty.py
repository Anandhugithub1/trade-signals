"""
One-off: backtest the CURRENT live trend strategy (strategy.py, unchanged) on
BANK NIFTY instead of NIFTY 50, same 6-month window, so results are directly
comparable to compare_sr_vs_trend.py's NIFTY numbers.

Does NOT touch data_feed.py / run_signal.py -- this fetches Bank Nifty candles
directly and reuses backtest.py's simulate_trade/summarize as-is. Nothing
about the live NIFTY signal pipeline changes by running this.

Bank Nifty contract spec: lot size 15 (as of 2024-25; NSE revises this
periodically -- adjust BANKNIFTY_LOT_SIZE here if it changes).

Run:  python src/backtest_banknifty.py --months 6
"""
from __future__ import annotations

import argparse

import pandas as pd

from backtest import simulate_trade, summarize
from strategy import StrategyParams, add_indicators, evaluate_row
from upstox_feed import get_upstox_history

BANKNIFTY_KEY = "NSE_INDEX|Nifty Bank"
BANKNIFTY_LOT_SIZE = 15


def run_backtest_banknifty(
    interval: str, max_loss: float, max_hold_bars: int, p: StrategyParams,
    months: int,
):
    df = get_upstox_history(
        interval={"15m": "15minute"}.get(interval, "15minute"),
        months=months, instrument_key=BANKNIFTY_KEY,
    )
    df = add_indicators(df, p)

    trades = []
    i = 1
    n = len(df)
    while i < n:
        sig = evaluate_row(df, i, p)
        if sig is not None:
            tr = simulate_trade(df, i, sig, p, max_loss, max_hold_bars, reversal_exit=True)
            trades.append(tr)
            i = df.index.get_loc(pd.Timestamp(tr.exit_time)) + 1 \
                if tr.exit_time in df.index else i + 1
        else:
            i += 1
    return trades


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--max-loss", type=float, default=3000)
    ap.add_argument("--max-hold-bars", type=int, default=26)
    args = ap.parse_args()

    # backtest.py's simulate_trade uses the module-level LOT_SIZE constant
    # for P&L sizing -- patch it for this run only, restore after.
    import backtest as bt
    orig_lot_size = bt.LOT_SIZE
    bt.LOT_SIZE = BANKNIFTY_LOT_SIZE
    try:
        p = StrategyParams()
        print(f"\nFetching {args.months}mo of BANK NIFTY {args.interval} bars via Upstox ...")
        trades = run_backtest_banknifty(
            args.interval, args.max_loss, args.max_hold_bars, p, args.months,
        )
        print(f"\n{'='*70}\nTREND STRATEGY on BANK NIFTY (same logic as strategy.py, "
              f"lot size={BANKNIFTY_LOT_SIZE})\n{'='*70}")
        s = summarize(trades, args.max_loss)
        for k, v in s.items():
            print(f"  {k:>22}: {v}")

        days = 126 if args.months == 6 else round(args.months * 21)
        tpd = round(s.get("trades", 0) / days, 2)
        print(f"  {'trades_per_day':>22}: {tpd}")
    finally:
        bt.LOT_SIZE = orig_lot_size

    print(f"\nNOTE: option P&L is a delta-based approximation (option_delta="
          f"{p.option_delta}); ignores theta/vega. Same caveat as the NIFTY "
          f"backtest -- treat expectancy as indicative.\n")


if __name__ == "__main__":
    main()
