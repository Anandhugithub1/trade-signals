"""
generate_signals — creates trade signals for top 15 crypto pairs by market cap.

NOTE: Gold (XAUUSDT) and Silver (XAGUSDT) commodity perpetuals are dropped for
now — their perpetual futures markets are thinner and more prone to price
manipulation than major crypto pairs, which skews the technical indicators.

═══════════════════════════════════════════════════════════════════
 DATA SOURCES  (all free, no API keys required)
═══════════════════════════════════════════════════════════════════
  Candles        Binance Futures → Bybit → OKX  (geo-fallback chain)
  Sentiment      Alternative.me Fear & Greed Index  (dashboard breadth only,
                 see _pair_trend_direction() — no longer a trading vote input)
  Derivatives    OKX funding rate + long/short ratio  (per pair, used by
                 donchian.py/mean_reversion.py's own logic where relevant)

═══════════════════════════════════════════════════════════════════
 ENGINES
═══════════════════════════════════════════════════════════════════
  donchian.py        — 55-bar channel breakout, 4h bars, 3R target.
                        Trend-following: needs only ~25% win rate to break
                        even. See donchian.py's own docstring for full
                        strategy + backtest numbers + HONEST LIMITS.
  mean_reversion.py   — RSI + Bollinger Band range-fade, 4h bars, ~1:1
                        target, ADX<20 gate (the OPPOSITE of a trend
                        filter — it wants the ABSENCE of a trend). See
                        mean_reversion.py's own docstring for full
                        strategy + backtest numbers + HONEST LIMITS.

REMOVED: the original vote-based momentum engine ("legacy") was retired —
its own backtest showed a thin, largely fee-consumed edge (35.2% win rate
against a fixed 2R target, PF 1.09) and was replaced by the two engines
above. All of its historical trade_signals rows were exported to CSV
(test_scripts/_exports/) before deletion; see git history for the removed
analyze_pair() implementation if it's ever needed for reference.

Trigger: every 4h via GitHub Actions cron. Max 3 signals/day PER ENGINE
(donchian + mean_reversion = 6/day max).
"""

import json
import os
import time
import requests
import numpy as np
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from google.oauth2 import service_account
import google.auth.transport.requests

from donchian import analyze_donchian
from mean_reversion import analyze_mean_reversion

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── config ────────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# Firebase service account — two ways to supply credentials:
#   Local dev  : FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
#   GitHub CI  : FIREBASE_SERVICE_ACCOUNT_JSON=<entire JSON as one-line secret>
def _load_firebase_sa() -> str:
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if path and os.path.isfile(path):
        with open(path) as f:
            return f.read()
    return os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")

FIREBASE_SA_JSON = _load_firebase_sa()

BINANCE_FUTURES  = "https://fapi.binance.com/fapi/v1/klines"
BYBIT_KLINES     = "https://api.bybit.com/v5/market/kline"
OKX_KLINES       = "https://www.okx.com/api/v5/market/candles"
FEAR_GREED_URL   = "https://api.alternative.me/fng/?limit=1"

_HEADERS = {"User-Agent": "TradePilot/1.0 signal-bot"}


def _retry(fn, retries: int = 3, backoff: float = 1.5, label: str = ""):
    """
    Call fn() up to `retries` times with exponential backoff.
    Only retries on transient errors (network / 5xx).  Raises on final failure.
    """
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(retries):
        try:
            return fn()
        except requests.HTTPError as exc:
            # Don't retry on 4xx (geo-block, bad request) — they won't fix themselves
            if exc.response is not None and exc.response.status_code < 500:
                raise
            last_exc = exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        except Exception as exc:
            raise   # unknown error — don't retry

        wait = backoff * (2 ** attempt)
        lbl  = f" [{label}]" if label else ""
        print(f"  [RETRY]{lbl} attempt {attempt + 1}/{retries} failed — retrying in {wait:.1f}s")
        time.sleep(wait)

    raise last_exc

