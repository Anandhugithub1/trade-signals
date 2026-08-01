"""
check_nifty_signals — closes out open NIFTY option signals.

This is the NIFTY counterpart to backend/check_signals (crypto). Without it,
every row inserted by run_signal.py stays `result='pending'` forever: nothing
ever wrote win/loss/expired, pnl_rs, or a closed-at time, so the app's win-rate
and P&L cards were computed over an empty "closed" set.

Logic per open signal (mirrors the crypto job's two-phase model, but on NIFTY
index bars and with the backtest's RUPEE stop):

  1. Fetch 15m NIFTY index bars covering the signal's session.
  2. Phase 1 — entry confirmation: the index must trade through index_entry.
     (run_signal posts the level at signal time, so this is usually the very
     first bar, but a gap can delay or skip it.)
  3. Phase 2 — once filled, watch each bar for:
        STOP    index_stop breached          -> loss
        TARGET  index_target reached         -> win   (skipped when target null)
  4. EOD — at/after expires_at the position is squared off at the last close;
     win/loss is then decided by the sign of the P&L.

P&L uses the same first-order delta model as the backtest (see backtest.py):

    pnl_rs = index_move_in_favour * option_delta * LOT_SIZE * lots

so the numbers here are directly comparable to the backtest's expectancy.
It ignores theta/gamma, which is why a flat EOD exit is booked as a loss-ish
small number rather than exactly zero.

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

from data_feed import get_index_history
from strategy import StrategyParams
from backtest import LOT_SIZE

IST = timezone(timedelta(hours=5, minutes=30))
SEP = "-" * 60

# Keep closed signals for 90 days, matching the crypto job's TTL and the
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
    """Parse a Supabase timestamptz into an IST-aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


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

    side = (row.get("side") or "CE").upper()
    is_ce = side == "CE"
    entry = float(row["index_entry"])
    stop = float(row["index_stop"])
    target = row.get("index_target")
    target = float(target) if target is not None else None
    lots = int(row.get("lots") or 1)

    delta = StrategyParams().option_delta
    rs_per_point = delta * LOT_SIZE * lots

    def pnl_for(exit_index: float) -> float:
        move = (exit_index - entry) if is_ce else (entry - exit_index)
        return round(move * rs_per_point, 2)

    # Only bars at/after the signal bar matter.
    window = bars[bars.index >= created]
    if window.empty:
        # No bars yet (fresh signal, or yfinance hasn't published the bar).
        # Still expire it if the session is over, so it can't hang forever.
        if expires is not None and now >= expires:
            return {
                "result": "expired",
                "exit_reason": "EOD",
                "closed_at": expires.isoformat(),
                "pnl_rs": 0.0,
                "exit_index": entry,
            }
        return None

    entry_confirmed = bool(row.get("entry_confirmed"))
    entry_at = _parse_ts(row.get("entry_at"))
    last_close = float(window["Close"].iloc[-1])

    for ts, bar in window.iterrows():
        high = float(bar["High"])
        low = float(bar["Low"])

        # Phase 1 — entry fill. The signal is posted at the bar's close, so a
        # CE fills when price trades at/below entry (and a PE at/above it).
        if not entry_confirmed:
            if (is_ce and low <= entry <= high) or (not is_ce and low <= entry <= high):
                entry_confirmed = True
                entry_at = ts
            else:
                continue

        # Phase 2 — stop first: on a bar that touches both, assume the worse
        # fill. We cannot see intrabar order from daily OHLC, and booking the
        # optimistic side would inflate the win rate.
        if is_ce:
            if low <= stop:
                return {
                    "result": "loss", "exit_reason": "STOP",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_index": round(stop, 2), "pnl_rs": pnl_for(stop),
                }
            if target is not None and high >= target:
                return {
                    "result": "win", "exit_reason": "TARGET",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_index": round(target, 2), "pnl_rs": pnl_for(target),
                }
        else:
            if high >= stop:
                return {
                    "result": "loss", "exit_reason": "STOP",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_index": round(stop, 2), "pnl_rs": pnl_for(stop),
                }
            if target is not None and low <= target:
                return {
                    "result": "win", "exit_reason": "TARGET",
                    "closed_at": ts.isoformat(), "entry_at":
                        entry_at.isoformat() if entry_at is not None else None,
                    "entry_confirmed": True,
                    "exit_index": round(target, 2), "pnl_rs": pnl_for(target),
                }

    # ── Square-off at expiry ────────────────────────────────────────────────
    if expires is not None and now >= expires:
        if not entry_confirmed:
            # Never filled — no position was ever taken, so no P&L.
            return {
                "result": "expired", "exit_reason": "EOD",
                "closed_at": expires.isoformat(),
                "entry_confirmed": False,
                "exit_index": round(last_close, 2), "pnl_rs": 0.0,
            }
        pnl = pnl_for(last_close)
        return {
            "result": "win" if pnl > 0 else "loss",
            "exit_reason": "EOD",
            "closed_at": expires.isoformat(),
            "entry_at": entry_at.isoformat() if entry_at is not None else None,
            "entry_confirmed": True,
            "exit_index": round(last_close, 2),
            "pnl_rs": pnl,
        }

    # Still open — persist the live progress so the app can show it.
    return {
        "_still_open": True,
        "entry_confirmed": entry_confirmed,
        "entry_at": entry_at.isoformat() if entry_at is not None else None,
        "latest_index": round(last_close, 2),
    }


