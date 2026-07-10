"""
generate_signals — creates trade signals for top 15 crypto pairs by market cap.

NOTE: Gold (XAUUSDT) and Silver (XAGUSDT) commodity perpetuals are dropped for
now — their perpetual futures markets are thinner and more prone to price
manipulation than major crypto pairs, which skews the technical indicators.
The is_commodity handling in analyze_pair() is left in place so they can be
re-added later without touching the voting logic.

═══════════════════════════════════════════════════════════════════
 DATA SOURCES  (all free, no API keys required)
═══════════════════════════════════════════════════════════════════
  Candles        Binance Futures → Bybit → OKX  (geo-fallback chain)
  Sentiment      Alternative.me Fear & Greed Index
  Market data    CoinGecko global market cap & dominance
  Derivatives    OKX funding rate + long/short ratio  (per pair)
  Coin news      Google News RSS + CoinDesk RSS
  Macro events   Google News RSS + Reuters  (Fed / rates / wars)

═══════════════════════════════════════════════════════════════════
 STRATEGY  —  regime-filtered momentum (1h timeframe, ~3–4% swings)
═══════════════════════════════════════════════════════════════════
  STEP 1 — REGIME GATE (the core of the system)
     • ADX(14) must be >= 20  → confirms a real trend exists
     • EMA stack must align    → price > EMA50 > EMA200 (up) or the inverse (down)
     • If neither holds → NO SIGNAL. Momentum never trades ranging markets.

  STEP 2 — VOTE (all votes only ever point WITH the confirmed trend)
     Trend engine  : EMA200, EMA50, EMA20/50 cross
     Momentum      : MACD (single vote; crossover just strengthens the reason)
     Volume        : OBV slope, Volume-spike amplifier
     Pullback edge : Oscillators + Bollinger — regime-aware, so an oversold
                     reading in an uptrend is a BUY (never a counter-trend short)
     Positioning   : Funding rate, Long/Short ratio (contrarian)
     Market context: F&G + market-cap + news + macro collapsed into ONE
                     low-weight vote (needs strong net agreement to fire)

  STEP 3 — DECISION
     LONG  when net score >= +4  AND uptrend
     SHORT when net score <= -4  AND downtrend
     Signal strength = |score| / active votes → 60–95 %
       NOTE: this is INDICATOR-AGREEMENT strength (how strongly the votes
       align), NOT a win probability. Backtests over 2 000+ trades show it
       does NOT predict win rate — an 85%-strength signal wins about as
       often as a 75% one. Treat/label it as "how clean the setup is",
       never as "chance this trade wins".

  STEP 4 — ENTRY
     Limit entry at the nearest recent swing low (longs) / swing high
     (shorts) within 1.2x ATR of price — a real reaction level, not an
     arbitrary offset. Falls back to a shallow 0.3x ATR offset if no
     qualifying swing level is nearby (see find_swing_level()).

  STEP 5 — RISK
     TP = fixed 3.5% target (matches 1h momentum swing)
     SL = min(2× ATR, 2.3% cap), then tightened so reward:risk is never < 1:1.5

Trigger: every 4h via GitHub Actions cron. Max 3 signals/day.
"""

import json
import os
import time
import uuid
import requests
import feedparser
import numpy as np
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
OKX_FUNDING      = "https://www.okx.com/api/v5/public/funding-rate"
OKX_LSR          = "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
FEAR_GREED_URL   = "https://api.alternative.me/fng/?limit=1"
GOOGLE_NEWS_RSS  = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q={coin}+cryptocurrency"
COINDESK_RSS     = "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"
REUTERS_RSS      = "https://feeds.reuters.com/reuters/businessNews"

# Macro event RSS feeds — Fed, rates, geopolitics
MACRO_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=fed+meeting+interest+rate+fomc&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=war+sanctions+geopolitical+economy+recession&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.reuters.com/reuters/businessNews",
]

# Keywords that push crypto HIGHER (risk-on, rate easing, stability)
_MACRO_BULL = {
    "rate cut", "dovish", "pivot", "pause hike", "easing", "stimulus",
    "bailout", "ceasefire", "peace deal", "peace talks", "soft landing",
    "inflation cooling", "inflation eased", "rate reduction", "fed cut",
    "interest cut", "quantitative easing", "liquidity", "risk on",
}

# Keywords that push crypto LOWER (risk-off, rate hikes, instability)
_MACRO_BEAR = {
    "rate hike", "hawkish", "tightening", "quantitative tightening",
    "recession", "default", "war escalation", "invasion", "sanctions",
    "banking crisis", "credit crunch", "inflation surge", "stagflation",
    "rate increase", "fed hike", "interest rate rise", "trade war",
    "tariff", "conflict escalation", "military action", "debt ceiling",
}

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
TOP_PAIRS = [
    "BTCUSDT",  "ETHUSDT",  "SOLUSDT",  "XRPUSDT",  "ADAUSDT",   # 1–5
    "DOGEUSDT", "TONUSDT",  "DOTUSDT",  "LTCUSDT",  "BCHUSDT",   # 6–10
    "UNIUSDT",                                                    # 11
]

