"""
check_signals — Lambda-style cron handler

Logic per signal:
  1. Fetch 1-hour candles from the hour the signal was posted → now.
  2. Phase 1  — wait until the entry price is touched in a candle.
  3. Phase 2  — once entry is confirmed, watch for SL or TP breach.
  4. Expiry   — if neither is hit within SIGNAL_EXPIRY_DAYS, mark "expired".

UTC note:
  All timestamps are handled in UTC throughout.
  iso_to_ms()  → parses any ISO-8601 string and forces UTC before converting.
  now_ms()     → datetime.now(timezone.utc) — always UTC.
  Binance API  → accepts/returns Unix ms, which are inherently UTC.
  No local-time conversions happen anywhere in this file.

Trigger: run once a day (cron / AWS Lambda / any scheduler).
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── config ────────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

BINANCE_KLINES     = "https://fapi.binance.com/fapi/v1/klines"  # USDT-M Futures perpetual
BYBIT_KLINES       = "https://api.bybit.com/v5/market/kline"    # Bybit USDT perpetual (fallback)
SIGNAL_EXPIRY_DAYS = 14
HOUR_MS            = 3_600_000
SEP                = "-" * 60


# ── helpers ───────────────────────────────────────────────────────────────────

def now_ms() -> int:
    """Current time as UTC milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def iso_to_ms(iso_str: str) -> int:
    """
    ISO 8601 string → UTC milliseconds.
    Forces UTC regardless of the offset stored in the string,
    so 'Z', '+00:00', '+05:30' etc. all resolve correctly.
    """
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def ms_to_utc(ms: int) -> str:
    """UTC milliseconds → human-readable UTC string for logs."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fetch_candles(symbol: str, signal_ms: int) -> list:
    """
    Fetch 1-hour OHLCV candles.
    Tries Binance Futures first; falls back to Bybit on HTTP 451/403
    (Binance blocks certain cloud/geo IP ranges including GitHub Actions).

    Both APIs return the same index layout we use:
      [0] open_time_ms  [2] high  [3] low  [4] close  [5] volume
    Bybit returns newest-first so we reverse before returning.
    """
    start = (signal_ms // HOUR_MS) * HOUR_MS
    end   = now_ms()

    # ── Binance attempt ───────────────────────────────────────────────────────
    try:
        resp = requests.get(
            BINANCE_KLINES,
            params={"symbol": symbol, "interval": "1h",
                    "startTime": start, "endTime": end, "limit": 500},
            timeout=10,
        )
        if resp.status_code not in (451, 403):
            resp.raise_for_status()
            return resp.json()
        print(f"  [WARN] Binance {resp.status_code} for {symbol} — falling back to Bybit")
    except requests.RequestException as e:
        print(f"  [WARN] Binance error for {symbol} ({e}) — falling back to Bybit")

    # ── Bybit fallback ────────────────────────────────────────────────────────
    resp = requests.get(
        BYBIT_KLINES,
        params={
            "category": "linear",
            "symbol":   symbol,
            "interval": "60",          # 60 minutes = 1h
            "start":    start,
            "end":      end,
            "limit":    500,
        },
        timeout=10,
    )
    resp.raise_for_status()
    candles = resp.json()["result"]["list"]
    return list(reversed(candles))     # Bybit is newest-first → reverse to oldest-first


def evaluate_signal(signal: dict, candles: list, signal_ms: int) -> tuple:
    """
    Two-phase evaluation.  Returns (result, close_price, diag).

    diag dict keys
    --------------
    entry_confirmed   bool
    entry_candle      str | None   — UTC time of candle that confirmed entry
    result_candle     str | None   — UTC time of candle that triggered SL/TP
    result_candle_h   float | None
    result_candle_l   float | None
    candles_skipped   int          — pre-signal partial candles ignored
    candles_checked   int          — candles evaluated in Phase 1/2
    last_candle_time  str | None   — most recent candle time (for pending logs)
    last_close        float | None — most recent close price
    dist_to_sl_pct    float | None — % distance from last close to SL
    dist_to_tp_pct    float | None — % distance from last close to TP
    """
    direction = signal["direction"]
    entry     = float(signal.get("entry_price") or signal.get("entry", 0))
    sl        = float(signal["stop_loss"])
    tp        = float(signal["take_profit"])

    diag = {
        "entry_confirmed":  False,
        "entry_candle":     None,
        "result_candle":    None,
        "result_candle_h":  None,
        "result_candle_l":  None,
        "candles_skipped":  0,
        "candles_checked":  0,
        "last_candle_time": None,
        "last_close":       None,
        "dist_to_sl_pct":   None,
        "dist_to_tp_pct":   None,
    }

    for candle in candles:
        open_ms = int(candle[0])
        high    = float(candle[2])
        low     = float(candle[3])
        close   = float(candle[4])

        # Skip the partial first candle that opened before the signal was posted
        if open_ms < signal_ms:
            diag["candles_skipped"] += 1
            continue

        diag["candles_checked"]  += 1
        diag["last_candle_time"]  = ms_to_utc(open_ms)
        diag["last_close"]        = close

        # Phase 1 — entry confirmation
        if not diag["entry_confirmed"]:
            if direction == "long"  and low  <= entry:
                diag["entry_confirmed"] = True
                diag["entry_candle"]    = ms_to_utc(open_ms)
            elif direction == "short" and high >= entry:
                diag["entry_confirmed"] = True
                diag["entry_candle"]    = ms_to_utc(open_ms)

        # Phase 2 — SL / TP (runs in same candle entry was confirmed)
        if diag["entry_confirmed"]:
            if direction == "long":
                if low <= sl:
                    diag["result_candle"]   = ms_to_utc(open_ms)
                    diag["result_candle_h"] = high
                    diag["result_candle_l"] = low
                    return "loss", sl, diag
                if high >= tp:
                    diag["result_candle"]   = ms_to_utc(open_ms)
                    diag["result_candle_h"] = high
                    diag["result_candle_l"] = low
                    return "win", tp, diag
            else:
                if high >= sl:
                    diag["result_candle"]   = ms_to_utc(open_ms)
                    diag["result_candle_h"] = high
                    diag["result_candle_l"] = low
                    return "loss", sl, diag
                if low <= tp:
                    diag["result_candle"]   = ms_to_utc(open_ms)
                    diag["result_candle_h"] = high
                    diag["result_candle_l"] = low
                    return "win", tp, diag

    # Compute distance from last close to SL / TP for pending diagnostics
    if diag["last_close"]:
        lc = diag["last_close"]
        if direction == "long":
            diag["dist_to_sl_pct"] = round((sl  - lc) / lc * 100, 2)  # negative = SL below price
            diag["dist_to_tp_pct"] = round((tp  - lc) / lc * 100, 2)  # positive = TP above price
        else:
            diag["dist_to_sl_pct"] = round((lc  - sl) / lc * 100, 2)  # positive = SL above price
            diag["dist_to_tp_pct"] = round((lc  - tp) / lc * 100, 2)  # positive = TP below price

    # ── Expiry check ──────────────────────────────────────────────────────────
    # Prefer the signal's own expires_at (set at creation time, 2–7 days).
    # Fall back to the flat SIGNAL_EXPIRY_DAYS for older signals without it.
    expires_at_str = signal.get("expires_at")
    if expires_at_str:
        if now_ms() >= iso_to_ms(expires_at_str):
            return "expired", None, diag
    else:
        age_days = (now_ms() - signal_ms) / 86_400_000
        if age_days >= SIGNAL_EXPIRY_DAYS:
            return "expired", None, diag

    return None, None, diag


def log_signal_header(signal: dict, signal_ms: int, candles: list) -> None:
    """Print signal details and UTC timestamp info before evaluation."""
    entry = float(signal.get("entry_price") or signal.get("entry", 0))
    sl    = float(signal["stop_loss"])
    tp    = float(signal["take_profit"])
    age_h = int((now_ms() - signal_ms) / HOUR_MS)

    expires_at_str = signal.get("expires_at", "")
    if expires_at_str:
        expires_ms  = iso_to_ms(expires_at_str)
        hours_left  = (expires_ms - now_ms()) / HOUR_MS
        expiry_line = f"{expires_at_str[:10]}  ({'+' if hours_left >= 0 else ''}{hours_left:.1f}h {'left' if hours_left >= 0 else 'OVERDUE'})"
    else:
        expiry_line = "not set (legacy signal)"

    print(SEP)
    print(f"  {signal['pair']} | {signal['direction'].upper()} | id={signal['id']}")
    print(f"  Posted   : {ms_to_utc(signal_ms)}  ({age_h}h ago)")
    print(f"  Expires  : {expiry_line}")
    print(f"  Entry    : {entry:>12,.4f}")
    print(f"  SL       : {sl:>12,.4f}")
    print(f"  TP       : {tp:>12,.4f}")
    if candles:
        first_t = ms_to_utc(int(candles[0][0]))
        last_t  = ms_to_utc(int(candles[-1][0]))
        print(f"  Candles: {len(candles)} fetched  [{first_t}  -->  {last_t}]")


def log_result(result, close_price, diag: dict, direction: str) -> None:
    """Print evaluation outcome with full diagnostic detail."""
    print()

    skipped = diag["candles_skipped"]
    checked = diag["candles_checked"]
    print(f"  Skipped {skipped} pre-signal candle(s), checked {checked} candle(s)")

    # Entry status
    if diag["entry_confirmed"]:
        print(f"  Entry confirmed  : {diag['entry_candle']}")
    else:
        print(f"  Entry confirmed  : NO  — price never reached entry level")

    # Result
    if result == "win":
        print(f"  RESULT           : WIN  (TP hit @ {close_price:,.4f})")
        print(f"  Triggered candle : {diag['result_candle']}")
        print(f"    Candle H={diag['result_candle_h']:,.4f}  L={diag['result_candle_l']:,.4f}")

    elif result == "loss":
        print(f"  RESULT           : LOSS  (SL hit @ {close_price:,.4f})")
        print(f"  Triggered candle : {diag['result_candle']}")
        print(f"    Candle H={diag['result_candle_h']:,.4f}  L={diag['result_candle_l']:,.4f}")

    elif result == "expired":
        print(f"  RESULT           : EXPIRED  (no breach in {SIGNAL_EXPIRY_DAYS} days)")

    else:  # still pending
        lc  = diag["last_close"]
        dsl = diag["dist_to_sl_pct"]
        dtp = diag["dist_to_tp_pct"]
        print(f"  RESULT           : PENDING")
        print(f"  Last candle      : {diag['last_candle_time']}")
        if lc is not None:
            print(f"  Last close price : {lc:,.4f}")
        if dsl is not None and dtp is not None:
            sl_sign = "+" if dsl > 0 else ""
            tp_sign = "+" if dtp > 0 else ""
            print(f"  Distance to SL   : {sl_sign}{dsl:.2f}%   (SL {'below' if direction=='long' else 'above'} current price)")
            print(f"  Distance to TP   : {tp_sign}{dtp:.2f}%   (TP {'above' if direction=='long' else 'below'} current price)")


# ── main handler ──────────────────────────────────────────────────────────────

def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    print(f"\n[check_signals] Run started at {ms_to_utc(now_ms())}")
    print(f"[check_signals] All timestamps below are UTC\n")

    response = (
        supabase.table("trade_signals")
        .select("*")
        .eq("result", "pending")
        .execute()
    )
    signals = response.data
    print(f"[check_signals] {len(signals)} pending signal(s) found")

    stats = {"checked": len(signals), "updated": 0, "still_pending": 0, "errors": []}

    for signal in signals:
        pair      = signal["pair"]
        direction = signal["direction"]
        sid       = signal["id"]

        try:
            signal_ms = iso_to_ms(signal["timestamp"])
            candles   = fetch_candles(pair, signal_ms)

            log_signal_header(signal, signal_ms, candles)

            result, close_price, diag = evaluate_signal(signal, candles, signal_ms)

            log_result(result, close_price, diag, direction)

            if result:
                update_payload = {"result": result}
                if close_price is not None:
                    update_payload["close_price"] = close_price
                supabase.table("trade_signals").update(update_payload).eq("id", sid).execute()
                print(f"  Supabase updated  -> result={result}")
                stats["updated"] += 1
            else:
                stats["still_pending"] += 1

        except requests.HTTPError as exc:
            msg = f"{pair} ({sid}): Binance HTTP {exc.response.status_code}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair} ({sid}): {exc}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)

    # ── 3-month TTL cleanup ───────────────────────────────────────────────────
    # Delete any signals (any result) whose timestamp is older than 90 days.
    # This mirrors what pg_cron does inside Supabase — keeping both means the
    # data is cleaned whether this script runs or not.
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        deleted = (
            supabase.table("trade_signals")
            .delete()
            .lt("timestamp", cutoff)
            .execute()
        )
        n_deleted = len(deleted.data) if deleted.data else 0
        print(f"\n  [TTL]  Deleted {n_deleted} signal(s) older than 90 days  (cutoff: {cutoff[:10]})")
        stats["deleted_old"] = n_deleted
    except Exception as exc:
        print(f"\n  [TTL ERR]  Cleanup failed: {exc}")
        stats["deleted_old"] = 0

    print(f"\n{SEP}")
    print(f"[check_signals] Done at {ms_to_utc(now_ms())}")
    print(f"  Updated      : {stats['updated']}")
    print(f"  Pending      : {stats['still_pending']}")
    print(f"  Deleted >90d : {stats.get('deleted_old', 0)}")
    print(f"  Errors       : {len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"    - {e}")

    return {"statusCode": 200, "body": json.dumps(stats)}


if __name__ == "__main__":
    result = handler()
    print("\n" + json.dumps(json.loads(result["body"]), indent=2))