def main() -> None:
    client = _client()
    if client is None:
        return

    now = datetime.now(IST)
    print(f"\n[check_nifty_signals] Run at {now:%Y-%m-%d %H:%M:%S IST}")

    try:
        res = (client.table("nifty_option_signals")
               .select("*").eq("result", "pending").execute())
        rows = res.data or []
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] fetch failed: {e}")
        return

    print(f"[check_nifty_signals] {len(rows)} open signal(s)")
    if not rows:
        return

    # One history pull covers every open signal (all are intraday NIFTY).
    try:
        bars = get_index_history("5d", "15m")
        bars.index = bars.index.tz_convert(IST) if bars.index.tz is not None \
            else bars.index.tz_localize(timezone.utc).tz_convert(IST)
    except Exception as e:  # noqa: BLE001
        print(f"  [data] index history unavailable: {e}")
        return

    closed = still_open = errors = 0

    for row in rows:
        sid = row["id"]
        try:
            verdict = evaluate_signal(row, bars, now)
            if verdict is None:
                still_open += 1
                continue

            if verdict.pop("_still_open", False):
                payload = {k: v for k, v in verdict.items() if v is not None}
                if payload:
                    client.table("nifty_option_signals") \
                        .update(payload).eq("id", sid).execute()
                still_open += 1
                print(f"  {SEP}")
                print(f"  {row['side']} {row.get('strike')} id={sid[:8]} "
                      f"-> still open "
                      f"(filled={payload.get('entry_confirmed')}, "
                      f"last={payload.get('latest_index')})")
                continue

            payload = {k: v for k, v in verdict.items() if v is not None}
            client.table("nifty_option_signals") \
                .update(payload).eq("id", sid).execute()
            closed += 1
            print(f"  {SEP}")
            print(f"  {row['side']} {row.get('strike')} id={sid[:8]} "
                  f"-> {verdict['result'].upper()} ({verdict['exit_reason']}) "
                  f"exit={verdict.get('exit_index')} "
                  f"pnl=Rs.{verdict.get('pnl_rs', 0):,.0f} "
                  f"closed_at={verdict.get('closed_at')}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  [ERR] {sid[:8]}: {type(e).__name__}: {e}")

    # ── TTL cleanup, mirroring the crypto job ───────────────────────────────
    try:
        cutoff = (now - timedelta(days=TTL_DAYS)).isoformat()
        deleted = (client.table("nifty_option_signals")
                   .delete().lt("timestamp", cutoff).execute())
        n = len(deleted.data) if deleted.data else 0
        print(f"\n  [TTL] Deleted {n} signal(s) older than {TTL_DAYS} days")
    except Exception as e:  # noqa: BLE001
        print(f"\n  [TTL ERR] {e}")

    print(f"\n{SEP}")
    print(f"[check_nifty_signals] Closed={closed}  Open={still_open}  Errors={errors}")


if __name__ == "__main__":
    main()