MIN_BULL_SCORE        = 4    # net bullish votes required for LONG
MIN_BEAR_SCORE        = 4    # net bearish votes required for SHORT
MIN_SIGNAL_STRENGTH   = 72   # signals below this strength % are discarded
MAX_SIGNALS           = 3    # insert at most this many signals per day

# ── Regime filter (momentum needs a trend) ────────────────────────────────────
ADX_TREND_MIN = 20   # ADX below this = ranging/choppy → skip (no momentum edge)

# ── Momentum targets (1h timeframe, ~3–4% swing moves) ────────────────────────
TARGET_TP_PCT = 0.035  # fixed 3.5% take-profit target
ATR_SL_MULT   = 2.0    # SL = 2× ATR (gives a 1h trade room to breathe)
MAX_SL_PCT    = 0.023  # hard SL cap → keeps reward:risk at/above the floor
MIN_RR        = 1.5    # never generate a signal below 1 : 1.5 reward:risk

# Swing support/resistance limit entry: instead of entering at raw market
# price, ask for a fill at the nearest recent swing low (longs) / swing high
# (shorts) — a real level the market has already reacted to, rather than an
# arbitrary ATR offset. Only used if that level is within MAX_DIST_ATR of
# price; otherwise falls back to the shallow 0.3x ATR offset so a signal is
# never skipped outright for lack of a nearby level. Backtested across
# 3/6/9-month windows to beat both market-entry and the old flat-ATR shallow
# limit on expectancy (see test_scripts/sim_sr_limit.py). SL/TP anchor to
# this entry.
SWING_LOOKBACK = 60    # candles to search for a swing level
SWING_ORDER    = 3     # a candle must be the extreme within +/- this many neighbours
MAX_DIST_ATR   = 1.2   # only use the swing level if within this many ATRs of price
ENTRY_ATR_MULT = 0.3   # fallback offset when no qualifying swing level is nearby

CANDLE_LIMIT  = 300    # 300 × 1h ≈ 12.5 days (EMA200 well-converged)
SEP = "-" * 60


# ── technical indicators ──────────────────────────────────────────────────────

def _ema_array(data: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.empty_like(data)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = data[i] * k + out[i - 1] * (1 - k)
    return out


def calc_rsi(close: np.ndarray, period: int = 14) -> float:
    """Wilder's smoothed RSI — uses full history for a stable result."""
    delta  = np.diff(close.astype(float))
    gains  = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    # Seed with simple average over first `period` bars
    avg_g  = np.mean(gains[:period])
    avg_l  = np.mean(losses[:period])
    # Wilder smoothing over remaining bars
    for i in range(period, len(delta)):
        avg_g = (avg_g * (period - 1) + gains[i])  / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def calc_macd(close: np.ndarray):
    """Returns (macd_val, signal_val, hist_now, hist_prev)."""
    ema12 = _ema_array(close, 12)
    ema26 = _ema_array(close, 26)
    macd_line = ema12 - ema26
    sig_line  = _ema_array(macd_line, 9)
    hist      = macd_line - sig_line
    return macd_line[-1], sig_line[-1], hist[-1], hist[-2]


def calc_ema(close: np.ndarray, period: int) -> float:
    return float(_ema_array(close, period)[-1])


def calc_bollinger(close: np.ndarray, period: int = 20):
    """Returns (upper, middle, lower, %B position 0-1)."""
    window = close[-period:]
    mid    = np.mean(window)
    std    = np.std(window)
    upper  = mid + 2 * std
    lower  = mid - 2 * std
    pct_b  = (close[-1] - lower) / (upper - lower) if upper != lower else 0.5
    return upper, mid, lower, float(pct_b)


def find_swing_level(direction: str, price: float, atr: float,
                      high: np.ndarray, low: np.ndarray) -> float | None:
    """Nearest qualifying swing low (long) / swing high (short) within the
    last SWING_LOOKBACK candles, on the favourable side of price. A swing
    point must be the local extreme within +/- SWING_ORDER candles. Returns
    None if no swing point qualifies, or the nearest one is farther than
    MAX_DIST_ATR * ATR from price (too far to be a realistic pullback)."""
    n = len(low)
    lo_win = max(0, n - SWING_LOOKBACK)
    best = None
    best_dist = None

    for i in range(lo_win + SWING_ORDER, n - SWING_ORDER):
        if direction == "long":
            window_lows = low[i - SWING_ORDER: i + SWING_ORDER + 1]
            if low[i] != window_lows.min():
                continue
            level = low[i]
            if level >= price:
                continue
            dist = price - level
        else:
            window_highs = high[i - SWING_ORDER: i + SWING_ORDER + 1]
            if high[i] != window_highs.max():
                continue
            level = high[i]
            if level <= price:
                continue
            dist = level - price

        if best_dist is None or dist < best_dist:
            best, best_dist = level, dist

    if best is None or best_dist > MAX_DIST_ATR * atr:
        return None
    return float(best)


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]),
                   np.abs(low[1:] - close[:-1]))
    )
    return float(np.mean(tr[-period:]))


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


