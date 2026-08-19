"""
Write crypto option signals to the Supabase `crypto_option_signals` table.

Uses the SERVICE ROLE key (bypasses RLS), exactly like the crypto futures
backend's generate_signals job. Configured via env vars:

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


def signal_record_to_row(rec: dict, max_hold_hours: int = 72) -> Optional[dict]:
    """
    Map the run_signal.build_record() output to a table row.
    Returns None if there is no signal in the record.
    """
    sig = rec.get("signal")
    if not sig:
        return None

    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "symbol": sig["symbol"],
        "side": sig["side"],
        "strike": sig.get("strike"),
        "option_expiry": sig.get("option_expiry"),
        "instrument": sig.get("instrument"),
        "size": sig.get("size", 0),
        "spot": rec.get("live_price") or sig["entry"],
        "entry": sig["entry"],
        "stop_price": sig["stop_price"],
        "target_price": sig.get("target_price"),
        "max_loss_usd": sig["max_loss_usd"],
        "rsi": sig.get("rsi"),
        "atr": sig.get("atr"),
        "result": "pending",
        "entry_confirmed": False,
        "exit_reason": None,
        # timestamp = when the trade was CREATED; closed_at is filled in by
        # check_signals.py when it actually exits/times out.
        "timestamp": now.isoformat(),
        "expires_at": (now + timedelta(hours=max_hold_hours)).isoformat(),
        "entry_at": None,
        "closed_at": None,
        "exit_price": None,
        "latest_price": rec.get("live_price") or sig["entry"],
        "note": sig.get("note"),
    }


def insert_signal(rec: dict, max_hold_hours: int = 72) -> bool:
    """Insert one signal row. Returns True on success, False otherwise."""
    row = signal_record_to_row(rec, max_hold_hours=max_hold_hours)
    if row is None:
        return False

    client = _client()
    if client is None:
        print("  [supabase] not configured; signal NOT written to DB "
              "(set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to enable).")
        return False

    try:
        client.table("crypto_option_signals").insert(row).execute()
        print(f"  [supabase] inserted signal {row['symbol']} {row['side']} "
              f"id={row['id'][:8]}...")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] insert failed: {e}")
        return False
