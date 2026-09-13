"""
check_signals — closes out open new-listing-short signals.

Logic per open signal:
  1. Fetch daily bars for the symbol from its entry time onward.
  2. Walk forward, checking each bar for:
        STOP   price high >= stop_price   -> loss  (checked first: worse-case
                                                      ordering when a bar
                                                      touches both levels)
        LOCK   price low  <= lock_price   -> win   (profit locked in early)
  3. TIME — at/after expires_at with neither triggered, close at the last
     seen price; win/loss decided by the sign of the resulting pnl.

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

from data_feed import get_daily_klines, klines_to_df

SEP = "-" * 60
TTL_DAYS = 90  # matches every other engine's TTL


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
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def evaluate_signal(row: dict, bars: pd.DataFrame, now: datetime) -> Optional[dict]:
    created = _parse_ts(row.get("timestamp"))
    expires = _parse_ts(row.get("expires_at"))
    if created is None or bars is None or bars.empty:
        return None

    entry = float(row["entry"])
    stop = float(row["stop_price"])
    lock = float(row["lock_price"])

    def pnl_for(exit_price: float) -> float:
        return round((entry - exit_price) / entry * 100, 2)

    window = bars[bars.index >= created]
    if expires is not None:
        window = window[window.index <= expires]
    if window.empty:
        if expires is not None and now >= expires:
            return {"result": "expired", "exit_reason": "TIME",
                    "closed_at": expires.isoformat(), "pnl_pct": 0.0,
                    "exit_price": entry}
        return None

    last_close = float(window["Close"].iloc[-1])

    for ts, bar in window.iterrows():
        high, low = float(bar["High"]), float(bar["Low"])
        if high >= stop:
            return {"result": "loss", "exit_reason": "STOP",
                    "closed_at": ts.isoformat(),
                    "exit_price": round(stop, 8), "pnl_pct": pnl_for(stop)}
        if low <= lock:
            return {"result": "win", "exit_reason": "LOCK",
                    "closed_at": ts.isoformat(),
                    "exit_price": round(lock, 8), "pnl_pct": pnl_for(lock)}

    if expires is not None and now >= expires:
        pnl = pnl_for(last_close)
        return {"result": "win" if pnl > 0 else "loss", "exit_reason": "TIME",
                "closed_at": expires.isoformat(),
                "exit_price": round(last_close, 8), "pnl_pct": pnl}

    # Still open — persist live progress.
    return {"_still_open": True, "latest_price": round(last_close, 8)}


def main() -> None:
    client = _client()
    if client is None:
        return

    now = datetime.now(timezone.utc)
    print(f"\n[check_signals] Run at {now:%Y-%m-%d %H:%M:%S UTC}")

    try:
        res = (client.table("new_listing_shorts")
               .select("*").eq("result", "pending").execute())
        rows = res.data or []
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] fetch failed: {e}")
        return

    print(f"[check_signals] {len(rows)} open signal(s)")
    if not rows:
        return

    closed = still_open = errors = 0
    for row in rows:
        sid = row["id"]
        symbol = row["symbol"]
        try:
            created = _parse_ts(row.get("timestamp"))
            candles = get_daily_klines(symbol, created.timestamp() * 1000, limit=40)
            if not candles:
                print(f"  [data] {symbol} history unavailable")
                errors += 1
                continue
            bars = klines_to_df(candles)

            verdict = evaluate_signal(row, bars, now)
            if verdict is None:
                still_open += 1
                continue

            if verdict.pop("_still_open", False):
                payload = {k: v for k, v in verdict.items() if v is not None}
                if payload:
                    client.table("new_listing_shorts").update(payload).eq("id", sid).execute()
                still_open += 1
                print(f"  {SEP}\n  {symbol} id={sid[:8]} -> still open "
                      f"(last={payload.get('latest_price')})")
                continue

            payload = {k: v for k, v in verdict.items() if v is not None}
            client.table("new_listing_shorts").update(payload).eq("id", sid).execute()
            closed += 1
            print(f"  {SEP}\n  {symbol} id={sid[:8]} -> {verdict['result'].upper()} "
                  f"({verdict['exit_reason']}) exit={verdict.get('exit_price')} "
                  f"pnl={verdict.get('pnl_pct', 0):+.2f}% closed_at={verdict.get('closed_at')}")
            try:
                from push_notify import notify_signal_result
                notify_signal_result(client, symbol, verdict.get("result"), verdict.get("pnl_pct"))
            except Exception as e:  # noqa: BLE001 -- never fail resolution over a push error
                print(f"  [FCM] skipped: {e}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  [ERR] {sid[:8]}: {type(e).__name__}: {e}")

    try:
        cutoff = (now - timedelta(days=TTL_DAYS)).isoformat()
        deleted = client.table("new_listing_shorts").delete().lt("timestamp", cutoff).execute()
        n = len(deleted.data) if deleted.data else 0
        print(f"\n  [TTL] Deleted {n} signal(s) older than {TTL_DAYS} days")
    except Exception as e:  # noqa: BLE001
        print(f"\n  [TTL ERR] {e}")

    print(f"\n{SEP}\n[check_signals] Closed={closed}  Open={still_open}  Errors={errors}")


if __name__ == "__main__":
    main()
