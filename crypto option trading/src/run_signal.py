"""
CI entry point (used by the GitHub Actions workflow).

Fetches the latest BTC/ETH perp bars, evaluates the most recent signal for
each symbol, enriches it with a live Deribit ATM option context when
reachable, prints it to the workflow log, and writes it to Supabase so the
Flutter app's Options tab shows it.

Unlike the NIFTY module this has no market-hours gate — crypto trades 24/7,
so every scheduled run is a legitimate signal check.

Exit code is always 0 (a "no signal" is a normal outcome, not a failure).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

import pandas as pd

from data_feed import get_perp_history, get_live_price
from strategy import StrategyParams, add_indicators, evaluate_row
from live_signal import get_deribit_atm_context

# Don't act on a signal older than this. The scan looks back a few bars for a
# fresh trigger; without an age cap a delayed CI run could resurrect a
# trigger from hours earlier and post it as if it were live.
MAX_SIGNAL_AGE_MIN = 90  # generous vs NIFTY's 30 -- crypto runs every 4h, not 15min

# How long an unfilled/unresolved signal is allowed to sit before check_signals
# force-times it out. Matches the backtest's max_hold_bars (72 x 1h = 3 days).
MAX_HOLD_HOURS = 72


def build_record(symbol: str, max_loss: float, interval: str) -> dict:
    p = StrategyParams()
    df = add_indicators(get_perp_history(symbol, interval=interval, months=2), p)

    sig = None
    for i in range(len(df) - 1, max(len(df) - 4, 0), -1):
        s = evaluate_row(df, i, p)
        if s is not None:
            sig = s
            break

    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Reject a trigger that has already gone stale (delayed CI run).
    if sig is not None:
        bar_ts = pd.Timestamp(sig.timestamp)
        if bar_ts.tzinfo is None:
            bar_ts = bar_ts.tz_localize(timezone.utc)
        age_min = (now - bar_ts.to_pydatetime()).total_seconds() / 60
        if age_min > MAX_SIGNAL_AGE_MIN:
            print(f"  [STALE] {symbol} trigger bar is {age_min:.0f} min old "
                  f"(cap {MAX_SIGNAL_AGE_MIN}) — discarding")
            sig = None

    live_price = get_live_price(symbol) or (
        float(df.iloc[-1]["Close"]) if not df.empty else None
    )

    rec: dict = {
        "generated_at": now_str,
        "symbol": symbol,
        "signal": None,
        "live_price": live_price,
    }

    if sig is None:
        return rec

    stop_move = p.sl_atr_mult * sig.atr
    is_call = sig.side == "CALL"
    stop_price = sig.entry - stop_move if is_call else sig.entry + stop_move
    risk_per_unit = stop_move * p.option_delta
    size = round(max_loss / risk_per_unit, 6) if risk_per_unit > 0 else 0.0

    rec["signal"] = {
        "symbol": symbol,
        "side": sig.side,
        "signal_time": sig.timestamp,
        "entry": sig.entry,
        "stop_price": round(stop_price, 2),
        "target_price": sig.target_index,
        "rsi": sig.rsi,
        "atr": sig.atr,
        "max_loss_usd": max_loss,
        "size": size,
        "note": sig.note,
    }

    ctx = get_deribit_atm_context(symbol, live_price or sig.entry)
    if ctx:
        leg = "call_" if is_call else "put_"
        rec["signal"]["strike"] = ctx.get("atm_strike")
        rec["signal"]["instrument"] = ctx.get(leg + "instrument")
        expiry_ms = ctx.get("expiry_ts_ms")
        if expiry_ms:
            rec["signal"]["option_expiry"] = (
                datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).date().isoformat()
            )

    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT"))
    ap.add_argument("--max-loss", type=float,
                     default=float(os.getenv("MAX_LOSS", "200")))
    ap.add_argument("--interval", default=os.getenv("INTERVAL", "1h"))
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    for symbol in symbols:
        rec = build_record(symbol, args.max_loss, args.interval)
        print(json.dumps(rec, indent=2, default=str))

        if rec["signal"]:
            s = rec["signal"]
            print(f"\n>>> SIGNAL: BUY {s['side']} {symbol}  "
                  f"entry={s['entry']} stop={s['stop_price']} "
                  f"target={s['target_price']}  (max loss ${s['max_loss_usd']:.0f})")
            try:
                from supabase_writer import insert_signal
                insert_signal(rec, max_hold_hours=MAX_HOLD_HOURS)
            except Exception as e:  # noqa: BLE001 -- never fail the run on DB issues
                print(f"  [supabase] skipped: {e}")
        else:
            print(f"\n>>> No fresh signal for {symbol} this bar. Stay flat.")


if __name__ == "__main__":
    main()
