"""
Write new-listing-short signals to Supabase, and check which symbols
already have a row (so run_signal.py never re-signals the same listing
twice across its ~7-day entry window).

Same degrade-gracefully pattern as every other engine: missing env vars or
the supabase package not installed makes every function a safe no-op.
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


def get_already_signaled_symbols() -> set[str]:
    """
    Every symbol that already has a row (pending or closed). The strategy
    fires at most once per listing, so this is the de-dupe check.
    Returns an empty set (never blocks generation) if Supabase is
    unreachable/unconfigured -- the DB's own UNIQUE(symbol) index is the
    real backstop against a duplicate insert.
    """
    client = _client()
    if client is None:
        return set()
    try:
        res = client.table("new_listing_shorts").select("symbol").execute()
        return {row["symbol"] for row in (res.data or [])}
    except Exception as e:  # noqa: BLE001
        print(f"  [supabase] could not fetch existing symbols: {e}")
        return set()


def signal_record_to_row(sig, max_hold_days: int) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "symbol": sig.symbol,
        "listing_date": sig.listing_date,
        "days_since_listing": sig.days_since_listing,
        "entry": sig.entry,
        "stop_price": sig.stop_price,
        "lock_price": sig.lock_price,
        "result": "pending",
        "exit_reason": None,
        "timestamp": now.isoformat(),
        "expires_at": (now + timedelta(days=max_hold_days)).isoformat(),
        "closed_at": None,
        "exit_price": None,
        "latest_price": sig.entry,
        "note": sig.note,
    }


def insert_signal(sig, max_hold_days: int) -> bool:
    row = signal_record_to_row(sig, max_hold_days)
    client = _client()
    if client is None:
        print("  [supabase] not configured; signal NOT written to DB.")
        return False
    try:
        client.table("new_listing_shorts").insert(row).execute()
        print(f"  [supabase] inserted signal SHORT {row['symbol']} id={row['id'][:8]}...")
        return True
    except Exception as e:  # noqa: BLE001
        # A UNIQUE(symbol) conflict here means another run already signaled
        # this listing -- not an error, just the de-dupe constraint working.
        print(f"  [supabase] insert failed (likely already signaled): {e}")
        return False
