"""
generate_signals — creates trade signals for the top 15 crypto pairs
by market cap using technical analysis + multi-source sentiment.

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
 VOTING TABLE  (each indicator casts +1 / -1 / 0)
═══════════════════════════════════════════════════════════════════
  #   Indicator            Bullish (+1)           Bearish (-1)
  ─── ──────────────────   ─────────────────────  ────────────────────
  1   RSI(14)              < 35 oversold           > 65 overbought
  2   Stochastic RSI       < 0.20 oversold         > 0.80 overbought
  3   Williams %R          < -80 oversold          > -20 overbought
  4   MACD histogram       positive momentum       negative momentum
  5   MACD crossover       histogram flipped +     histogram flipped −  [bonus]
  6   EMA 200              price above             price below
  7   EMA 50               price above             price below
  8   EMA 20/50 cross      EMA20 > EMA50           EMA20 < EMA50
  9   Bollinger %B         < 0.20 low band         > 0.80 high band
  10  OBV slope            trending up             trending down
  11  Volume spike         > 1.5× avg trend        (amplifies dominant bias)
  12  Fear & Greed         extreme fear            extreme greed
  13  Global mkt cap       24h change > +3 %       24h change < -3 %
  14  Funding rate         negative (shorts pay)   positive (longs pay)
  15  Long/Short ratio     LSR < 0.8  (over-shorted)  LSR > 1.5 (over-longed)
  16  Coin news            bullish headlines        bearish headlines
  17  Macro events         rate cut/ceasefire       rate hike/war/recession
  ─── ──────────────────   ─────────────────────  ────────────────────

  LONG  signal when net score >= MIN_BULL_SCORE  (4)
  SHORT signal when net score <= -MIN_BEAR_SCORE (4)
  Confidence = score ratio → 60–95 %

Trigger: every 4h via GitHub Actions cron. Max 5 signals/day.
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

# Top 15 by market cap — excludes stablecoins (USDT/USDC/BUSD)
# Pairs available on Binance/Bybit/OKX perpetual futures
TOP_PAIRS = [
    "BTCUSDT",  "ETHUSDT",  "BNBUSDT",  "SOLUSDT",  "XRPUSDT",   # 1–5
    "ADAUSDT",  "DOGEUSDT", "TRXUSDT",  "AVAXUSDT", "TONUSDT",    # 6–10
    "DOTUSDT",  "LINKUSDT", "LTCUSDT",  "BCHUSDT",  "UNIUSDT",    # 11–15
]

MIN_BULL_SCORE       = 4    # net bullish votes required for LONG  (raised: 17 indicators now)
MIN_BEAR_SCORE       = 4    # net bearish votes required for SHORT
MIN_SIGNAL_CONFIDENCE = 72  # signals below this % are discarded (low conviction)
MAX_SIGNALS          = 5    # insert at most this many signals per day
ATR_SL_MULT          = 1.2  # SL = entry ± (ATR_SL_MULT × ATR)
ATR_TP_MULT          = 1.8  # TP = entry ± (ATR_TP_MULT × ATR)

# Hard percentage caps — SL/TP can never exceed these distances from entry,
# regardless of ATR.  Targets 2–3% intraday moves.
MAX_SL_PCT  = 0.020   # stop loss  no wider than 2.0% of entry
MAX_TP_PCT  = 0.030   # take profit no further than 3.0% of entry
MIN_SL_PCT  = 0.005   # stop loss  at least 0.5% (avoids noise wick-outs)
MIN_TP_PCT  = 0.010   # take profit at least 1.0%
CANDLE_LIMIT         = 300  # 300 × 4h ≈ 50 days (enough for EMA200 warmup)
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
    delta = np.diff(close[-period - 1:])
    gains  = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_g = np.mean(gains)
    avg_l = np.mean(losses)
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


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]),
                   np.abs(low[1:] - close[:-1]))
    )
    return float(np.mean(tr[-period:]))


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
    Combined (60% conf weight, 40% RR weight) → scales 2–7 days.

    Examples:
      confidence=65, RR=1.5  →  ~3 days
      confidence=80, RR=2.0  →  ~5 days
      confidence=90, RR=2.5  →  ~7 days
    """
    conf_factor = min((confidence - 60) / 35.0, 1.0)
    rr_factor   = min(max((rr_ratio - 1.0) / 2.0, 0.0), 1.0)
    factor      = conf_factor * 0.6 + rr_factor * 0.4
    days        = round(2 + factor * 5)            # 2 → 7
    return max(2, min(7, int(days)))


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
            params={"symbol": symbol, "interval": "4h", "limit": CANDLE_LIMIT},
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
                    "interval": "240", "limit": CANDLE_LIMIT},
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
        params={"instId": _okx_symbol(symbol), "bar": "4H", "limit": CANDLE_LIMIT},
        headers=_HEADERS, timeout=10,
    )
    r.raise_for_status()
    return list(reversed(r.json()["data"]))   # OKX newest-first → reverse


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

