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
import time
import requests
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from google.oauth2 import service_account
import google.auth.transport.requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── config ────────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

def _load_firebase_sa() -> str:
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if path and os.path.isfile(path):
        with open(path) as f:
            return f.read()
    return os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")

FIREBASE_SA_JSON = _load_firebase_sa()

BINANCE_FUTURES    = "https://fapi.binance.com/fapi/v1/klines"   # USDT-M Futures (blocked in US/India)
BYBIT_KLINES       = "https://api.bybit.com/v5/market/kline"     # Bybit perpetual (blocked on Azure)
OKX_KLINES         = "https://www.okx.com/api/v5/market/candles" # OKX — US-accessible, no geo-block
_HEADERS           = {"User-Agent": "TradePilot/1.0 signal-bot"}


def _retry(fn, retries: int = 3, backoff: float = 1.5, label: str = ""):
    """Retry on transient network / 5xx errors with exponential backoff."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(retries):
        try:
            return fn()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code < 500:
                raise   # 4xx — geo-block / bad request, won't fix on retry
            last_exc = exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        except Exception:
            raise

        wait = backoff * (2 ** attempt)
        lbl  = f" [{label}]" if label else ""
        print(f"  [RETRY]{lbl} attempt {attempt + 1}/{retries} failed — retrying in {wait:.1f}s")
        time.sleep(wait)
    raise last_exc
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


def _okx_symbol(pair: str) -> str:
    """BTCUSDT → BTC-USDT  (OKX instId format)"""
    return pair[:-4] + "-USDT"


def fetch_candles(symbol: str, signal_ms: int) -> list:
    """
    Fetch 1-hour OHLCV candles — three-provider fallback chain.

    All three share the same index layout:
      [0] open_time_ms  [2] high  [3] low  [4] close  [5] volume
    Bybit and OKX return newest-first so their results are reversed.

    Provider chain:
      1. Binance Futures  fapi.binance.com  — blocked in US & India (451)
      2. Bybit Futures    api.bybit.com     — blocked on Azure cloud IPs (403)
      3. OKX              www.okx.com       — US-accessible, no geo-block ✓
    """
    start = (signal_ms // HOUR_MS) * HOUR_MS
    end   = now_ms()

    # 1. Binance Futures
    try:
        r = requests.get(
            BINANCE_FUTURES,
            params={"symbol": symbol, "interval": "1h",
                    "startTime": start, "endTime": end, "limit": 500},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        print(f"  [WARN] Binance Futures {r.status_code} for {symbol} — trying Bybit")
    except Exception as e:
        print(f"  [WARN] Binance Futures error for {symbol} ({e}) — trying Bybit")

    # 2. Bybit Futures
    try:
        r = requests.get(
            BYBIT_KLINES,
            params={"category": "linear", "symbol": symbol,
                    "interval": "60", "start": start, "end": end, "limit": 500},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return list(reversed(r.json()["result"]["list"]))
        print(f"  [WARN] Bybit {r.status_code} for {symbol} — trying OKX")
    except Exception as e:
        print(f"  [WARN] Bybit error for {symbol} ({e}) — trying OKX")

    # 3. OKX (US-accessible, identical index format, no geo-block)
    # OKX doesn't support time filtering on candles for 1h in the same way,
    # so we fetch the max and slice to the signal window after.
    r = requests.get(
        OKX_KLINES,
        params={"instId": _okx_symbol(symbol), "bar": "1H", "limit": 500},
        headers=_HEADERS, timeout=10,
    )
    r.raise_for_status()
    return list(reversed(r.json()["data"]))   # OKX newest-first → reverse


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


# ── push notifications ───────────────────────────────────────────────────────

def _fcm_token() -> tuple[str, str] | None:
    """Returns (bearer_token, project_id) or None if not configured."""
    if not FIREBASE_SA_JSON:
        return None
    try:
        sa    = json.loads(FIREBASE_SA_JSON)
        creds = service_account.Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token, sa["project_id"]
    except Exception as exc:
        print(f"  [FCM] token error: {exc}")
        return None


def _notify_signal_result(supabase, signal: dict, result: str, close_price: float | None) -> None:
    """
    Send push notification to all enabled devices when SL or TP is hit.

    WIN  → "BTCUSDT LONG  ✓ Take Profit hit — +1.92%"
    LOSS → "BTCUSDT LONG  ✗ Stop Loss hit  — -2.00%"
    """
    if result not in ("win", "loss"):
        return

    fcm = _fcm_token()
    if not fcm:
        return

    bearer, project_id = fcm

    # Fetch enabled device tokens
    try:
        res    = supabase.table("notification_tokens").select("device_token").eq("is_enabled", True).execute()
        tokens = [r["device_token"] for r in (res.data or [])]
    except Exception:
        tokens = []

    if not tokens:
        return

    pair      = signal["pair"]
    direction = signal["direction"].upper()
    entry     = float(signal.get("entry") or signal.get("entry_price", 0))

    # Calculate P&L %
    pnl_str = ""
    if close_price and entry:
        diff     = close_price - entry
        directed = diff if signal["direction"] == "long" else -diff
        pnl      = (directed / entry) * 100
        pnl_str  = f"  {'+' if pnl >= 0 else ''}{pnl:.2f}%"

    if result == "win":
        title = f"{pair} {direction} — Take Profit Hit"
        body  = f"TP reached at ${close_price:,.4f}{pnl_str}"
    else:
        title = f"{pair} {direction} — Stop Loss Hit"
        body  = f"SL triggered at ${close_price:,.4f}{pnl_str}"

    url     = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

    ok = fail = 0
    for token in tokens:
        try:
            resp = requests.post(url, headers=headers, json={
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "data": {"type": "signal_result", "result": result, "pair": pair},
                    "android": {"priority": "high"},
                    "apns": {"payload": {"aps": {"sound": "default"}}},
                }
            }, timeout=8)
            if resp.status_code == 200:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    tag = "[WIN]" if result == "win" else "[LOSS]"
    print(f"  [FCM] {tag} push sent to {len(tokens)} device(s) — {ok} ok / {fail} failed")


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

    if not signals:
        print(f"[check_signals] No pending signals — nothing to do. Exiting.\n")
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "reason": "no_pending_signals"})}

    stats = {"checked": len(signals), "updated": 0, "still_pending": 0, "errors": []}

    for signal in signals:
        pair      = signal["pair"]
        direction = signal["direction"]
        sid       = signal["id"]

        try:
            signal_ms = iso_to_ms(signal["timestamp"])
            candles   = _retry(lambda: fetch_candles(pair, signal_ms), label=pair)

            log_signal_header(signal, signal_ms, candles)

            result, close_price, diag = evaluate_signal(signal, candles, signal_ms)

            log_result(result, close_price, diag, direction)

            # Always update latest_price — shows current price even for pending signals
            latest = diag.get("last_close")
            if latest is not None:
                _retry(
                    lambda lp=latest: supabase.table("trade_signals")
                        .update({"latest_price": lp}).eq("id", sid).execute(),
                    label=f"latest_price {pair}",
                )

            if result:
                update_payload = {"result": result}
                if close_price is not None:
                    update_payload["close_price"] = close_price
                _retry(
                    lambda: supabase.table("trade_signals")
                        .update(update_payload).eq("id", sid).execute(),
                    label=f"DB update {pair}",
                )
                print(f"  Supabase updated  -> result={result}  latest_price=${latest:,.4f}" if latest else f"  Supabase updated  -> result={result}")

                # Push notification for win/loss
                _notify_signal_result(supabase, signal, result, close_price)

                stats["updated"] += 1
            else:
                print(f"  latest_price updated -> ${latest:,.4f}" if latest else "  latest_price: unavailable")
                stats["still_pending"] += 1

        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            msg  = f"{pair} ({sid}): all candle providers returned HTTP {code}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except TimeoutError as exc:
            msg = f"{pair} ({sid}): request timed out — {exc}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair} ({sid}): {type(exc).__name__}: {exc}"
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