def calc_stoch_rsi(close: np.ndarray, rsi_period: int = 14, stoch_period: int = 14) -> float:
    """Stochastic RSI — 0 (oversold) to 1 (overbought). More sensitive than plain RSI."""
    # Build RSI series for entire close array
    delta = np.diff(close.astype(float))
    gain  = np.where(delta > 0, delta, 0.0)
    loss  = np.where(delta < 0, -delta, 0.0)
    avg_g = np.mean(gain[:rsi_period])
    avg_l = np.mean(loss[:rsi_period])
    rsi_vals = np.empty(len(close))
    rsi_vals[:rsi_period + 1] = np.nan
    for i in range(rsi_period, len(delta)):
        avg_g = (avg_g * (rsi_period - 1) + gain[i]) / rsi_period
        avg_l = (avg_l * (rsi_period - 1) + loss[i]) / rsi_period
        rs = avg_g / avg_l if avg_l != 0 else 1e9
        rsi_vals[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    rsi_clean = rsi_vals[~np.isnan(rsi_vals)]
    if len(rsi_clean) < stoch_period:
        return 0.5
    window = rsi_clean[-stoch_period:]
    lo, hi = window.min(), window.max()
    return float((rsi_clean[-1] - lo) / (hi - lo)) if hi != lo else 0.5


def calc_williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """Williams %R — -100 (oversold) to 0 (overbought)."""
    hh = np.max(high[-period:])
    ll = np.min(low[-period:])
    return float(-100.0 * (hh - close[-1]) / (hh - ll)) if hh != ll else -50.0


def calc_obv_slope(close: np.ndarray, vol: np.ndarray, period: int = 20) -> float:
    """
    On-Balance Volume linear-regression slope over `period` candles.
    Positive = OBV trending up (volume confirming price rise).
    Negative = OBV trending down (volume confirming price fall).
    """
    obv = np.zeros(len(close))
    for i in range(1, len(close)):
        obv[i] = obv[i-1] + (vol[i] if close[i] > close[i-1] else
                              -vol[i] if close[i] < close[i-1] else 0)
    window = obv[-period:]
    x = np.arange(len(window), dtype=float)
    slope = np.polyfit(x, window, 1)[0]
    return float(slope)


def calc_expiry_days(confidence: int, rr_ratio: float) -> int:
    """
    Higher confidence + better RR ratio = longer window to play out.

    Confidence 60-95 and RR 1.0-3.0 each contribute to the window:
      conf_factor  maps 60→0.0, 95→1.0
      rr_factor    maps 1.0→0.0, 3.0→1.0
    Combined (60% conf weight, 40% RR weight) → scales 3–4 days.

    Examples:
      confidence=65, RR=1.5  →  3 days
      confidence=80, RR=2.0  →  3–4 days
      confidence=90, RR=2.5  →  4 days
    """
    conf_factor = min((confidence - 60) / 35.0, 1.0)
    rr_factor   = min(max((rr_ratio - 1.0) / 2.0, 0.0), 1.0)
    factor      = conf_factor * 0.6 + rr_factor * 0.4
    days        = round(3 + factor * 1)            # 3 → 4
    return max(3, min(4, int(days)))


def volume_ratio(vol: np.ndarray, period: int = 20) -> float:
    avg = np.mean(vol[-period - 1:-1])
    return float(vol[-1] / avg) if avg > 0 else 1.0


def _okx_symbol(pair: str) -> str:
    """BTCUSDT → BTC-USDT  (OKX instId format)"""
    return pair[:-4] + "-USDT"


def fetch_candles(symbol: str) -> list:
    """
    Fetch 4-hour OHLCV candles — three-provider fallback chain.

    All three share the same index layout:
      [0] open_time_ms  [1] open  [2] high  [3] low  [4] close  [5] volume
    Bybit and OKX return newest-first so their results are reversed.

    Provider chain:
      1. Binance Futures  fapi.binance.com  — blocked in US & India (451)
      2. Bybit Futures    api.bybit.com     — blocked on Azure cloud IPs (403)
      3. OKX              www.okx.com       — US-accessible, no geo-block ✓
    """
    # 1. Binance Futures
    try:
        r = requests.get(
            BINANCE_FUTURES,
            params={"symbol": symbol, "interval": "1h", "limit": CANDLE_LIMIT},
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
                    "interval": "60", "limit": CANDLE_LIMIT},
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
        params={"instId": _okx_symbol(symbol), "bar": "1H", "limit": CANDLE_LIMIT},
        headers=_HEADERS, timeout=10,
    )
    r.raise_for_status()
    return list(reversed(r.json()["data"]))   # OKX newest-first → reverse


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


_BULL_WORDS = {"surge","rally","bullish","breakout","gain","high","pump","rise","soar","record","up","green","buy","long","upside","positive","adoption","partnership","launch","approve","etf"}
_BEAR_WORDS = {"crash","drop","bearish","fall","dump","low","fear","plunge","sell","short","ban","hack","fraud","loss","warning","risk","bear","decline","negative","lawsuit","regulation"}


def _score_headlines(titles: list[str]) -> tuple[int, int]:
    """Count bullish vs bearish keywords across a list of headline strings."""
    bull = bear = 0
    for t in titles:
        words = set(t.lower().split())
        bull += bool(words & _BULL_WORDS)
        bear += bool(words & _BEAR_WORDS)
    return bull, bear


