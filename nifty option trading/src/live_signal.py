"""
Live signal generator.

Pulls recent NIFTY index history (yfinance), computes the latest signal, and
enriches it with the REAL ATM option premium + PCR from NSE's live option chain
so you get an actionable "buy this option" line. Also sizes the position to your
rupee risk limit.

Run:  python src/live_signal.py --max-loss 1250
"""
from __future__ import annotations

import argparse
import math

from data_feed import (
    get_index_history, get_option_chain, parse_atm_context, select_strike,
)
from strategy import StrategyParams, add_indicators, evaluate_row
from backtest import LOT_SIZE


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the latest NIFTY option signal")
    ap.add_argument("--max-loss", type=float, default=3000)
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--period", default="5d")
    ap.add_argument("--strike-style", choices=["ITM", "ATM", "OTM"],
                    default="ATM",
                    help="which strike to buy. ATM matches the backtest; "
                         "ITM is safer/costlier; OTM is cheap but underperforms")
    args = ap.parse_args()

    p = StrategyParams()
    df = add_indicators(get_index_history(args.period, args.interval), p)

    # Look at the most recent bars for a fresh signal
    sig = None
    for i in range(len(df) - 1, max(len(df) - 4, 0), -1):
        s = evaluate_row(df, i, p)
        if s is not None:
            sig = s
            break

    print("\n" + "=" * 60)
    print("NIFTY 50 OPTION SIGNAL")
    print("=" * 60)

    ctx = parse_atm_context(get_option_chain() or {})
    if ctx:
        print(f"Live spot     : {ctx['spot']}")
        print(f"ATM strike    : {ctx['atm_strike']}")
        print(f"ATM CE / PE   : {ctx['atm_ce_ltp']} / {ctx['atm_pe_ltp']}")
        print(f"PCR (OI)      : {ctx['pcr']}  "
              f"({'bullish' if (ctx['pcr'] or 0) > 1 else 'bearish'} tilt)")
    else:
        print("Live option chain: unavailable (NSE blocked/failed) — "
              "spot from yfinance below.")

    if sig is None:
        print("\nNo fresh signal on the last few bars. Stay flat / wait.\n")
        return

    print("-" * 60)
    print(f"SIGNAL        : BUY {sig.side}")
    print(f"Signal time   : {sig.timestamp}")
    print(f"Index entry   : {sig.entry}")
    print(f"Index stop    : {sig.stop_index}")
    print(f"Index target  : {sig.target_index}")
    print(f"RSI / ATR     : {sig.rsi} / {sig.atr}")

    # Position sizing to the rupee limit
    stop_dist = abs(sig.entry - sig.stop_index)
    risk_per_lot = stop_dist * p.option_delta * LOT_SIZE
    lots = max(1, math.floor(args.max_loss / risk_per_lot)) if risk_per_lot else 1
    print(f"Suggested lots: {lots}  "
          f"(risk ~= Rs.{risk_per_lot * lots:,.0f}, cap Rs.{args.max_loss:.0f})")

    # Recommend WHICH strike to buy, per the chosen style.
    if ctx:
        pick = select_strike(ctx, sig.side, args.strike_style)
        if pick and pick["premium"]:
            prem = pick["premium"]
            print(f"Strike style  : {pick['style']} (delta {pick['delta_hint']})")
            print(f"Buy           : NIFTY {pick['strike']} {sig.side} @ ~{prem}")
            print(f"Premium outlay: ~Rs.{prem * LOT_SIZE * lots:,.0f} "
                  f"for {lots} lot(s)")
            print(f"Strike note   : {pick['note']}")
        else:
            print("Strike        : option chain unavailable for the chosen strike.")

    print(f"\nWhy: {sig.note}\n")


if __name__ == "__main__":
    main()
