"""
check_signals — Lambda-style cron handler
Fetches all pending trade signals from Supabase, checks Binance hourly
candles to see if Stop Loss or Take Profit was hit, then updates the result.

Trigger: run once a day (cron / AWS Lambda / any scheduler).
"""

import json
import os
import requests
from datetime import datetime, timezone
from supabase import create_client, Client

# ── env ───────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # bypasses RLS

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"


# ── helpers ───────────────────────────────────────────────────────────────────

def fetch_candles(symbol: str, start_ms: int) -> list:
    """
    Fetch 1-hour OHLC candles from Binance starting at signal creation time.
    Returns up to 500 candles (~20 days). Free, no API key required.
    Each candle: [openTime, open, high, low, close, volume, closeTime, ...]
    """
    params = {
        "symbol": symbol,
        "interval": "1h",
        "startTime": start_ms,
        "limit": 500,
    }
    resp = requests.get(BINANCE_KLINES, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def evaluate_signal(signal: dict, candles: list):
    """
    Walk candles in chronological order (oldest → newest).
    First SL or TP breach decides the result.

    Returns:
        ("win",  close_price)  if TP hit first
        ("loss", close_price)  if SL hit first
        (None,   None)         if still open / no breach found
    """
    direction = signal["direction"]
    sl = float(signal["stop_loss"])
    tp = float(signal["take_profit"])

    for candle in candles:
        high = float(candle[2])
        low  = float(candle[3])

        if direction == "long":
            if low <= sl:
                return "loss", sl
            if high >= tp:
                return "win", tp
        else:  # short
            if high >= sl:
                return "loss", sl
            if low <= tp:
                return "win", tp

    return None, None


def iso_to_ms(iso_str: str) -> int:
    """Convert ISO 8601 timestamp string to Unix milliseconds."""
    iso_str = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso_str).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


# ── main handler ──────────────────────────────────────────────────────────────

def handler(event=None, context=None):
    """
    AWS Lambda / generic cron entry point.
    Can also be called directly: python handler.py
    """
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # 1. Load all pending signals
    response = (
        supabase.table("trade_signals")
        .select("*")
        .eq("result", "pending")
        .execute()
    )
    signals = response.data
    print(f"[check_signals] {len(signals)} pending signal(s) found\n")

    stats = {"checked": len(signals), "updated": 0, "still_pending": 0, "errors": []}

    for signal in signals:
        pair = signal["pair"]
        direction = signal["direction"]
        sid = signal["id"]

        try:
            start_ms = iso_to_ms(signal["timestamp"])
            candles = fetch_candles(pair, start_ms)

            result, close_price = evaluate_signal(signal, candles)

            if result:
                supabase.table("trade_signals").update(
                    {"result": result, "close_price": close_price}
                ).eq("id", sid).execute()

                emoji = "✅" if result == "win" else "❌"
                print(f"  {emoji}  {pair} {direction.upper():5s}  →  {result.upper()}  @ {close_price}")
                stats["updated"] += 1
            else:
                print(f"  ⏳  {pair} {direction.upper():5s}  →  still pending ({len(candles)} candles checked)")
                stats["still_pending"] += 1

        except requests.HTTPError as exc:
            msg = f"{pair} ({sid}): Binance HTTP {exc.response.status_code}"
            print(f"  ⚠️  {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair} ({sid}): {exc}"
            print(f"  ⚠️  {msg}")
            stats["errors"].append(msg)

    print(f"\n[check_signals] Done — {stats['updated']} updated, "
          f"{stats['still_pending']} still pending, "
          f"{len(stats['errors'])} error(s)")

    return {
        "statusCode": 200,
        "body": json.dumps(stats),
    }


# ── local run ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()          # loads .env locally; no-op in GitHub Actions
    except ImportError:
        pass
    result = handler()
    print("\n" + json.dumps(json.loads(result["body"]), indent=2))