def get_news_sentiment(coin_sym: str) -> tuple[int, str]:
    """
    Scores news sentiment for a coin using two free RSS feeds:
      1. Google News  — coin-specific headlines (no key, no limit)
      2. CoinDesk RSS — top crypto news (no key, no limit)

    Returns (+1 bullish / -1 bearish / 0 neutral, reason_str).
    """
    titles: list[str] = []

    # 1. Google News — coin-specific
    try:
        url  = GOOGLE_NEWS_RSS.format(coin=coin_sym)
        feed = feedparser.parse(url)
        titles += [e.title for e in feed.entries[:10]]
    except Exception:
        pass

    # 2. CoinDesk RSS — general market headlines (filter for coin name)
    try:
        feed = feedparser.parse(COINDESK_RSS)
        titles += [
            e.title for e in feed.entries[:20]
            if coin_sym.replace("USDT", "").lower() in e.title.lower()
        ]
    except Exception:
        pass

    if not titles:
        return 0, "News: no headlines found"

    bull, bear = _score_headlines(titles)
    total = len(titles)

    if bull > bear + 2:
        return 1,  f"News: bullish  ({bull} bull / {bear} bear from {total} headlines)"
    if bear > bull + 2:
        return -1, f"News: bearish  ({bear} bear / {bull} bull from {total} headlines)"
    return 0, f"News: neutral  ({bull} bull / {bear} bear from {total} headlines)"


def get_macro_sentiment() -> tuple[int, str]:
    """
    Scans macro RSS feeds for Fed meetings, interest rate decisions,
    wars, sanctions, and other global events that move crypto markets.

    Runs ONCE per handler invocation (applies to all pairs equally).

    Returns (+1 risk-on / -1 risk-off / 0 neutral, reason_str).

    Bullish signals  (risk-on / easing):
      rate cut, dovish, pivot, ceasefire, peace deal, soft landing,
      stimulus, inflation cooling, quantitative easing …

    Bearish signals  (risk-off / tightening):
      rate hike, hawkish, tightening, recession, war escalation,
      invasion, sanctions, banking crisis, stagflation, trade war …
    """
    titles: list[str] = []

    for url in MACRO_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            titles += [e.title for e in feed.entries[:15]]
        except Exception:
            pass

    if not titles:
        return 0, "Macro: no headlines fetched"

    text  = " ".join(titles).lower()
    bull  = sum(1 for kw in _MACRO_BULL if kw in text)
    bear  = sum(1 for kw in _MACRO_BEAR if kw in text)

    if bull > bear + 1:
        return 1,  f"Macro: risk-on  ({bull} bullish keywords: easing/peace/cut detected)"
    if bear > bull + 1:
        return -1, f"Macro: risk-off ({bear} bearish keywords: hike/war/recession detected)"
    return 0, f"Macro: neutral  ({bull} bull / {bear} bear macro keywords)"


def get_market_cap_change() -> tuple[int, str]:
    """
    CoinGecko global crypto market cap 24h change.
    A strong positive move = broad risk-on (+1).
    A strong negative move = broad risk-off (-1).
    """
    try:
        r = requests.get(COINGECKO_GLOBAL, headers=_HEADERS, timeout=6)
        if r.status_code == 200:
            chg = r.json()["data"]["market_cap_change_percentage_24h_usd"]
            if chg > 3:
                return 1,  f"Global mkt cap +{chg:.1f}% 24h (risk-on)"
            if chg < -3:
                return -1, f"Global mkt cap {chg:.1f}% 24h (risk-off)"
            return 0,  f"Global mkt cap {chg:+.1f}% 24h (neutral)"
    except Exception as e:
        pass
    return 0, "Global mkt cap: unavailable"


def get_funding_rate(pair: str) -> tuple[int, str]:
    """
    OKX perpetual funding rate — free, no key.
    Negative rate → shorts paying longs → over-shorted → contrarian BULLISH.
    Positive rate → longs paying shorts → over-longed  → contrarian BEARISH.
    Threshold: ±0.03% (3× normal 0.01% baseline).
    """
    instId = pair[:-4] + "-USDT-SWAP"   # BTCUSDT → BTC-USDT-SWAP
    try:
        r = requests.get(OKX_FUNDING, params={"instId": instId},
                         headers=_HEADERS, timeout=5)
        if r.status_code == 200 and r.json().get("data"):
            rate = float(r.json()["data"][0]["fundingRate"])
            pct  = rate * 100
            if rate < -0.0003:
                return 1,  f"Funding rate {pct:.4f}% — shorts paying (contrarian bullish)"
            if rate > 0.0003:
                return -1, f"Funding rate {pct:.4f}% — longs paying  (contrarian bearish)"
            return 0, f"Funding rate {pct:.4f}% — neutral"
    except Exception:
        pass
    return 0, "Funding rate: unavailable"


