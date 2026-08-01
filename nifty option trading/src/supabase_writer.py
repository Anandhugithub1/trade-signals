"""
Write NIFTY option signals to the Supabase `nifty_option_signals` table.

Uses the SERVICE ROLE key (bypasses RLS), exactly like the crypto backend's
generate_signals job. Configured via env vars:

    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

If either is missing OR the supabase package isn't installed, insert_signal()
becomes a no-op that just logs -- so the CI run never fails because of it.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))


def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        print("  [supabase] package not installed; skipping DB write.")
        return None
    try:
        return create_client(url, key)
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] client init failed: {e}")
        return None


MARKET_CLOSE = (15, 30)   # 15:30 IST — intraday positions are squared off here


def _end_of_trading_day_ist(now: Optional[datetime] = None) -> str:
    """
    Intraday signals expire at 15:30 IST on the next session that is still
    open.

    A signal generated at or after 15:30 IST (a late CI run, or the 10:00 UTC
    cron that fires exactly at the close) used to get an expires_at in the
    PAST, which made the row look already-expired the moment it was written.
    Weekend runs had the same problem. So: if the close has already passed,
    roll forward to the next weekday's close.
    """
    now = now or datetime.now(IST)
    eod = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1],
                      second=0, microsecond=0)
    if now >= eod:
        eod += timedelta(days=1)
    while eod.weekday() >= 5:          # 5 = Saturday, 6 = Sunday
        eod += timedelta(days=1)
    return eod.isoformat()


def signal_record_to_row(rec: dict) -> Optional[dict]:
    """
    Map the run_signal.build_record() output to a table row.
    Returns None if there is no signal in the record.
    """
    sig = rec.get("signal")
    if not sig:
        return None

    ctx = rec.get("live_chain") or {}
    side = sig["side"]
    strike = ctx.get("atm_strike")
    premium = None
    if ctx:
        premium = ctx.get("atm_ce_ltp") if side == "CE" else ctx.get("atm_pe_ltp")

    now = datetime.now(IST)
    return {
        "id": str(uuid.uuid4()),
        "side": side,
        "strike": strike,
        "strike_style": "ATM",
        "premium": premium,
        "lots": sig.get("lots", 1),
        "spot": ctx.get("spot") or sig["index_entry"],
        "index_entry": sig["index_entry"],
        "index_stop": sig["index_stop"],
        "index_target": sig.get("index_target"),
        "max_loss_rs": sig["max_loss_rs"],
        "rsi": sig.get("rsi"),
        "atr": sig.get("atr"),
        "result": "pending",
        "entry_confirmed": False,
        "exit_reason": None,
        # timestamp = when the trade was CREATED; closed_at is filled in by
        # check_nifty_signals when it actually exits/expires.
        "timestamp": now.isoformat(),
        "expires_at": _end_of_trading_day_ist(now),
        "entry_at": None,
        "closed_at": None,
        "exit_index": None,
        "latest_index": ctx.get("spot") or sig["index_entry"],
        "note": sig.get("note"),
    }


def insert_signal(rec: dict) -> bool:
    """Insert one signal row. Returns True on success, False otherwise."""
    row = signal_record_to_row(rec)
    if row is None:
        return False

    client = _client()
    if client is None:
        print("  [supabase] not configured; signal NOT written to DB "
              "(set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to enable).")
        return False

    try:
        client.table("nifty_option_signals").insert(row).execute()
        print(f"  [supabase] inserted signal {row['side']} "
              f"strike={row['strike']} id={row['id'][:8]}...")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] insert failed: {e}")
        return False
