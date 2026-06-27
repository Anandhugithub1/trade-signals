"""
generate_signals — creates trade signals for the top 10 crypto pairs
by market cap using technical analysis + market sentiment.

Data sources (all free):
  Binance REST API   — OHLCV candles (no key required)
  Alternative.me     — Fear & Greed Index (no key required)
  CryptoPanic API    — per-coin news sentiment (free key, optional)

Technical indicators:
  RSI(14)            — momentum / overbought-oversold
  MACD(12,26,9)      — trend + crossover signal
  EMA 50 / 200       — trend direction / golden-cross zone
  Bollinger Bands    — price extremes vs recent volatility
  Volume spike       — confirms signal strength
  ATR(14)            — sizes Stop Loss and Take Profit

Sentiment layer:
  Fear & Greed Index — market-wide contrarian signal
  CryptoPanic news   — coin-specific positive/negative news flow

Signal logic:
  Each indicator votes +1 (bullish) or -1 (bearish).
  LONG  if total score >=  MIN_BULL_SCORE
  SHORT if total score <= -MIN_BEAR_SCORE
  Skip  otherwise

  Confidence = maps score ratio → 60–95 %

Trigger: run once or twice a day.
"""

import json
import os
import uuid
import requests
import numpy as np
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
CRYPTOPANIC_KEY      = os.environ.get("CRYPTOPANIC_API_KEY", "")

BINANCE_KLINES  = "https://fapi.binance.com/fapi/v1/klines"  # USDT-M Futures perpetual
FEAR_GREED_URL  = "https://api.alternative.me/fng/?limit=1"
CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"

# Top 10 by market cap (Binance perpetual pairs)
TOP_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
]

MIN_BULL_SCORE       = 3    # net bullish votes required for LONG
MIN_BEAR_SCORE       = 3    # net bearish votes required for SHORT
MIN_SIGNAL_CONFIDENCE = 72  # signals below this % are discarded (low conviction)
MAX_SIGNALS          = 3    # insert at most this many signals per run
ATR_SL_MULT          = 2.0  # SL = entry ± (ATR_SL_MULT × ATR)
ATR_TP_MULT          = 3.0  # TP = entry ± (ATR_TP_MULT × ATR)
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


def get_news_sentiment(coin_sym: str) -> tuple[int, str]:
    """
    Returns (+1 / -1 / 0, reason_str).
    Requires CRYPTOPANIC_API_KEY.  Skipped if key is empty.
    """
    if not CRYPTOPANIC_KEY:
        return 0, "News: skipped (no CRYPTOPANIC_API_KEY)"
    try:
        r = requests.get(
            CRYPTOPANIC_URL,
            params={"auth_token": CRYPTOPANIC_KEY,
                    "currencies": coin_sym,
                    "filter": "hot",
                    "kind": "news"},
            timeout=5,
        )
        r.raise_for_status()
        posts = r.json().get("results", [])[:10]
        if not posts:
            return 0, f"News: no recent posts for {coin_sym}"

        bull = sum(1 for p in posts
                   if p.get("votes", {}).get("positive", 0) >
                      p.get("votes", {}).get("negative", 0))
        bear = len(posts) - bull

        if bull >= bear * 2:
            return 1, f"News: bullish ({bull} pos / {bear} neg)"
        if bear >= bull * 2:
            return -1, f"News: bearish ({bear} neg / {bull} pos)"
        return 0, f"News: mixed ({bull} pos / {bear} neg)"
    except Exception as exc:
        return 0, f"News: error ({exc})"


# ── signal engine ─────────────────────────────────────────────────────────────