def analyze_pair(pair: str, candles: list,
                 fear_greed_score: int, fear_greed_reason: str,
                 macro_score: int = 0, macro_reason: str = "",
                 market_cap_score: int = 0, market_cap_reason: str = "",
                 funding_score: int = 0, funding_reason: str = "",
                 lsr_score: int = 0, lsr_reason: str = "") -> dict | None:
    """
    Score a pair across all indicators and return a signal dict, or None.

    Voting table
    ─────────────────────────────────────────────────────────
    Indicator         Bullish (+1)          Bearish (-1)
    ─────────────────────────────────────────────────────────
    RSI(14)           < 35 (oversold)       > 65 (overbought)
    MACD histogram    positive              negative
    MACD crossover    just crossed up       just crossed down  [bonus]
    EMA 200           price above           price below
    EMA 50            price above           price below
    Bollinger %B      < 0.20 (low band)     > 0.80 (high band)
    Volume spike      > 1.5× avg × trend   (amplifies, not standalone)
    Fear & Greed      extreme fear          extreme greed
    News sentiment    majority positive     majority negative
    Macro events      rate cut / ceasefire  rate hike / war / recession
    ─────────────────────────────────────────────────────────
    """
    if len(candles) < 210:
        return None  # not enough history

    close  = np.array([float(c[4]) for c in candles])
    high   = np.array([float(c[2]) for c in candles])
    low    = np.array([float(c[3]) for c in candles])
    vol    = np.array([float(c[5]) for c in candles])
    price  = close[-1]

    score   = 0
    votes   = []   # (indicator, vote, reason_str)

    # 1. RSI(14)
    rsi_val = calc_rsi(close)
    if rsi_val < 35:
        score += 1; votes.append(("RSI", +1, f"RSI {rsi_val:.1f} — oversold"))
    elif rsi_val > 65:
        score -= 1; votes.append(("RSI", -1, f"RSI {rsi_val:.1f} — overbought"))
    else:
        votes.append(("RSI",  0, f"RSI {rsi_val:.1f} — neutral"))

    # 2. Stochastic RSI — more sensitive, good for extreme detection
    srsi = calc_stoch_rsi(close)
    if srsi < 0.20:
        score += 1; votes.append(("StochRSI", +1, f"StochRSI {srsi:.2f} — oversold"))
    elif srsi > 0.80:
        score -= 1; votes.append(("StochRSI", -1, f"StochRSI {srsi:.2f} — overbought"))
    else:
        votes.append(("StochRSI", 0, f"StochRSI {srsi:.2f} — neutral"))

    # 3. Williams %R — momentum oscillator
    wr = calc_williams_r(high, low, close)
    if wr < -80:
        score += 1; votes.append(("Williams%R", +1, f"W%R {wr:.1f} — oversold"))
    elif wr > -20:
        score -= 1; votes.append(("Williams%R", -1, f"W%R {wr:.1f} — overbought"))
    else:
        votes.append(("Williams%R", 0, f"W%R {wr:.1f} — neutral"))

    # 2. MACD histogram direction
    _, _, hist_now, hist_prev = calc_macd(close)
    if hist_now > 0:
        score += 1; votes.append(("MACD hist",  +1, f"histogram {hist_now:+.4f} (bullish momentum)"))
    elif hist_now < 0:
        score -= 1; votes.append(("MACD hist",  -1, f"histogram {hist_now:+.4f} (bearish momentum)"))

    # 3. MACD crossover bonus
    if hist_prev < 0 < hist_now:
        score += 1; votes.append(("MACD cross", +1, "bullish crossover (hist flipped +)"))
    elif hist_prev > 0 > hist_now:
        score -= 1; votes.append(("MACD cross", -1, "bearish crossover (hist flipped -)"))

    # 4. EMA 200 — macro trend filter
    ema200 = calc_ema(close, 200)
    if price > ema200:
        score += 1; votes.append(("EMA200", +1, f"price {price:,.4f} > EMA200 {ema200:,.4f}"))
    else:
        score -= 1; votes.append(("EMA200", -1, f"price {price:,.4f} < EMA200 {ema200:,.4f}"))

    # 6. EMA 50 — intermediate trend
    ema50 = calc_ema(close, 50)
    if price > ema50:
        score += 1; votes.append(("EMA50",  +1, f"price > EMA50 {ema50:,.4f}"))
    else:
        score -= 1; votes.append(("EMA50",  -1, f"price < EMA50 {ema50:,.4f}"))

    # 7. EMA 20/50 short-term crossover
    ema20 = calc_ema(close, 20)
    if ema20 > ema50:
        score += 1; votes.append(("EMA20/50", +1, f"EMA20 {ema20:,.4f} > EMA50 — bullish cross"))
    else:
        score -= 1; votes.append(("EMA20/50", -1, f"EMA20 {ema20:,.4f} < EMA50 — bearish cross"))

    # 8. Bollinger Bands
    bb_upper, bb_mid, bb_lower, pct_b = calc_bollinger(close)
    if pct_b < 0.20:
        score += 1; votes.append(("BB",  +1, f"%B={pct_b:.2f} — near lower band (potential reversal up)"))
    elif pct_b > 0.80:
        score -= 1; votes.append(("BB",  -1, f"%B={pct_b:.2f} — near upper band (potential reversal down)"))
    else:
        votes.append(("BB",   0, f"%B={pct_b:.2f} — mid-band"))

    # 9. OBV slope — volume confirms price trend
    obv_slope = calc_obv_slope(close, vol)
    if obv_slope > 0:
        score += 1; votes.append(("OBV", +1, f"OBV slope {obv_slope:+.0f} — volume trending up"))
    elif obv_slope < 0:
        score -= 1; votes.append(("OBV", -1, f"OBV slope {obv_slope:+.0f} — volume trending down"))
    else:
        votes.append(("OBV", 0, "OBV slope flat"))

    # 10. Volume spike (amplifies the dominant trend)
    vol_r = volume_ratio(vol)
    if vol_r >= 1.5:
        amp = 1 if score > 0 else (-1 if score < 0 else 0)
        score += amp
        votes.append(("Volume", amp,
                      f"volume {vol_r:.2f}× avg — amplifies {'bullish' if amp > 0 else 'bearish' if amp < 0 else 'neutral'} bias"))

    # 11. Fear & Greed
    if fear_greed_score != 0:
        score += fear_greed_score
        votes.append(("Fear/Greed", fear_greed_score, fear_greed_reason))
    else:
        votes.append(("Fear/Greed", 0, fear_greed_reason))

    # 12. Global market cap change
    if market_cap_score != 0:
        score += market_cap_score
        votes.append(("Mkt Cap", market_cap_score, market_cap_reason))
    else:
        votes.append(("Mkt Cap", 0, market_cap_reason or "Mkt cap: neutral"))

    # 13. Funding rate — derivatives positioning
    if funding_score != 0:
        score += funding_score
        votes.append(("Funding", funding_score, funding_reason))
    else:
        votes.append(("Funding", 0, funding_reason or "Funding rate: neutral"))

    # 14. Long/Short ratio — derivatives positioning
    if lsr_score != 0:
        score += lsr_score
        votes.append(("L/S Ratio", lsr_score, lsr_reason))
    else:
        votes.append(("L/S Ratio", 0, lsr_reason or "L/S ratio: balanced"))

    # 15. Coin-specific news
    coin_sym = pair.replace("USDT", "")
    news_score, news_reason = get_news_sentiment(coin_sym)
    if news_score != 0:
        score += news_score
        votes.append(("News", news_score, news_reason))
    else:
        votes.append(("News", 0, news_reason))

    # 16. Macro events — Fed, interest rates, wars, geopolitics
    if macro_score != 0:
        score += macro_score
        votes.append(("Macro", macro_score, macro_reason))
    else:
        votes.append(("Macro", 0, macro_reason or "Macro: neutral"))

    # ── Decision ─────────────────────────────────────────────────────────────
    base_result = {"score": score, "price": price, "atr": round(calc_atr(high, low, close), 6),
                   "votes": votes, "has_signal": False}

    if score >= MIN_BULL_SCORE:
        direction = "long"
    elif score <= -MIN_BEAR_SCORE:
        direction = "short"
    else:
        return base_result   # return score info even when no signal

    # Confidence: map |score| / max_possible → 60-95%
    max_possible = len([v for v in votes if v[1] != 0]) or 1
    confidence = int(60 + min(abs(score) / max_possible, 1.0) * 35)
    confidence = max(60, min(95, confidence))

    # ATR-based SL / TP with hard percentage caps
    # ATR suggests the distance; caps ensure we target 2–3% moves, not 5%+.
    atr_val = base_result["atr"]

    raw_sl_dist = ATR_SL_MULT * atr_val
    raw_tp_dist = ATR_TP_MULT * atr_val

    sl_dist = max(min(raw_sl_dist, price * MAX_SL_PCT), price * MIN_SL_PCT)
    tp_dist = max(min(raw_tp_dist, price * MAX_TP_PCT), price * MIN_TP_PCT)

    if direction == "long":
        sl = round(price - sl_dist, 6)
        tp = round(price + tp_dist, 6)
    else:
        sl = round(price + sl_dist, 6)
        tp = round(price - tp_dist, 6)

    # Risk : Reward ratio  (stored as the reward side of "1 : X")
    risk     = abs(price - sl)
    reward   = abs(tp - price)
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    # Expiry window: 2–7 days based on confidence + RR quality
    expiry_days = calc_expiry_days(confidence, rr_ratio)
    now         = datetime.now(timezone.utc)
    expires_at  = (now + timedelta(days=expiry_days)).isoformat()

    # Compact votes dict — only non-zero votes, no reason strings.
    # Drops storage from ~1KB to ~120 bytes per signal.
    # Format: {"MACD hist": 1, "EMA200": 1, "Macro": -1, ...}
    votes_json = {n: v for n, v, _ in votes if v != 0}

    return {
        "signal": {
            "id":          str(uuid.uuid4()),
            "pair":        pair,
            "direction":   direction,
            "entry":       round(float(price), 6),
            "stop_loss":   sl,
            "take_profit": tp,
            "confidence":  confidence,
            "rr_ratio":    rr_ratio,
            "timestamp":   now.isoformat(),
            "expires_at":  expires_at,
            "result":      "pending",
            "close_price": None,
            "votes_json":  votes_json,   # full indicator breakdown → analytics
        },
        "score":       score,
        "price":       price,
        "atr":         round(atr_val, 6),
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
    rr_label = "Excellent" if rr >= 2.0 else "Good" if rr >= 1.5 else "Fair"
    print(f"  {pair:<12}  score={score:+d}  -> {s['direction'].upper()}  confidence={s['confidence']}%")
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

            conf = analysis["signal"]["confidence"]
            if conf < MIN_SIGNAL_CONFIDENCE:
                print(f"\n  [LOW CONF]  {pair}  {conf}% < {MIN_SIGNAL_CONFIDENCE}% threshold — discarded")
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

    # ── Pass 2: rank by confidence desc, keep only up to slots_left ──────────
    candidates.sort(key=lambda a: a["signal"]["confidence"], reverse=True)
    to_insert = candidates[:slots_left]
    overflow  = candidates[slots_left:]

    if overflow:
        print(f"\n{SEP}")
        print(f"  Dropped (exceed daily cap of {MAX_SIGNALS} — {today_count} already today):")
        for a in overflow:
            s = a["signal"]
            print(f"    {s['pair']:<12}  {s['direction'].upper():<5}  confidence={s['confidence']}%  — not inserted")

    # ── Pass 3: insert the winners ────────────────────────────────────────────
    if to_insert:
        print(f"\n{SEP}")
        print(f"  Inserting top {len(to_insert)} signal(s)  (max={MAX_SIGNALS}):\n")

    for analysis in to_insert:
        sig = analysis["signal"]
        try:
            supabase.table("trade_signals").insert(sig).execute()
            print(f"  [DB OK]  {sig['pair']:<12}  {sig['direction'].upper():<5}  "
                  f"confidence={sig['confidence']}%  "
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
    print(f"  Low confidence   : {stats['low_confidence']}  (below {MIN_SIGNAL_CONFIDENCE}%)")
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