def get_long_short_ratio(pair: str) -> tuple[int, str]:
    """
    OKX long/short account ratio — free, no key.
    LSR < 0.8 → market is over-shorted → contrarian BULLISH.
    LSR > 1.5 → market is over-longed  → contrarian BEARISH.
    """
    instId = pair[:-4] + "-USDT-SWAP"
    try:
        r = requests.get(OKX_LSR,
                         params={"instId": instId, "period": "1H"},
                         headers=_HEADERS, timeout=5)
        if r.status_code == 200 and r.json().get("data"):
            lsr = float(r.json()["data"][0][1])
            if lsr < 0.8:
                return 1,  f"L/S ratio {lsr:.2f} — over-shorted (contrarian bullish)"
            if lsr > 1.5:
                return -1, f"L/S ratio {lsr:.2f} — over-longed  (contrarian bearish)"
            return 0, f"L/S ratio {lsr:.2f} — balanced"
    except Exception:
        pass
    return 0, "L/S ratio: unavailable"


# ── signal engine ─────────────────────────────────────────────────────────────

NOTE_MAX_LEN = 500  # hard cap enforced on the note column

def _build_note(direction: str, adx: float, votes: list) -> str:
    """
    Plain-English summary of the main reason(s) behind the trade — the
    strongest votes that agree with the final direction, joined into one
    sentence. Capped at NOTE_MAX_LEN chars.
    """
    sign = 1 if direction == "long" else -1
    agreeing = sorted(
        (v for v in votes if v[1] * sign > 0),
        key=lambda v: abs(v[1]),
        reverse=True,
    )
    reasons = [reason for _name, _vote, reason in agreeing[:3]]
    trend = f"ADX {adx:.1f} confirms a {'strong' if adx >= 30 else 'clear'} {'up' if direction == 'long' else 'down'}trend"
    note = "; ".join([trend] + reasons) + "."
    if len(note) > NOTE_MAX_LEN:
        note = note[:NOTE_MAX_LEN - 1].rsplit(" ", 1)[0] + "…"
    return note


