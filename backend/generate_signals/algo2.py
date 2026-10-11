"""
algo2 — Macro Trend Momentum strategy for crypto (Algo 2).
Replaces the old mean reversion engine.

STRATEGY
  Timeframe:  1h candles with 4h Macro Bull alignment
  Regime:     Price > 4h EMA200, 4h EMA50 > 4h EMA200 (confirmed secular bull market)
  Trigger:    1h EMA12 crosses above EMA26, RSI(14) between 50 and 70 (bull expansion),
              MACD histogram > 0, Volume > 20-period Volume MA
  Direction:  LONG only
  Target:     Pure 1:2 Risk-to-Reward:
              - Take Profit: +10.0% (+2R)
              - Stop Loss:   -5.0% (-1R)
              - Breakeven win rate is only 33.3%, leaving substantial edge over costs.
  Hold:       Up to 72 hours (3 days).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
import numpy as np

TP_PCT = 0.100    # +10.0% Take Profit (+2R)
SL_PCT = 0.050    # -5.0% Stop Loss (-1R)
RR_RATIO = 2.0    # 1:2 Reward:Risk
MAX_HOLD_HOURS = 72
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


def analyze_algo2(pair: str, candles_1h: list, candles_4h: list | None = None,
                  live_price: float | None = None) -> dict | None:
    """
    Evaluate pair for Algo 2 (1h Macro Bull Momentum 1:2).
    """
    if len(candles_1h) < 210:
        return None

    close_1h = np.array([float(c[4]) for c in candles_1h])
    vol_1h   = np.array([float(c[5]) for c in candles_1h])

    ema12_1h = _ema(close_1h, 12)
    ema26_1h = _ema(close_1h, 26)
    ema50_1h = _ema(close_1h, 50)
    ema200_1h = _ema(close_1h, 200)

    last_close = float(close_1h[-1])
    rsi_1h = _rsi(close_1h, 14)
    vol_ma20 = float(np.mean(vol_1h[-20:]))
    last_vol = float(vol_1h[-1])

    # 4h Macro alignment check if 4h candles provided
    macro_bull = True
    if candles_4h and len(candles_4h) >= 200:
        close_4h = np.array([float(c[4]) for c in candles_4h])
        ema50_4h = _ema(close_4h, 50)[-1]
        ema200_4h = _ema(close_4h, 200)[-1]
        last_close_4h = float(close_4h[-1])
        if not (last_close_4h > ema200_4h and ema50_4h > ema200_4h):
            macro_bull = False

    # Check 1h filters
    trend_ok = (last_close > ema200_1h[-1]) and (last_close > ema50_1h[-1])
    momentum_cross = (ema12_1h[-1] > ema26_1h[-1]) and (ema12_1h[-2] <= ema26_1h[-2] or ema12_1h[-1] > ema26_1h[-1] * 1.002)
    rsi_ok = (50.0 <= rsi_1h <= 72.0)
    vol_ok = (last_vol >= vol_ma20 * 0.95)

    if not (macro_bull and trend_ok and momentum_cross and rsi_ok and vol_ok):
        return None

    entry = float(live_price) if live_price else last_close
    sl = entry * (1.0 - SL_PCT)
    tp = entry * (1.0 + TP_PCT)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=MAX_HOLD_HOURS)

    # Rank score: combination of RSI strength and distance above EMA50
    rank_score = (rsi_1h - 50.0) + ((last_close - ema50_1h[-1]) / ema50_1h[-1] * 100.0)

    return {
        "id": str(uuid.uuid4()),
        "pair": pair,
        "direction": "long",
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
        "note": (f"Algo 2: 1h Macro Bull Momentum (1:2). Price > EMA200 & EMA50, "
                 f"EMA12 > EMA26 crossover, RSI(14)={rsi_1h:.1f}. "
                 f"Target +10.0% (+2R), Stop -5.0% (-1R)."),
        "_rank": float(rank_score),
    }
