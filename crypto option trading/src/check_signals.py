"""
check_signals — closes out open crypto option signals.

This is the crypto-options counterpart to backend/check_signals (futures)
and the NIFTY module's check_nifty_signals.py, adapted for a 24/7 market:
there is no session close to square off against, so a position that never
hits its stop or target is force-closed at `expires_at` (entry time +
max_hold_hours, matching the backtest's max_hold_bars) instead of at a fixed
daily close time.

Without this job, every row inserted by run_signal.py stays `result='pending'`
forever: nothing ever writes win/loss/expired, pnl_usd, or a closed-at time,
so the app's win-rate and P&L cards would be computed over an empty set.

Logic per open signal:
  1. Fetch 1h bars for the signal's symbol covering its lifetime.
  2. Phase 1 — entry confirmation: price must trade through `entry`.
  3. Phase 2 — once filled, watch each bar for:
        STOP    stop_price breached      -> loss
        TARGET  target_price reached     -> win   (skipped when target null)
  4. TIMEOUT — at/after expires_at the position is closed at the last seen
     price; win/loss is then decided by the sign of the P&L.

P&L uses the same first-order delta model as the backtest (see backtest.py):

    pnl_usd = price_move_in_favour * option_delta * size

so the numbers here are directly comparable to the backtest's expectancy.

Exit code is always 0 — "nothing to close" is a normal outcome.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

import pandas as pd

from data_feed import get_perp_history
from strategy import StrategyParams

SEP = "-" * 60

# Keep closed signals for 90 days, matching the other jobs' TTL and the
# app's "last 90 days" fetch window.
TTL_DAYS = 90


def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("  [supabase] SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set "
              "— cannot check signals.")
        return None
    try:
        from supabase import create_client
    except ImportError:
        print("  [supabase] package not installed; skipping.")
        return None
    try:
        return create_client(url, key)
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] client init failed: {e}")
        return None


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate_signal(row: dict, bars: pd.DataFrame, now: datetime) -> Optional[dict]:
    """
    Walk the bars after the signal time and decide the outcome.

    Returns None while the trade is still genuinely open, otherwise a dict of
    the columns to write back.
    """
    created = _parse_ts(row.get("timestamp"))
    expires = _parse_ts(row.get("expires_at"))
    if created is None:
        return None

    side = (row.get("side") or "CALL").upper()
    is_call = side == "CALL"
    entry = float(row["entry"])
    stop = float(row["stop_price"])
    target = row.get("target_price")
    target = float(target) if target is not None else None
    size = float(row.get("size") or 0)

    delta = StrategyParams().option_delta

    def pnl_for(exit_price: float) -> float:
        move = (exit_price - entry) if is_call else (entry - exit_price)
        return round(move * delta * size, 2)

    window = bars[bars.index >= created]
    if expires is not None:
        window = window[window.index <= expires]
    if window.empty:
        if expires is not None and now >= expires:
            return {
                "result": "expired",
                "exit_reason": "TIMEOUT",
                "closed_at": expires.isoformat(),
                "pnl_usd": 0.0,
                "exit_price": entry,
            }
        return None

    entry_confirmed = bool(row.get("entry_confirmed"))
    entry_at = _parse_ts(row.get("entry_at"))
    last_close = float(window["Close"].iloc[-1])

    for ts, bar in window.iterrows():
        high = float(bar["High"])
        low = float(bar["Low"])

        # Phase 1 — entry fill.
        if not entry_confirmed:
            if low <= entry <= high:
                entry_confirmed = True
                entry_at = ts
            else:
                continue

        # Phase 2 — stop first: on a bar that touches both, assume the worse
        # fill (cannot see intrabar order from OHLC).
        if is_call:
            if low <= stop:
                return {
                    "result": "loss", "exit_reason": "STOP",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_price": round(stop, 2), "pnl_usd": pnl_for(stop),
                }
            if target is not None and high >= target:
                return {
                    "result": "win", "exit_reason": "TARGET",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_price": round(target, 2), "pnl_usd": pnl_for(target),
                }
        else:
            if high >= stop:
                return {
                    "result": "loss", "exit_reason": "STOP",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_price": round(stop, 2), "pnl_usd": pnl_for(stop),
                }
            if target is not None and low <= target:
                return {
                    "result": "win", "exit_reason": "TARGET",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_price": round(target, 2), "pnl_usd": pnl_for(target),
                }

    # Force-close at timeout (no session close in crypto -- only a max hold).
    if expires is not None and now >= expires:
        if not entry_confirmed:
            return {
                "result": "expired", "exit_reason": "TIMEOUT",
                "closed_at": expires.isoformat(),
                "entry_confirmed": False,
                "exit_price": round(last_close, 2), "pnl_usd": 0.0,
            }
        pnl = pnl_for(last_close)
        return {
            "result": "win" if pnl > 0 else "loss",
            "exit_reason": "TIMEOUT",
            "closed_at": expires.isoformat(),
            "entry_at": entry_at.isoformat() if entry_at is not None else None,
            "entry_confirmed": True,
            "exit_price": round(last_close, 2),
            "pnl_usd": pnl,
        }

    # Still open — persist live progress so the app can show it.
    return {
        "_still_open": True,
        "entry_confirmed": entry_confirmed,
        "entry_at": entry_at.isoformat() if entry_at is not None else None,
        "latest_price": round(last_close, 2),
    }


def main() -> None:
    client = _client()
    if client is None:
        return

    now = datetime.now(timezone.utc)
    print(f"\n[check_signals] Run at {now:%Y-%m-%d %H:%M:%S UTC}")

    try:
        res = (client.table("crypto_option_signals")
               .select("*").eq("result", "pending").execute())
        rows = res.data or []
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] fetch failed: {e}")
        return

    print(f"[check_signals] {len(rows)} open signal(s)")
    if not rows:
        return

    # Group by symbol so each gets its own bar history.
    by_symbol: dict[str, list] = {}
    for row in rows:
        by_symbol.setdefault(row.get("symbol", "BTCUSDT"), []).append(row)

    bars_cache: dict[str, pd.DataFrame] = {}
    for symbol in by_symbol:
        try:
            bars = get_perp_history(symbol, interval="1h", months=1)
            if bars.index.tz is None:
                bars.index = bars.index.tz_localize(timezone.utc)
            bars_cache[symbol] = bars
        except Exception as e:  # noqa: BLE001
            print(f"  [data] {symbol} history unavailable: {e}")

    closed = still_open = errors = 0

    for symbol, symbol_rows in by_symbol.items():
        bars = bars_cache.get(symbol)
        if bars is None:
            errors += len(symbol_rows)
            continue

        for row in symbol_rows:
            sid = row["id"]
            try:
                verdict = evaluate_signal(row, bars, now)
                if verdict is None:
                    still_open += 1
                    continue

                if verdict.pop("_still_open", False):
                    payload = {k: v for k, v in verdict.items() if v is not None}
                    if payload:
                        client.table("crypto_option_signals") \
                            .update(payload).eq("id", sid).execute()
                    still_open += 1
                    print(f"  {SEP}")
                    print(f"  {symbol} {row['side']} id={sid[:8]} -> still open "
                          f"(filled={payload.get('entry_confirmed')}, "
                          f"last={payload.get('latest_price')})")
                    continue

                payload = {k: v for k, v in verdict.items() if v is not None}
                client.table("crypto_option_signals") \
                    .update(payload).eq("id", sid).execute()
                closed += 1
                print(f"  {SEP}")
                print(f"  {symbol} {row['side']} id={sid[:8]} -> "
                      f"{verdict['result'].upper()} ({verdict['exit_reason']}) "
                      f"exit={verdict.get('exit_price')} "
                      f"pnl=${verdict.get('pnl_usd', 0):,.2f} "
                      f"closed_at={verdict.get('closed_at')}")
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"  [ERR] {sid[:8]}: {type(e).__name__}: {e}")

    # ── TTL cleanup, mirroring the other jobs ───────────────────────────────
    try:
        cutoff = (now - timedelta(days=TTL_DAYS)).isoformat()
        deleted = (client.table("crypto_option_signals")
                   .delete().lt("timestamp", cutoff).execute())
        n = len(deleted.data) if deleted.data else 0
        print(f"\n  [TTL] Deleted {n} signal(s) older than {TTL_DAYS} days")
    except Exception as e:  # noqa: BLE001
        print(f"\n  [TTL ERR] {e}")

    print(f"\n{SEP}")
    print(f"[check_signals] Closed={closed}  Open={still_open}  Errors={errors}")


if __name__ == "__main__":
    main()
