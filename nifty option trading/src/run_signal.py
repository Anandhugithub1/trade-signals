"""
CI entry point (used by the GitHub Actions workflow).

Fetches the latest NIFTY bars, evaluates the most recent signal, enriches it
with the live NSE ATM premium/PCR when reachable, prints it to the workflow
log, and writes it to Supabase so the Flutter app's NIFTY Options tab shows it.

Exit code is always 0 (a "no signal" is a normal outcome, not a failure).
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from data_feed import get_index_history, get_option_chain, parse_atm_context
from strategy import StrategyParams, add_indicators, evaluate_row
from backtest import LOT_SIZE

IST = timezone(timedelta(hours=5, minutes=30))


def build_record(max_loss: float, interval: str, period: str) -> dict:
    p = StrategyParams()
    df = add_indicators(get_index_history(period, interval), p)

    sig = None
    for i in range(len(df) - 1, max(len(df) - 4, 0), -1):
        s = evaluate_row(df, i, p)
        if s is not None:
            sig = s
            break

    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    ctx = parse_atm_context(get_option_chain() or {})

    rec: dict = {
        "generated_at": now_ist,
        "signal": None,
        "live_chain": ctx,  # may be None if NSE unreachable
    }

    if sig is None:
        return rec

    stop_move = max_loss / (p.option_delta * LOT_SIZE)
    lots = 1
    rec["signal"] = {
        "side": sig.side,
        "signal_time": sig.timestamp,
        "index_entry": sig.entry,
        "index_stop": round(
            sig.entry - stop_move if sig.side == "CE" else sig.entry + stop_move, 2
        ),
        "index_target": sig.target_index,
        "rsi": sig.rsi,
        "atr": sig.atr,
        "max_loss_rs": max_loss,
        "lots": lots,
        "note": sig.note,
    }

    if ctx:
        prem = ctx["atm_ce_ltp"] if sig.side == "CE" else ctx["atm_pe_ltp"]
        rec["signal"]["buy"] = f"NIFTY {ctx['atm_strike']} {sig.side} @ ~{prem}"
        if prem:
            rec["signal"]["premium_outlay_rs"] = round(prem * LOT_SIZE * lots, 0)

    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-loss", type=float,
                    default=float(os.getenv("MAX_LOSS", "3000")))
    ap.add_argument("--interval", default=os.getenv("INTERVAL", "15m"))
    ap.add_argument("--period", default=os.getenv("PERIOD", "5d"))
    args = ap.parse_args()

    rec = build_record(args.max_loss, args.interval, args.period)

    print(json.dumps(rec, indent=2))

    if rec["signal"]:
        s = rec["signal"]
        print(f"\n>>> SIGNAL: BUY {s['side']}  "
              f"entry={s['index_entry']} stop={s['index_stop']} "
              f"target={s['index_target']}  (max loss Rs.{s['max_loss_rs']:.0f})")
        # Write to Supabase so the Flutter app's NIFTY Options tab shows it.
        # No-op (with a log line) if Supabase env vars aren't configured.
        try:
            from supabase_writer import insert_signal
            insert_signal(rec)
        except Exception as e:  # noqa: BLE001 -- never fail the run on DB issues
            print(f"  [supabase] skipped: {e}")
    else:
        print("\n>>> No fresh signal this bar. Stay flat.")


if __name__ == "__main__":
    main()