def analyze_pair(pair: str, candles: list,
                 fear_greed_score: int, fear_greed_reason: str,
                 macro_score: int = 0, macro_reason: str = "",
                 market_cap_score: int = 0, market_cap_reason: str = "",
                 funding_score: int = 0, funding_reason: str = "",
                 lsr_score: int = 0, lsr_reason: str = "") -> dict | None:
    """
    Regime-filtered momentum — see the module docstring for the full strategy.
    Returns an analysis dict; has_signal=True only when a trade is generated.
    """
    if len(candles) < 210:
        return {"score": 0, "price": 0.0, "atr": 0.0, "votes": [],
                "has_signal": False, "reason": "insufficient history"}

    close  = np.array([float(c[4]) for c in candles])
    high   = np.array([float(c[2]) for c in candles])
    low    = np.array([float(c[3]) for c in candles])
    vol    = np.array([float(c[5]) for c in candles])
    price  = close[-1]

    score        = 0
    votes        = []   # (indicator, vote, reason_str)
    is_commodity = pair in ("XAUUSDT", "XAGUSDT")
    atr_val      = round(calc_atr(high, low, close), 6)

    # Use the real-time ticker price as entry — more accurate than the candle close
    # which can lag by up to 1h. Falls back to close[-1] if ticker fetch fails.
    live = get_live_price(pair)
    entry_price = live if live is not None else price
    if live is not None and abs(live - price) / price > 0.001:
        print(f"  [LIVE] {pair} live=${live:,.4f}  candle_close=${price:,.4f}  "
              f"(diff {(live-price)/price*100:+.2f}%)")

    def no_signal(reason: str) -> dict:
        return {"score": score, "price": entry_price, "atr": atr_val, "adx": round(adx, 1),
                "votes": votes + [("Regime", 0, reason)], "has_signal": False}

    # ── REGIME GATE — momentum only trades confirmed trends (ADX + EMA stack) ──
    # This is the core fix: instead of summing trend-following and mean-reversion
    # votes that fight each other, we first decide the regime, then only trade
    # WITH a confirmed trend. Ranging markets are skipped entirely.
    adx    = calc_adx(high, low, close)
    ema20  = calc_ema(close, 20)
    ema50  = calc_ema(close, 50)
    ema200 = calc_ema(close, 200)
    uptrend   = price > ema50 > ema200
    downtrend = price < ema50 < ema200

    if adx < ADX_TREND_MIN:
        return no_signal(f"ADX {adx:.1f} < {ADX_TREND_MIN} — ranging, momentum sits out")
    if not (uptrend or downtrend):
        return no_signal(f"ADX {adx:.1f} trending but EMAs not stacked — no clean direction")

    votes.append(("Regime", 0, f"ADX {adx:.1f} — {'UP' if uptrend else 'DOWN'}trend confirmed"))

    # ── Trend backbone (the momentum engine) ──────────────────────────────────
    if price > ema200:
        score += 1; votes.append(("EMA200", +1, f"price > EMA200 {ema200:,.4f} (macro trend up)"))
    else:
        score -= 1; votes.append(("EMA200", -1, f"price < EMA200 {ema200:,.4f} (macro trend down)"))

    if price > ema50:
        score += 1; votes.append(("EMA50", +1, f"price > EMA50 {ema50:,.4f}"))
    else:
        score -= 1; votes.append(("EMA50", -1, f"price < EMA50 {ema50:,.4f}"))

    if ema20 > ema50:
        score += 1; votes.append(("EMA20/50", +1, "EMA20 > EMA50 (short-term up)"))
    else:
        score -= 1; votes.append(("EMA20/50", -1, "EMA20 < EMA50 (short-term down)"))

    # ── MACD — single vote (crossover strengthens the reason, never double-counts) ──
    _, _, hist_now, hist_prev = calc_macd(close)
    crossed_up   = hist_prev < 0 < hist_now
    crossed_down = hist_prev > 0 > hist_now
    if hist_now > 0:
        score += 1
        votes.append(("MACD", +1, f"histogram {hist_now:+.4f} ({'bullish + fresh cross' if crossed_up else 'bullish momentum'})"))
    elif hist_now < 0:
        score -= 1
        votes.append(("MACD", -1, f"histogram {hist_now:+.4f} ({'bearish + fresh cross' if crossed_down else 'bearish momentum'})"))

    # ── OBV slope — volume confirms the trend ─────────────────────────────────
    obv_slope = calc_obv_slope(close, vol)
    if obv_slope > 0:
        score += 1; votes.append(("OBV", +1, "volume trending up (confirms)"))
    elif obv_slope < 0:
        score -= 1; votes.append(("OBV", -1, "volume trending down (confirms)"))
    else:
        votes.append(("OBV", 0, "OBV flat"))

    # ── Oscillators — REGIME-AWARE, only ever vote WITH the trend ─────────────
    # An oversold reading inside an uptrend = healthy pullback = bonus long entry.
    # An overbought reading inside an uptrend is NORMAL momentum → neutral (we do
    # NOT short a strong uptrend). This is the fix for "buying tops via contradiction".
    rsi_val = calc_rsi(close)
    srsi    = calc_stoch_rsi(close)
    wr_val  = calc_williams_r(high, low, close)
    osc_oversold   = sum([rsi_val < 40, srsi < 0.25, wr_val < -75]) >= 2
    osc_overbought = sum([rsi_val > 60, srsi > 0.75, wr_val > -25]) >= 2
    osc_det = f"RSI {rsi_val:.0f} StochRSI {srsi:.2f} W%R {wr_val:.0f}"
    if uptrend and osc_oversold:
        score += 1; votes.append(("Oscillators", +1, f"oversold pullback in uptrend — {osc_det}"))
    elif downtrend and osc_overbought:
        score -= 1; votes.append(("Oscillators", -1, f"overbought bounce in downtrend — {osc_det}"))
    else:
        votes.append(("Oscillators", 0, f"no pullback edge — {osc_det}"))

    # ── Bollinger — REGIME-AWARE pullback confirmation ────────────────────────
    _, _, _, pct_b = calc_bollinger(close)
    if uptrend and pct_b < 0.40:
        score += 1; votes.append(("Bollinger", +1, f"%B {pct_b:.2f} — dip within uptrend"))
    elif downtrend and pct_b > 0.60:
        score -= 1; votes.append(("Bollinger", -1, f"%B {pct_b:.2f} — bounce within downtrend"))
    else:
        votes.append(("Bollinger", 0, f"%B {pct_b:.2f} — no pullback"))

    # ── Derivatives (contrarian positioning) ──────────────────────────────────
    if funding_score != 0:
        score += funding_score; votes.append(("Funding", funding_score, funding_reason))
    else:
        votes.append(("Funding", 0, funding_reason or "Funding: neutral"))
    if lsr_score != 0:
        score += lsr_score; votes.append(("L/S Ratio", lsr_score, lsr_reason))
    else:
        votes.append(("L/S Ratio", 0, lsr_reason or "L/S: balanced"))

    # ── Market Context — ALL soft sentiment collapsed into ONE low-weight vote ─
    # F&G, market cap, news and macro are individually noisy. We require strong
    # net agreement (|sum| >= 2) before they nudge the score by a single point,
    # so a Google-News keyword can never flip a technical setup on its own.
    coin_sym = pair.replace("USDT", "")
    news_score, news_reason = get_news_sentiment(coin_sym)
    ctx_sum = macro_score + news_score
    if not is_commodity:
        ctx_sum += fear_greed_score + market_cap_score
    if ctx_sum >= 2:
        score += 1; votes.append(("Market Context", +1, f"net sentiment +{ctx_sum} (F&G/news/macro agree bullish)"))
    elif ctx_sum <= -2:
        score -= 1; votes.append(("Market Context", -1, f"net sentiment {ctx_sum} (F&G/news/macro agree bearish)"))
    else:
        votes.append(("Market Context", 0, f"net sentiment {ctx_sum:+d} — mixed/neutral"))

    # ── Volume spike — amplifies the FINAL net direction ──────────────────────
    vol_r = volume_ratio(vol)
    if vol_r >= 1.5 and score != 0:
        amp = 1 if score > 0 else -1
        score += amp
        votes.append(("Volume", amp, f"volume {vol_r:.2f}× avg — amplifies {'bullish' if amp > 0 else 'bearish'}"))
    else:
        votes.append(("Volume", 0, f"volume {vol_r:.2f}× avg"))

    # ── Decision ─────────────────────────────────────────────────────────────
    base_result = {"score": score, "price": entry_price, "atr": atr_val,
                   "adx": round(adx, 1), "votes": votes, "has_signal": False}

    if score >= MIN_BULL_SCORE and uptrend:
        direction = "long"
    elif score <= -MIN_BEAR_SCORE and downtrend:
        direction = "short"
    else:
        return base_result   # score too weak, or would be counter-trend

    # ── Swing S/R limit entry — ask for a fill at a real reaction level ───────
    # Prefer the nearest recent swing low (longs) / swing high (shorts) within
    # MAX_DIST_ATR of price — a level the market has already reacted to, not
    # an arbitrary offset. Falls back to the shallow 0.3x ATR offset if no
    # qualifying swing level is nearby, so a signal is never skipped outright.
    # Everything downstream (SL/TP, RR) anchors to this adjusted entry.
    market_price = entry_price
    swing_level = find_swing_level(direction, market_price, atr_val, high, low)
    if swing_level is not None:
        entry_price = round(swing_level, 6)
    elif direction == "long":
        entry_price = round(market_price - ENTRY_ATR_MULT * atr_val, 6)
    else:
        entry_price = round(market_price + ENTRY_ATR_MULT * atr_val, 6)

    # ── Signal strength: |score| / active votes → 60–95 ──────────────────────
    # Indicator-AGREEMENT strength (how cleanly the votes align), 60–95.
    # NOT a win probability — backtests show it doesn't predict win rate.
    # Kept for internal ranking (Pass 2 picks the highest) and expiry sizing;
    # the user-facing app no longer displays it as a confidence %.
    active   = len([v for v in votes if v[1] != 0]) or 1
    strength = max(60, min(95, int(60 + min(abs(score) / active, 1.0) * 35)))

    # ── SL / TP — sized off the LIVE entry price ─────────────────────────────
    tp_dist = entry_price * TARGET_TP_PCT
    sl_dist = min(ATR_SL_MULT * atr_val, entry_price * MAX_SL_PCT)
    if sl_dist <= 0:
        sl_dist = entry_price * 0.01
    if tp_dist / sl_dist < MIN_RR:
        sl_dist = tp_dist / MIN_RR

    if direction == "long":
        sl = round(entry_price - sl_dist, 6)
        tp = round(entry_price + tp_dist, 6)
    else:
        sl = round(entry_price + sl_dist, 6)
        tp = round(entry_price - tp_dist, 6)

    # Risk : Reward ratio
    risk     = abs(entry_price - sl)
    reward   = abs(tp - entry_price)
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    # Expiry window: 2–7 days based on signal strength + RR quality
    expiry_days = calc_expiry_days(strength, rr_ratio)
    now         = datetime.now(timezone.utc)
    expires_at  = (now + timedelta(days=expiry_days)).isoformat()

    # Compact votes dict — only non-zero votes, no reason strings (~120 bytes).
    votes_json = {n: v for n, v, _ in votes if v != 0}

    note = _build_note(direction, adx, votes)

    return {
        "signal": {
            "id":          str(uuid.uuid4()),
            "pair":        pair,
            "direction":   direction,
            "entry":       round(float(entry_price), 6),
            "stop_loss":   sl,
            "take_profit": tp,
            "confidence":  strength,     # DB column name kept for compat; value = indicator-agreement strength, NOT a win probability (app no longer shows it)
            "rr_ratio":    rr_ratio,
            "timestamp":   now.isoformat(),
            "expires_at":  expires_at,
            "result":      "pending",
            "close_price": None,
            "votes_json":  votes_json,
            "note":        note,
        },
        "score":       score,
        "price":       entry_price,
        "atr":         round(atr_val, 6),
        "adx":         round(adx, 1),
        "rr_ratio":    rr_ratio,
        "expiry_days": expiry_days,
        "votes":       votes,
        "has_signal":  True,
    }