# Top crypto by market cap — stablecoins excluded.
# All available on Binance/Bybit/OKX USDT-M perpetual futures.
# Gold (XAUUSDT) / Silver (XAGUSDT) intentionally dropped — see module docstring.
# BNBUSDT, TRXUSDT, AVAXUSDT, LINKUSDT dropped: they were the consistently
# weakest performers across both 9-month and 2-year backtests (~23-31% win
# rate vs ~40-54% for the kept pairs). See test_scripts.
# BTCUSDT dropped 2026-08-05: 12.5% win rate over 8 closed live trades, the
# worst of any pair with a meaningful sample. Small n, so this is a judgement
# call on live results rather than a statistically settled one — re-add if a
# longer backtest disagrees.
TOP_PAIRS = [
    "ETHUSDT",  "SOLUSDT",  "XRPUSDT",  "ADAUSDT",               # 1–4
    "DOGEUSDT", "TONUSDT",  "DOTUSDT",  "LTCUSDT",  "BCHUSDT",   # 5–9
    "UNIUSDT",                                                    # 10
]

# ── Engine tags (written to the `strategy` column) ────────────────────────────
# Two engines run side by side so live results can decide between them:
#   donchian       — channel breakout (4h bars): 30.0% win, PF 1.27 backtested
#   mean_reversion — range-fade (4h bars): 52.5% win rate / PF 1.11 backtested,
#                    ~73 trades/yr — a genuinely different mechanism, not a
#                    tuned variant of a trend-following approach.
# Donchian is prioritised for the daily slots; see Pass 2.
DONCHIAN_TAG       = "donchian"
MEAN_REVERSION_TAG = "mean_reversion"
LEGACY_TAG         = "legacy"   # retired; kept only as the `held_by` fallback
                                 # default for any stray pre-existing row

# Per-ENGINE daily cap, not a shared pool: 3 donchian + 3 mean_reversion =
# 6/day max. A shared cap meant the prioritised engine took every slot it
# qualified for and the other got only leftovers, so each engine's sample
# size depended on how busy the other happened to be. Separate caps let both
# accumulate trades on their own merit, which is the whole point of running
# them side by side.
MAX_SIGNALS_PER_ENGINE = 3
MAX_SIGNALS            = MAX_SIGNALS_PER_ENGINE * 2   # 6 — used for logging

CANDLE_LIMIT  = 300    # kept for any script still importing it; no longer
                        # used by this module directly since analyze_pair()
                        # (the only caller) was removed
SEP = "-" * 60


# ── technical indicators ──────────────────────────────────────────────────────

