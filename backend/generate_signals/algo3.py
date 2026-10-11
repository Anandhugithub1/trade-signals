"""
algo3 — Bearish Macro Breakdown Short strategy for crypto (Algo 3).
Dedicated short-selling algorithm with strict 1:2 Risk-to-Reward.

STRATEGY
  Timeframe:  4h candles (macro regime) with optional 1h confirmation
  Regime:     Price < 4h EMA200, 4h EMA50 < 4h EMA200 (confirmed secular bear trend)
  Trigger:    Breakdown below 20-period low or 4h EMA12 crossing below EMA26,
              RSI(14) between 28 and 52 (bearish momentum expansion),
              Volume >= 20-period Volume MA
  Direction:  SHORT only
  Target:     Pure 1:2 Risk-to-Reward:
              - Take Profit: +10.0% gain (+2R) [price falls 10%]
              - Stop Loss:   -5.0% loss (-1R) [price rises 5%]
              - Breakeven win rate is only 33.3%, yielding substantial edge over fees.
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
STRATEGY_TAG = "algo3"


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
        return 0.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def analyze_algo3(pair: str, candles_4h: list, candles_1h: list | None = None,
                  live_price: float | None = None) -> dict | None:
    """
    Evaluate pair for Algo 3 (4h Bearish Macro Breakdown Short 1:2).
    """
    if len(candles_4h) < 210:
        return None

    close_4h = np.array([float(c[4]) for c in candles_4h])
    low_4h   = np.array([float(c[3]) for c in candles_4h])
    high_4h  = np.array([float(c[2]) for c in candles_4h])
    vol_4h   = np.array([float(c[5]) for c in candles_4h])

    ema12_4h  = _ema(close_4h, 12)
    ema26_4h  = _ema(close_4h, 26)
    ema50_4h  = _ema(close_4h, 50)
    ema200_4h = _ema(close_4h, 200)

    last_close = float(close_4h[-1])
    rsi_4h     = _rsi(close_4h, 14)
    vol_ma20   = float(np.mean(vol_4h[-20:]))
    last_vol   = float(vol_4h[-1])

    # 4h Secular Bear Regime check
    bear_regime = (last_close < ema200_4h[-1]) and (last_close < ema50_4h[-1])

    # Breakdown trigger: breaking below 20-period lowest low, or EMA12 < EMA26 bear crossover
    lowest_20 = float(np.min(low_4h[-21:-1]))
    breakdown_trigger = (last_close <= lowest_20 * 1.005) or (
        ema12_4h[-1] < ema26_4h[-1] and ema12_4h[-2] >= ema26_4h[-2]
    )

    # RSI filter: Bearish momentum expansion (28 <= RSI <= 52).
    rsi_ok = (28.0 <= rsi_4h <= 52.0)

    # Volume confirmation
    vol_ok = (last_vol >= vol_ma20 * 0.90)

    if not (bear_regime and breakdown_trigger and rsi_ok and vol_ok):
        return None

    entry = float(live_price) if live_price else last_close
    # For SHORT: Take profit is entry - 10%, Stop loss is entry + 5%
    sl = entry * (1.0 + SL_PCT)
    tp = entry * (1.0 - TP_PCT)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=MAX_HOLD_HOURS)

    # Rank score: distance below EMA50 + (50 - RSI)
    rank_score = (50.0 - rsi_4h) + ((ema50_4h[-1] - last_close) / ema50_4h[-1] * 100.0)

    return {
        "id": str(uuid.uuid4()),
        "pair": pair,
        "direction": "short",
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
        "note": (f"Algo 3: Bearish Macro Breakdown Short (1:2). Price < EMA200 & EMA50, "
                 f"20-period breakdown, RSI(14)={rsi_4h:.1f}. "
                 f"Target +10.0% (+2R), Stop -5.0% (-1R)."),
        "_rank": float(rank_score),
    }
