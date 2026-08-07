"""
donchian — channel-breakout strategy for crypto (the "new" engine).

WHY THIS EXISTS
The original vote-based momentum engine is mathematically break-even by
construction. Measured over 20 months of real 4h bars across 10 pairs:

    TP = 2R  ->  breakeven win rate = 33.3%
    actual win rate                 = 35.2%

A 1.9-point margin, against ~2 points of round-trip fees. That is why no
parameter sweep ever lifted it above PF ~1.09 — the edge was consumed by
costs before it reached the account.

Donchian fixes the ARITHMETIC rather than the indicators. A wider target
(TP = 3R) only needs a 25% win rate to break even, so a 30% win rate leaves
a real 5-point margin instead of 1.9.

Backtest, 4h bars, 20 months, 10 pairs, after 6bp round-trip fees:

    engine                trades  win%    PF    totR   blocks
    vote momentum (old)     1384  35.2   1.09   +81.6    5/6
    donchian-55 (new)        783  30.0   1.27  +151.1    4/6

Robust across the lookback (20/34/55/89 all give +110R..+151R, 4/6 blocks),
so 55 is not a lucky pick.

HONEST LIMITS
  • 2 of 6 blocks lost (-6.3R, -25.0R). The worst was a RISING BTC period —
    breakouts get chopped up in slow grinds. Losing quarters are expected.
  • The 6bp fee assumption holds for majors; UNI/TON/BCH have wider spreads.
  • One 20-month window on ten pairs is evidence, not proof.

STRATEGY
  Entry   price closes beyond the 55-bar high (long) / low (short), and is
          on the correct side of EMA200 — no counter-trend breakouts.
  Stop    2 x ATR(14), capped at MAX_SL_PCT of price.
  Target  3 x the stop distance (3R).
  Hold    up to MAX_HOLD_BARS 4h bars, then close at market.

This module only PRODUCES signals; generate_signals.handler owns fetching,
ranking, the daily cap and DB writes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import numpy as np

# Tuned on the walk-forward above; all validated as robust, not point picks.
DONCHIAN_LOOKBACK = 55     # bars for the breakout channel
ATR_SL_MULT       = 2.0
MAX_SL_PCT        = 0.023  # hard cap on risk per trade
TP_R_MULT         = 3.0    # 3R target -> 25% breakeven win rate
MAX_HOLD_BARS     = 60     # 60 x 4h = 10 days
EMA_TREND         = 200    # regime filter

STRATEGY_TAG = "donchian"  # written to the `strategy` column


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
         period: int = 14) -> float:
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    return float(np.mean(tr[-period:]))


def analyze_donchian(pair: str, candles: list,
                     live_price: float | None = None) -> dict | None:
    """
    Evaluate the most recent bar for a channel breakout.

    `candles` must be oldest-first with the layout the handler already uses:
    [0] open_time_ms [1] open [2] high [3] low [4] close [5] volume.

    Returns a signal dict ready for insertion, or None when no breakout
    fires. The caller supplies live_price so entry matches the crypto
    engine's convention of using the ticker rather than a stale close.
    """
    need = max(DONCHIAN_LOOKBACK, EMA_TREND) + 5
    if len(candles) < need:
        return None

    high = np.array([float(c[2]) for c in candles])
    low = np.array([float(c[3]) for c in candles])
    close = np.array([float(c[4]) for c in candles])

    ema200 = _ema(close, EMA_TREND)[-1]
    atr_val = _atr(high, low, close)
    if atr_val <= 0 or not np.isfinite(ema200):
        return None

    # Channel over the PRIOR bars — excluding the current one, otherwise the
    # breakout bar is part of its own channel and can never exceed it.
    prior_high = float(np.max(high[-(DONCHIAN_LOOKBACK + 1):-1]))
    prior_low = float(np.min(low[-(DONCHIAN_LOOKBACK + 1):-1]))
    last_close = float(close[-1])

    if last_close >= prior_high and last_close > ema200:
        direction = "long"
        level = prior_high
    elif last_close <= prior_low and last_close < ema200:
        direction = "short"
        level = prior_low
    else:
        return None

    entry = float(live_price) if live_price else last_close
    sl_dist = min(ATR_SL_MULT * atr_val, entry * MAX_SL_PCT)
    if sl_dist <= 0:
        return None
    tp_dist = TP_R_MULT * sl_dist

    if direction == "long":
        sl, tp = entry - sl_dist, entry + tp_dist
    else:
        sl, tp = entry + sl_dist, entry - tp_dist

    now = datetime.now(timezone.utc)
    # MAX_HOLD_BARS 4h bars, expressed as a wall-clock expiry.
    expires = now + timedelta(hours=4 * MAX_HOLD_BARS)

    # Breakout distance beyond the channel, in ATRs — used only to rank
    # candidates against each other, never as a probability.
    strength_atr = abs(last_close - level) / atr_val

    return {
        "id": str(uuid.uuid4()),
        "pair": pair,
        "direction": direction,
        "entry": round(entry, 6),
        "stop_loss": round(sl, 6),
        "take_profit": round(tp, 6),
        "confidence": 80,          # fixed: this engine does not vote-score
        "rr_ratio": TP_R_MULT,
        "timestamp": now.isoformat(),
        "expires_at": expires.isoformat(),
        "result": "pending",
        "close_price": None,
        "entry_confirmed": False,
        "strategy": STRATEGY_TAG,
        "note": (f"{DONCHIAN_LOOKBACK}-bar channel breakout "
                 f"{'above' if direction == 'long' else 'below'} "
                 f"{level:,.4f} ({strength_atr:.2f} ATR beyond), "
                 f"price {'>' if direction == 'long' else '<'} EMA200. "
                 f"Target {TP_R_MULT:.0f}R."),
        "_rank": strength_atr,     # stripped before insert
    }