def _ema_array(data: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.empty_like(data)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = data[i] * k + out[i - 1] * (1 - k)
    return out


def calc_ema(close: np.ndarray, period: int) -> float:
    return float(_ema_array(close, period)[-1])


def calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """
    Average Directional Index (0–100) — measures TREND STRENGTH (not direction).
      ADX >= 25  strong trend  (momentum strategies work here)
      ADX <  20  ranging/choppy (momentum whipsaws — sit out)
    Uses Wilder's smoothing, the standard implementation.
    """
    high  = high.astype(float)
    low   = low.astype(float)
    close = close.astype(float)

    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    up   = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    def _wilder(x: np.ndarray, n: int) -> np.ndarray:
        out = np.zeros(len(x))
        if len(x) < n:
            return out
        out[n - 1] = x[:n].sum()
        for i in range(n, len(x)):
            out[i] = out[i - 1] - out[i - 1] / n + x[i]
        return out

    tr_s  = _wilder(tr, period)
    pdm_s = _wilder(plus_dm, period)
    mdm_s = _wilder(minus_dm, period)

    plus_di  = 100 * np.divide(pdm_s, tr_s, out=np.zeros_like(tr_s), where=tr_s != 0)
    minus_di = 100 * np.divide(mdm_s, tr_s, out=np.zeros_like(tr_s), where=tr_s != 0)
    di_sum   = plus_di + minus_di
    dx       = 100 * np.abs(plus_di - minus_di) / np.where(di_sum == 0, 1, di_sum)
    return float(np.mean(dx[-period:]))


def _okx_symbol(pair: str) -> str:
    """BTCUSDT → BTC-USDT  (OKX instId format)"""
    return pair[:-4] + "-USDT"


def fetch_candles(symbol: str, interval: str = "4h") -> list:
    """
    Fetch OHLCV candles — three-provider fallback chain. Both remaining
    engines (donchian, mean_reversion) run on 4h bars.

    All three share the same index layout:
      [0] open_time_ms  [1] open  [2] high  [3] low  [4] close  [5] volume
    Bybit and OKX return newest-first so their results are reversed.

    Provider chain:
      1. Binance Futures  fapi.binance.com  — blocked in US & India (451)
      2. Bybit Futures    api.bybit.com     — blocked on Azure cloud IPs (403)
      3. OKX              www.okx.com       — US-accessible, no geo-block ✓
    """
    # Each provider spells the same interval differently.
    binance_iv, bybit_iv, okx_iv = {
        "1h": ("1h", "60", "1H"),
        "4h": ("4h", "240", "4H"),
    }[interval]

    # Ask for the provider maximum so both engines' EMA200 regime filters
    # (which alone need 200 bars of history) have real runway.
    limit = 1000

    # 1. Binance Futures
    try:
        r = requests.get(
            BINANCE_FUTURES,
            params={"symbol": symbol, "interval": binance_iv, "limit": limit},
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
                    "interval": bybit_iv, "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return list(reversed(r.json()["result"]["list"]))
        print(f"  [WARN] Bybit {r.status_code} for {symbol} — trying OKX")
    except Exception as e:
        print(f"  [WARN] Bybit error for {symbol} ({e}) — trying OKX")

    # 3. OKX (US-accessible, identical index format, no geo-block)
    r = requests.get(
        OKX_KLINES,
        params={"instId": _okx_symbol(symbol), "bar": okx_iv, "limit": limit},
        headers=_HEADERS, timeout=10,
    )
    r.raise_for_status()
    return list(reversed(r.json()["data"]))   # OKX newest-first → reverse


def is_stale_feed(candles: list, lookback: int = 30) -> bool:
    """
    True when a feed has flatlined — the same close for `lookback` bars.

    A delisted or halted pair keeps returning candles, but with a frozen
    price. Every indicator then degenerates: ATR is 0, the Donchian channel
    has zero width, and EMAs converge on the constant. TONUSDT is currently
    in this state (identical close for 60+ bars on both 1h and 4h), which
    would silently feed garbage into both engines rather than erroring.
    """
    if len(candles) < lookback:
        return False
    closes = {float(c[4]) for c in candles[-lookback:]}
    return len(closes) <= 1


def get_live_price(symbol: str) -> float | None:
    """
    Fetch the real-time last-traded price from ticker APIs.
    Used as the signal entry price instead of the stale candle close,
    which can lag by up to 1h when the candle just opened.

    Same provider fallback chain as fetch_candles:
      1. Binance Futures  (geo-blocked in some regions)
      2. Bybit Futures    (blocked on some cloud IPs)
      3. OKX              (US-accessible, always works from GitHub Actions)
    Returns None if all providers fail — caller falls back to candle close.
    """
    # 1. Binance Futures ticker
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": symbol}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass

    # 2. Bybit Futures ticker
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": symbol}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            items = r.json().get("result", {}).get("list", [])
            if items:
                return float(items[0]["lastPrice"])
    except Exception:
        pass

    # 3. OKX ticker
    try:
        r = requests.get(
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": _okx_symbol(symbol) + "-SWAP"}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200 and r.json().get("data"):
            return float(r.json()["data"][0]["last"])
    except Exception:
        pass

    return None   # all providers failed — caller uses candle close


# ── external sentiment ────────────────────────────────────────────────────────

def get_fear_greed() -> tuple[int, int, str]:
    """
    Returns (vote, raw_value, label).
    vote:      +1 extreme fear (contrarian bullish), -1 extreme greed, 0 neutral
    raw_value: 0-100 integer from the Fear & Greed API
    """
    try:
        r = requests.get(FEAR_GREED_URL, timeout=5)
        d = r.json()["data"][0]
        val   = int(d["value"])
        label = d["value_classification"]
        if val <= 25:
            return 1, val, f"Extreme Fear ({val}) — contrarian bullish"
        if val >= 75:
            return -1, val, f"Extreme Greed ({val}) — contrarian bearish"
        return 0, val, f"Neutral ({val} — {label})"
    except Exception as exc:
        return 0, -1, f"Fear/Greed unavailable ({exc})"


# ── market breadth (dashboard sentiment tally only — NOT a trading signal) ────

def _pair_trend_direction(candles: list) -> int:
    """Lightweight, engine-agnostic per-pair trend read: ADX(14) confirms a
    real trend exists, EMA50/EMA200 stack gives its direction. Returns
    +1 (bull) / -1 (bear) / 0 (no confirmed trend), used ONLY to feed the
    dashboard's bullish/bearish % breadth chart (_upsert_sentiment) — this
    never generates a trade signal, unlike the retired analyze_pair()."""
    if len(candles) < 210:
        return 0
    close = np.array([float(c[4]) for c in candles])
    high  = np.array([float(c[2]) for c in candles])
    low   = np.array([float(c[3]) for c in candles])

    if calc_adx(high, low, close) < 20:
        return 0
    price  = close[-1]
    ema50  = calc_ema(close, 50)
    ema200 = calc_ema(close, 200)
    if price > ema50 > ema200:
        return 1
    if price < ema50 < ema200:
        return -1
    return 0


# ── push notifications ───────────────────────────────────────────────────────

def _get_fcm_access_token() -> tuple[str, str]:
    """
    Returns (Bearer token, project_id) using the Firebase service account JSON.
    The JSON is stored as a string in FIREBASE_SERVICE_ACCOUNT_JSON env var.
    """
    sa_info   = json.loads(FIREBASE_SA_JSON)
    project   = sa_info["project_id"]
    creds     = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token, project


def _send_push_notifications(supabase, inserted_signals: list) -> None:
    """
    Send FCM V1 push notifications to all enabled devices.

    Uses the FCM HTTP v1 API (the modern API — legacy was deprecated June 2024).
    Requires FIREBASE_SERVICE_ACCOUNT_JSON env var containing the full
    service account JSON downloaded from:
      Firebase Console → Project Settings → Service Accounts → Generate new private key

    Sends one request per device token (V1 API requirement — no batch endpoint).
    Silently skips if env var is not configured.
    """
    if not FIREBASE_SA_JSON or not inserted_signals:
        if not FIREBASE_SA_JSON:
            print("  [FCM]  FIREBASE_SERVICE_ACCOUNT_JSON not set — skipping push")
        return

    try:
        # Fetch all enabled device tokens from Supabase
        res = (
            supabase.table("notification_tokens")
            .select("device_token")
            .eq("is_enabled", True)
            .execute()
        )
        tokens = [r["device_token"] for r in (res.data or [])]
        if not tokens:
            print("  [FCM]  No enabled devices — skipping push")
            return

        # Get short-lived OAuth2 access token
        bearer, project_id = _get_fcm_access_token()
        url     = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

        # Build notification content
        n      = len(inserted_signals)
        pairs  = ", ".join(s["pair"] for s in inserted_signals[:3])
        plural = "s" if n > 1 else ""
        title  = "New Trade Signal" + ("s" if n > 1 else "")
        body   = f"{n} new signal{plural}: {pairs}"

        # V1 API: one request per token
        ok = fail = 0
        for token in tokens:
            try:
                resp = requests.post(url, headers=headers, json={
                    "message": {
                        "token": token,
                        "notification": {"title": title, "body": body},
                        "data": {"type": "new_signal", "count": str(n)},
                        "android": {"priority": "high"},
                        "apns": {"payload": {"aps": {"sound": "default", "badge": n}}},
                    }
                }, timeout=8)
                if resp.status_code == 200:
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1

        print(f"  [FCM]  Sent to {len(tokens)} device(s) — {ok} ok / {fail} failed")

    except Exception as exc:
        print(f"  [FCM ERR]  {exc}")


# ── market sentiment ─────────────────────────────────────────────────────────

def _upsert_sentiment(supabase, analyses: list, fg_raw: int, fg_label: str) -> None:
    """
    Compute today's market sentiment from all pair analyses and upsert
    into the market_sentiment table (one row per day, keyed on date).

    Sentiment percentages are derived from how many pairs are bullish/bearish.
    Active longs/shorts are read from the current pending signals.
    """
    if not analyses:
        return

    bullish = sum(1 for a in analyses if a.get("score", 0) > 0)
    bearish = sum(1 for a in analyses if a.get("score", 0) < 0)
    neutral = len(analyses) - bullish - bearish
    total   = len(analyses)

    bullish_pct = round(bullish / total * 100)
    bearish_pct = round(bearish / total * 100)
    neutral_pct = max(0, 100 - bullish_pct - bearish_pct)

    dominant = "bullish" if bullish > bearish else "bearish" if bearish > bullish else "neutral"

    # Count active longs and shorts from pending signals
    pending = (
        supabase.table("trade_signals")
        .select("direction")
        .eq("result", "pending")
        .execute()
    ).data or []
    active_longs  = sum(1 for s in pending if s.get("direction") == "long")
    active_shorts = sum(1 for s in pending if s.get("direction") == "short")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "date":             today,
        "bullish_pct":      bullish_pct,
        "neutral_pct":      neutral_pct,
        "bearish_pct":      bearish_pct,
        "fear_greed_value": fg_raw if fg_raw >= 0 else None,
        "fear_greed_label": fg_label,
        "active_longs":     active_longs,
        "active_shorts":    active_shorts,
        "dominant":         dominant,
    }

    supabase.table("market_sentiment").upsert(row, on_conflict="date").execute()

    print(f"\n  [SENTIMENT]  {today}  Bullish={bullish_pct}%  Neutral={neutral_pct}%  Bearish={bearish_pct}%  "
          f"Dominant={dominant}  F&G={fg_raw}  Longs={active_longs}  Shorts={active_shorts}")


# ── main handler ──────────────────────────────────────────────────────────────

def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    now_utc   = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[generate_signals] Started at {today_str}")

    # ── Daily cap check ───────────────────────────────────────────────────────
    # Count signals already created today (midnight UTC → now).
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_rows  = (
        supabase.table("trade_signals")
        .select("id, strategy")
        .gte("timestamp", today_start)
        .execute()
    ).data or []

    # Each engine has its own budget, so count them separately.
    today_by_engine = {
        DONCHIAN_TAG: sum(1 for r in today_rows
                          if (r.get("strategy") or LEGACY_TAG) == DONCHIAN_TAG),
        MEAN_REVERSION_TAG: sum(1 for r in today_rows
                          if (r.get("strategy") or LEGACY_TAG) == MEAN_REVERSION_TAG),
    }
    donchian_slots = max(0, MAX_SIGNALS_PER_ENGINE - today_by_engine[DONCHIAN_TAG])
    mr_slots       = max(0, MAX_SIGNALS_PER_ENGINE - today_by_engine[MEAN_REVERSION_TAG])
    today_count    = len(today_rows)
    slots_left     = donchian_slots + mr_slots

    print(f"[generate_signals] Signals today: {today_count} / {MAX_SIGNALS}  "
          f"(donchian {today_by_engine[DONCHIAN_TAG]}/{MAX_SIGNALS_PER_ENGINE}, "
          f"mean_reversion {today_by_engine[MEAN_REVERSION_TAG]}/{MAX_SIGNALS_PER_ENGINE})")

    if slots_left == 0:
        print(f"[generate_signals] Both engines at their daily cap of "
              f"{MAX_SIGNALS_PER_ENGINE} — skipping run.\n")
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "today_count": today_count})}

    print(f"[generate_signals] Room for {donchian_slots} donchian + "
          f"{mr_slots} mean_reversion signal(s) this run.\n")

    # ── Global indicators (fetched once, applied to all pairs) ───────────────
    # F&G is kept only for the dashboard's sentiment tally (_upsert_sentiment)
    # — neither remaining engine uses it as a trading input.
    fg_score, fg_raw, fg_reason = get_fear_greed()
    fg_label = fg_reason.split(" — ")[0] if " — " in fg_reason else fg_reason
    print(f"  Fear & Greed  : {fg_reason}\n")

    stats = {
        "analysed": 0, "inserted": 0,
        "no_signal": 0,
        "skipped_existing": 0, "errors": [],
        "today_count": today_count,
        "slots_left": slots_left,
    }

    # ── Pass 1: analyse all pairs, collect valid candidates ───────────────────
    breadth = []   # {"pair": ..., "score": +1/-1/0} for the sentiment tally only
    donchian_candidates = []   # breakout signals from the trend-following engine
    mr_candidates       = []   # range-fade signals from the mean-reversion engine

    for pair in TOP_PAIRS:
        try:
            # A pending position blocks only the ENGINE that opened it, not
            # the pair. Skipping the whole pair meant a position from one
            # engine made the other blind to that symbol entirely, so the
            # two could not be compared fairly.
            existing = (
                supabase.table("trade_signals")
                .select("id, timestamp, strategy")
                .eq("pair", pair)
                .eq("result", "pending")
                .execute()
            ).data or []
            held_by = {r.get("strategy") or LEGACY_TAG for r in existing}

            # Donchian + mean-reversion both run on the SAME 4h candles,
            # fetched once and shared between them.
            d4 = None
            if DONCHIAN_TAG not in held_by or MEAN_REVERSION_TAG not in held_by:
                try:
                    d4 = fetch_candles(pair, interval="4h")
                    if is_stale_feed(d4):
                        print(f"  [STALE] {pair:<12} — price frozen, feed likely "
                              f"delisted/halted; skipping all engines")
                        stats["stale_feed"] = stats.get("stale_feed", 0) + 1
                        d4 = None
                except Exception as exc:
                    print(f"  [4H FETCH ERR] {pair}: {exc}")
                    d4 = None

            if d4 is None:
                stats["no_signal"] += 1
                continue

            stats["analysed"] += 1
            breadth.append({"pair": pair, "score": _pair_trend_direction(d4)})

            if DONCHIAN_TAG in held_by:
                print(f"  [SKIP] {pair:<12} — donchian position already open")
            else:
                try:
                    dsig = analyze_donchian(pair, d4, get_live_price(pair))
                    if dsig:
                        donchian_candidates.append(dsig)
                        print(f"  [DONCHIAN] {pair:<12} {dsig['direction'].upper():<5} "
                              f"entry={dsig['entry']:,.4f} "
                              f"({dsig['_rank']:.2f} ATR beyond channel)")
                except Exception as exc:
                    print(f"  [DONCHIAN ERR] {pair}: {exc}")

            if MEAN_REVERSION_TAG in held_by:
                print(f"  [SKIP] {pair:<12} — mean_reversion position already open")
                stats["skipped_existing"] += 1
            else:
                try:
                    mrsig = analyze_mean_reversion(pair, d4, get_live_price(pair))
                    if mrsig:
                        mr_candidates.append(mrsig)
                        print(f"  [MEAN-REV] {pair:<12} {mrsig['direction'].upper():<5} "
                              f"entry={mrsig['entry']:,.4f} rr=1:{mrsig['rr_ratio']:.2f}")
                except Exception as exc:
                    print(f"  [MEAN-REV ERR] {pair}: {exc}")

        except requests.HTTPError as exc:
            msg = f"{pair}: API HTTP {exc.response.status_code} (all providers failed)"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair}: {exc}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)

    # ── Pass 2: rank within each engine's own budget ─────────────────────────
    # The engines don't compete for slots — each has MAX_SIGNALS_PER_ENGINE of
    # its own, so neither engine's sample size depends on how active the
    # other happens to be. Both are tagged in the `strategy` column so live
    # results can settle which one actually earns its place.
    donchian_candidates.sort(key=lambda s: -s["_rank"])
    mr_candidates.sort(key=lambda s: -s["_rank"])

    new_take = donchian_candidates[:donchian_slots]

    # Never open two positions on the same pair from different engines: if
    # Donchian is taking a pair this run, mean_reversion stands down on it.
    # Donchian wins the tie because it is the measurably better strategy by
    # backtested PF (1.27 vs mean_reversion's 1.11 — see donchian.py /
    # mean_reversion.py).
    donchian_pairs = {s["pair"] for s in new_take}
    mr_eligible = [s for s in mr_candidates if s["pair"] not in donchian_pairs]
    mr_take = mr_eligible[:mr_slots]

    to_insert = [{"signal": s, "engine": DONCHIAN_TAG} for s in new_take] \
        + [{"signal": s, "engine": MEAN_REVERSION_TAG} for s in mr_take]
    overflow = mr_eligible[mr_slots:]

    print(f"\n  Engine mix: {len(new_take)}/{donchian_slots} donchian + "
          f"{len(mr_take)}/{mr_slots} mean_reversion  "
          f"[{len(donchian_candidates)} / {len(mr_candidates)} qualified]")

    if overflow:
        print(f"\n{SEP}")
        print(f"  Dropped (mean_reversion engine at its cap of {MAX_SIGNALS_PER_ENGINE}/day "
              f"— {today_by_engine[MEAN_REVERSION_TAG]} already today):")
        for s in overflow:
            print(f"    {s['pair']:<12}  {s['direction'].upper():<5}  rr=1:{s['rr_ratio']:.2f}  — not inserted")

    # ── Pass 3: insert the winners ────────────────────────────────────────────
    if to_insert:
        print(f"\n{SEP}")
        print(f"  Inserting top {len(to_insert)} signal(s)  (max={MAX_SIGNALS}):\n")

    for analysis in to_insert:
        sig = dict(analysis["signal"])          # copy: we mutate before insert
        engine = analysis.get("engine", DONCHIAN_TAG)
        sig["strategy"] = engine
        sig.pop("_rank", None)                  # ranking helper, not a column
        try:
            supabase.table("trade_signals").insert(sig).execute()
            print(f"  [DB OK]  {sig['pair']:<12}  {sig['direction'].upper():<5}  "
                  f"[{engine}]  "
                  f"RR=1:{sig['rr_ratio']:.2f}  "
                  f"entry=${sig['entry']:,.4f}  id={sig['id'][:8]}...")
            stats["inserted"] += 1
            stats[f"inserted_{engine}"] = stats.get(f"inserted_{engine}", 0) + 1
        except Exception as exc:
            msg = f"{sig['pair']} insert failed: {exc}"
            print(f"  [DB ERR] {msg}")
            stats["errors"].append(msg)

    # ── Pass 4: push notifications ────────────────────────────────────────────
    inserted_sigs = [a["signal"] for a in to_insert if a["signal"]["pair"] not in
                     [e.split(" ")[0] for e in stats["errors"]]]
    _send_push_notifications(supabase, inserted_sigs[:stats["inserted"]])

    # ── Pass 5: upsert market sentiment ──────────────────────────────────────
    try:
        _upsert_sentiment(supabase, breadth, fg_raw, fg_label)
    except Exception as exc:
        print(f"\n  [SENTIMENT ERR] {exc}")

    print(f"\n{SEP}")
    print(f"[generate_signals] Done")
    print(f"  Inserted         : {stats['inserted']}  "
          f"(donchian {stats.get('inserted_' + DONCHIAN_TAG, 0)}, "
          f"mean_reversion {stats.get('inserted_' + MEAN_REVERSION_TAG, 0)}; "
          f"cap {MAX_SIGNALS_PER_ENGINE}/engine, today total="
          f"{today_count + stats['inserted']})")
    print(f"  No signal        : {stats['no_signal']}")
    print(f"  Already pending  : {stats['skipped_existing']}")
    print(f"  Errors           : {len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"    - {e}")

    return {"statusCode": 200, "body": json.dumps(stats)}


if __name__ == "__main__":
    result = handler()
    print("\n" + json.dumps(json.loads(result["body"]), indent=2))
