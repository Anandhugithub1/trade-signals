"""
algo2 — Sideways Regime Range strategy for crypto (Algo 2).
Replaces the old 1h bull momentum engine with the 4h Sideways Range Reversion engine.

STRATEGY
  Timeframe:  4h candles (institutional range boundary)
  Regime:     Consolidation / Sideways market: ADX(14) < 24.0 and Bollinger Bandwidth >= 3.5%
  Trigger:    
              - Range Long:  Close >= EMA200 * 0.98, Low <= Lower BB, Bullish bounce candle (Close > Open), RSI < 44
              - Range Short: Close <= EMA200 * 1.02, High >= Upper BB, Bearish rejection candle (Close < Open), RSI > 56
  Direction:  LONG and SHORT (captures both boundaries of the range)
  Target:     Pure 1:2 Risk-to-Reward:
              - Take Profit: +8.0% gain (+2R)
              - Stop Loss:   -4.0% loss (-1R)
              - Breakeven win rate is only 33.3%, leaving substantial edge over costs.
  Hold:       Up to 144 hours (6 days max hold validity).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
import numpy as np

TP_PCT = 0.080    # +8.0% Take Profit (+2R)
SL_PCT = 0.040    # -4.0% Stop Loss (-1R)
RR_RATIO = 2.0    # 1:2 Reward:Risk
MAX_HOLD_HOURS = 144  # 6 days (36 x 4h bars)
STRATEGY_TAG = "algo2"


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def _rsi(close: np.ndarray, period: int = 14) -> float:
    if len(close) < period + 1:
        return 50.0
    diff = np.diff(close)
    gains = np.maximum(diff, 0)
    losses = np.maximum(-diff, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    if len(close) < period * 2:
        return 50.0
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr = np.zeros(len(tr))
    p_dm = np.zeros(len(tr))
    m_dm = np.zeros(len(tr))
    atr[period - 1] = np.mean(tr[:period])
    p_dm[period - 1] = np.mean(plus_dm[:period])
    m_dm[period - 1] = np.mean(minus_dm[:period])
    for i in range(period, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        p_dm[i] = (p_dm[i - 1] * (period - 1) + plus_dm[i]) / period
        m_dm[i] = (m_dm[i - 1] * (period - 1) + minus_dm[i]) / period

    valid = atr > 0
    p_di = np.zeros_like(atr)
    m_di = np.zeros_like(atr)
    p_di[valid] = 100.0 * p_dm[valid] / atr[valid]
    m_di[valid] = 100.0 * m_dm[valid] / atr[valid]

    denom = p_di + m_di
    dx = np.zeros_like(p_di)
    v2 = denom > 0
    dx[v2] = 100.0 * np.abs(p_di[v2] - m_di[v2]) / denom[v2]

    adx_start = period * 2 - 1
    if len(dx) <= adx_start:
        return float(np.mean(dx[period:]))
    adx = np.zeros(len(dx))
    adx[adx_start] = np.mean(dx[period:adx_start + 1])
    for i in range(adx_start + 1, len(dx)):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return float(adx[-1])


def analyze_algo2(pair: str, candles_1h: list | None = None, candles_4h: list | None = None,
                  live_price: float | None = None) -> dict | None:
    """
    Evaluate pair for Algo 2: 4h Sideways Regime Range (Pure 1:2 R:R).
    Works on 4h candles (either passed as candles_4h or candles_1h).
    """
    candles = candles_4h if (candles_4h and len(candles_4h) >= 100) else candles_1h
    if not candles or len(candles) < 100:
        return None

    open_arr  = np.array([float(c[1]) for c in candles])
    high_arr  = np.array([float(c[2]) for c in candles])
    low_arr   = np.array([float(c[3]) for c in candles])
    close_arr = np.array([float(c[4]) for c in candles])

    last_open  = float(open_arr[-1])
    last_high  = float(high_arr[-1])
    last_low   = float(low_arr[-1])
    last_close = float(close_arr[-1])

    # 1. Low Trend / Sideways Filter: ADX < 24.0
    adx_val = _adx(high_arr, low_arr, close_arr, 14)
    if adx_val >= 24.0:
        return None

    # 2. Bollinger Bands (20, 2.0 std)
    bb_mid = float(np.mean(close_arr[-20:]))
    bb_std = float(np.std(close_arr[-20:]))
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0.0

    # Range must have sufficient width (>= 3.5%) to cover stoploss and yield profit
    if bb_width < 0.035:
        return None

    # 3. Macro EMA200 alignment and RSI(14)
    ema200 = float(_ema(close_arr, 200)[-1]) if len(close_arr) >= 200 else bb_mid
    rsi_val = _rsi(close_arr, 14)

    # 4. Check Range Setups
    is_long = False
    is_short = False

    # Range Long Setup: Price bounces at lower band in healthy macro structure
    if (last_close >= ema200 * 0.98 and
            last_low <= bb_lower * 1.002 and
            last_close > last_open and
            rsi_val < 44.0):
        is_long = True

    # Range Short Setup: Price rejects at upper band in neutral/bearish macro structure
    elif (last_close <= ema200 * 1.02 and
          last_high >= bb_upper * 0.998 and
          last_close < last_open and
          rsi_val > 56.0):
        is_short = True

    if not (is_long or is_short):
        return None

    direction = 'long' if is_long else 'short'
    base_price = float(live_price) if live_price else last_close

    # Limit entry offset: -1.0% for Long, +1.0% for Short
    if is_long:
        entry = base_price * 0.990
        sl = entry * (1.0 - SL_PCT)
        tp = entry * (1.0 + TP_PCT)
        rank_score = (44.0 - rsi_val) + (bb_width * 100.0)
        note_desc = (f"Algo 2: Sideways Range Long (1:2). ADX={adx_val:.1f} (<24), "
                     f"bounced off lower BB ({bb_lower:.4f}), RSI={rsi_val:.1f}. "
                     f"Limit entry -1.0% @ {entry:.4f}. TP +8.0% (+2R), SL -4.0% (-1R). 6d max hold.")
    else:
        entry = base_price * 1.010
        sl = entry * (1.0 + SL_PCT)
        tp = entry * (1.0 - TP_PCT)
        rank_score = (rsi_val - 56.0) + (bb_width * 100.0)
        note_desc = (f"Algo 2: Sideways Range Short (1:2). ADX={adx_val:.1f} (<24), "
                     f"rejected at upper BB ({bb_upper:.4f}), RSI={rsi_val:.1f}. "
                     f"Limit entry +1.0% @ {entry:.4f}. TP +8.0% (+2R), SL -4.0% (-1R). 6d max hold.")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=MAX_HOLD_HOURS)

    return {
        "id": str(uuid.uuid4()),
        "pair": pair,
        "direction": direction,
        "entry": round(entry, 6),
        "stop_loss": round(sl, 6),
        "take_profit": round(tp, 6),
        "confidence": 85,
        "rr_ratio": RR_RATIO,
        "timestamp": now.isoformat(),
        "expires_at": expires.isoformat(),
        "result": "pending",
        "close_price": None,
        "entry_confirmed": False,
        "strategy": STRATEGY_TAG,
        "note": note_desc,
        "_rank": float(rank_score),
    }