# ── logging ───────────────────────────────────────────────────────────────────

def log_analysis(pair: str, analysis: dict) -> None:
    print(SEP)
    score = analysis["score"]

    if not analysis.get("has_signal"):
        threshold = f">= +{MIN_BULL_SCORE} or <= -{MIN_BEAR_SCORE}"
        print(f"  {pair:<12}  score={score:+d}  -> NO SIGNAL  (threshold {threshold})")
        # Still show the indicator breakdown so you can see why
        for name, vote, reason in analysis.get("votes", []):
            arrow = " [+]" if vote > 0 else (" [-]" if vote < 0 else " [ ]")
            print(f"  {arrow}  {name:<12}  {reason}")
        return

    s       = analysis["signal"]
    rr      = analysis.get("rr_ratio", 0)
    exp_d   = analysis.get("expiry_days", "?")
    adx     = analysis.get("adx", 0)
    rr_label = "Excellent" if rr >= 2.0 else "Good" if rr >= 1.5 else "Fair"
    print(f"  {pair:<12}  score={score:+d}  -> {s['direction'].upper()}  strength={s['confidence']}%  (ADX {adx})")
    print(f"  Entry   : ${s['entry']:>14,.6f}     ATR      = {analysis['atr']:,.6f}")
    print(f"  SL      : ${s['stop_loss']:>14,.6f}     RR Ratio = 1 : {rr:.2f}  ({rr_label})")
    print(f"  TP      : ${s['take_profit']:>14,.6f}     Expires  = {exp_d} day(s)  [{s['expires_at'][:10]}]")
    print()
    for name, vote, reason in analysis["votes"]:
        arrow = " [+]" if vote > 0 else (" [-]" if vote < 0 else " [ ]")
        print(f"  {arrow}  {name:<12}  {reason}")


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
        .select("id")
        .gte("timestamp", today_start)
        .execute()
    )
    today_count   = len(today_rows.data)
    slots_left    = max(0, MAX_SIGNALS - today_count)

    print(f"[generate_signals] Signals today: {today_count} / {MAX_SIGNALS}  "
          f"(slots remaining: {slots_left})")

    if slots_left == 0:
        print(f"[generate_signals] Daily cap of {MAX_SIGNALS} already reached — skipping run.\n")
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "today_count": today_count})}

    print(f"[generate_signals] Will create up to {slots_left} more signal(s) this run.\n")

    # ── Global indicators (fetched once, applied to all pairs) ───────────────
    fg_score, fg_raw, fg_reason = get_fear_greed()
    fg_label = fg_reason.split(" — ")[0] if " — " in fg_reason else fg_reason
    print(f"  Fear & Greed  : {fg_reason}")

    mc_score, mc_reason = get_market_cap_change()
    print(f"  Market cap    : {mc_reason}")

    macro_score, macro_reason = get_macro_sentiment()
    print(f"  Macro events  : {macro_reason}\n")

    stats = {
        "analysed": 0, "inserted": 0,
        "low_confidence": 0, "no_signal": 0,
        "skipped_existing": 0, "errors": [],
        "today_count": today_count,
        "slots_left": slots_left,
    }

    # ── Pass 1: analyse all pairs, collect valid candidates ───────────────────
    candidates   = []   # analyses that passed score + confidence thresholds
    all_analyses = []   # every analysis (for sentiment computation)

    for pair in TOP_PAIRS:
        try:
            existing = (
                supabase.table("trade_signals")
                .select("id, timestamp")
                .eq("pair", pair)
                .eq("result", "pending")
                .execute()
            )
            if existing.data:
                ts = existing.data[0].get("timestamp", "")[:10]
                print(f"  [SKIP] {pair:<12} — pending signal already exists ({ts})")
                stats["skipped_existing"] += 1
                continue

            candles = fetch_candles(pair)

            # Per-pair derivatives data (OKX free, no key)
            fr_score, fr_reason = get_funding_rate(pair)
            ls_score, ls_reason = get_long_short_ratio(pair)

            stats["analysed"] += 1
            analysis = analyze_pair(
                pair, candles,
                fg_score, fg_reason,
                macro_score, macro_reason,
                mc_score, mc_reason,
                fr_score, fr_reason,
                ls_score, ls_reason,
            )
            analysis["pair"] = pair
            all_analyses.append(analysis)

            log_analysis(pair, analysis)

            if not analysis.get("has_signal"):
                stats["no_signal"] += 1
                continue

            strength = analysis["signal"]["confidence"]
            if strength < MIN_SIGNAL_STRENGTH:
                print(f"\n  [LOW STR]  {pair}  strength {strength}% < {MIN_SIGNAL_STRENGTH}% — discarded")
                stats["low_confidence"] += 1
                continue

            candidates.append(analysis)

        except requests.HTTPError as exc:
            msg = f"{pair}: API HTTP {exc.response.status_code} (all providers failed)"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair}: {exc}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)

    # ── Pass 2: rank by signal strength desc, keep only up to slots_left ─────
    candidates.sort(key=lambda a: a["signal"]["confidence"], reverse=True)
    to_insert = candidates[:slots_left]
    overflow  = candidates[slots_left:]

    if overflow:
        print(f"\n{SEP}")
        print(f"  Dropped (exceed daily cap of {MAX_SIGNALS} — {today_count} already today):")
        for a in overflow:
            s = a["signal"]
            print(f"    {s['pair']:<12}  {s['direction'].upper():<5}  strength={s['confidence']}%  — not inserted")

    # ── Pass 3: insert the winners ────────────────────────────────────────────
    if to_insert:
        print(f"\n{SEP}")
        print(f"  Inserting top {len(to_insert)} signal(s)  (max={MAX_SIGNALS}):\n")

    for analysis in to_insert:
        sig = analysis["signal"]
        try:
            supabase.table("trade_signals").insert(sig).execute()
            print(f"  [DB OK]  {sig['pair']:<12}  {sig['direction'].upper():<5}  "
                  f"strength={sig['confidence']}%  "
                  f"RR=1:{sig['rr_ratio']:.2f}  "
                  f"entry=${sig['entry']:,.4f}  id={sig['id'][:8]}...")
            stats["inserted"] += 1
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
        _upsert_sentiment(supabase, all_analyses, fg_raw, fg_label)
    except Exception as exc:
        print(f"\n  [SENTIMENT ERR] {exc}")

    print(f"\n{SEP}")
    print(f"[generate_signals] Done")
    print(f"  Inserted         : {stats['inserted']}  (daily cap={MAX_SIGNALS}, today total={today_count + stats['inserted']})")
    print(f"  Low strength     : {stats['low_confidence']}  (below {MIN_SIGNAL_STRENGTH}%)")
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