def analyze_pair(pair: str, candles: list,
                 fear_greed_score: int, fear_greed_reason: str) -> dict | None:
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

    # 1. RSI
    rsi_val = calc_rsi(close)
    if rsi_val < 35:
        score += 1; votes.append(("RSI", +1, f"RSI {rsi_val:.1f} — oversold"))
    elif rsi_val > 65:
        score -= 1; votes.append(("RSI", -1, f"RSI {rsi_val:.1f} — overbought"))
    else:
        votes.append(("RSI",  0, f"RSI {rsi_val:.1f} — neutral"))

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

    # 5. EMA 50 — intermediate trend
    ema50 = calc_ema(close, 50)
    if price > ema50:
        score += 1; votes.append(("EMA50",  +1, f"price > EMA50 {ema50:,.4f}"))
    else:
        score -= 1; votes.append(("EMA50",  -1, f"price < EMA50 {ema50:,.4f}"))

    # 6. Bollinger Bands
    bb_upper, bb_mid, bb_lower, pct_b = calc_bollinger(close)
    if pct_b < 0.20:
        score += 1; votes.append(("BB",  +1, f"%B={pct_b:.2f} — near lower band (potential reversal up)"))
    elif pct_b > 0.80:
        score -= 1; votes.append(("BB",  -1, f"%B={pct_b:.2f} — near upper band (potential reversal down)"))
    else:
        votes.append(("BB",   0, f"%B={pct_b:.2f} — mid-band"))

    # 7. Volume spike (amplifies the dominant trend)
    vol_r = volume_ratio(vol)
    if vol_r >= 1.5:
        amp = 1 if score > 0 else (-1 if score < 0 else 0)
        score += amp
        votes.append(("Volume", amp,
                      f"volume {vol_r:.2f}× avg — amplifies {'bullish' if amp > 0 else 'bearish' if amp < 0 else 'neutral'} bias"))

    # 8. Fear & Greed
    if fear_greed_score != 0:
        score += fear_greed_score
        votes.append(("Fear/Greed", fear_greed_score, fear_greed_reason))
    else:
        votes.append(("Fear/Greed", 0, fear_greed_reason))

    # 9. News (per-coin)
    coin_sym = pair.replace("USDT", "")
    news_score, news_reason = get_news_sentiment(coin_sym)
    if news_score != 0:
        score += news_score
        votes.append(("News", news_score, news_reason))
    else:
        votes.append(("News", 0, news_reason))

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

    # ATR-based SL / TP
    atr_val = base_result["atr"]
    if direction == "long":
        sl = round(price - ATR_SL_MULT * atr_val, 6)
        tp = round(price + ATR_TP_MULT * atr_val, 6)
    else:
        sl = round(price + ATR_SL_MULT * atr_val, 6)
        tp = round(price - ATR_TP_MULT * atr_val, 6)

    # Risk : Reward ratio  (stored as the reward side of "1 : X")
    risk     = abs(price - sl)
    reward   = abs(tp - price)
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    # Expiry window: 2–7 days based on confidence + RR quality
    expiry_days = calc_expiry_days(confidence, rr_ratio)
    now         = datetime.now(timezone.utc)
    expires_at  = (now + timedelta(days=expiry_days)).isoformat()

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

    print(f"\n[generate_signals] Started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"[generate_signals] Analysing {len(TOP_PAIRS)} pairs\n")

    # Fetch shared Fear & Greed Index once
    fg_score, fg_raw, fg_reason = get_fear_greed()
    fg_label = fg_reason.split(" — ")[0] if " — " in fg_reason else fg_reason
    print(f"  Fear & Greed : {fg_reason}\n")

    stats = {
        "analysed": 0, "inserted": 0,
        "low_confidence": 0, "no_signal": 0,
        "skipped_existing": 0, "errors": [],
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

            resp = requests.get(
                BINANCE_KLINES,
                params={"symbol": pair, "interval": "4h", "limit": CANDLE_LIMIT},
                timeout=10,
            )
            resp.raise_for_status()
            candles = resp.json()

            stats["analysed"] += 1
            analysis = analyze_pair(pair, candles, fg_score, fg_reason)
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
            msg = f"{pair}: Binance HTTP {exc.response.status_code}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair}: {exc}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)

    # ── Pass 2: rank by confidence desc, keep only top MAX_SIGNALS ───────────
    candidates.sort(key=lambda a: a["signal"]["confidence"], reverse=True)
    to_insert = candidates[:MAX_SIGNALS]
    overflow  = candidates[MAX_SIGNALS:]

    if overflow:
        print(f"\n{SEP}")
        print(f"  Dropped (exceed MAX_SIGNALS={MAX_SIGNALS} cap — kept higher confidence):")
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

    # ── Pass 4: upsert market sentiment ──────────────────────────────────────
    try:
        _upsert_sentiment(supabase, all_analyses, fg_raw, fg_label)
    except Exception as exc:
        print(f"\n  [SENTIMENT ERR] {exc}")

    print(f"\n{SEP}")
    print(f"[generate_signals] Done")
    print(f"  Inserted         : {stats['inserted']}  (cap={MAX_SIGNALS})")
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
