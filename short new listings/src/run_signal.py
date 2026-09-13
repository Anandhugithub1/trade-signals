"""
CI entry point (used by the GitHub Actions workflow).

Scans every Binance USDT perp currently in the entry-age window
(27-33 days since listing, see strategy.py), skips any symbol that already
has a signal row (a listing gets exactly one shot at this strategy, ever),
and writes a SHORT signal for each new match.

Exit code is always 0 (no eligible listings this run is a normal outcome).
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

from data_feed import get_usdt_perp_listings, get_live_price
from strategy import StrategyParams, evaluate_listing


def _notify(symbol: str) -> None:
    """
    Push "new signal" alert, only to devices new enough to have the Shorts
    tab (see push_notify.py). Never fails the run — a push failure must
    not prevent the signal from being recorded.
    """
    try:
        from supabase_writer import _client
        from push_notify import notify_new_signal
        client = _client()
        if client is not None:
            notify_new_signal(client, symbol)
    except Exception as e:  # noqa: BLE001
        print(f"  [FCM] skipped: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop-pct", type=float, default=float(os.getenv("STOP_PCT", "0.30")))
    ap.add_argument("--lock-pct", type=float, default=float(os.getenv("LOCK_PCT", "0.50")))
    ap.add_argument("--max-hold-days", type=int, default=int(os.getenv("MAX_HOLD_DAYS", "30")))
    args = ap.parse_args()

    p = StrategyParams(stop_pct=args.stop_pct, lock_pct=args.lock_pct,
                        max_hold_days=args.max_hold_days)

    print(f"Scanning Binance USDT perps for listings {p.entry_window_min_days}-"
          f"{p.entry_window_max_days} days old ...")
    candidates = get_usdt_perp_listings(
        min_age_days=p.entry_window_min_days, max_age_days=p.entry_window_max_days)
    print(f"  {len(candidates)} listing(s) in the entry window")

    if not candidates:
        return

    from supabase_writer import get_already_signaled_symbols, insert_signal
    already = get_already_signaled_symbols()
    print(f"  {len(already)} symbol(s) already have a signal on record")

    fired = 0
    for c in candidates:
        if c["symbol"] in already:
            continue
        live_price = get_live_price(c["symbol"])
        sig = evaluate_listing(c["symbol"], c["onboard_ms"], c["age_days"], live_price, p)
        if sig is None:
            continue
        print(f"\n>>> SIGNAL: SHORT {sig.symbol}  entry={sig.entry} "
              f"stop={sig.stop_price} lock={sig.lock_price}")
        print(json.dumps(sig.__dict__, indent=2, default=str))
        try:
            if insert_signal(sig, args.max_hold_days):
                fired += 1
                _notify(sig.symbol)
        except Exception as e:  # noqa: BLE001 -- never fail the run on DB issues
            print(f"  [supabase] skipped: {e}")

    print(f"\n>>> {fired} new signal(s) written this run.")


if __name__ == "__main__":
    main()
