"""
ALTERNATIVE APPROACH: intraday MEAN-REVERSION on NIFTY (high win-rate style).

The trend strategy (strategy.py) wins ~32% of trades with big winners. This is
the opposite profile: fade over-stretched moves back to "fair value" for many
SMALL, high-probability wins. Research target: ~55-70% win rate.

Because the NIFTY index has no real traded volume, we cannot compute a true
VWAP. We use a BOLLINGER-BAND revert instead -- statistically the same idea:
"fair value" = the moving-average midline; the bands are +/- k standard
deviations. Price poking outside a band and snapping back is the signal.

  BUY CE (bullish bounce) when:
    - Close pierces BELOW the lower band (over-stretched down)
    - RSI < rsi_oversold                 (momentum exhausted)
    - then price ticks back UP (close > prior close)  -> reversion starting
    TARGET: the band midline (mean).   STOP: rupee stop (your Rs.1250-2000).

  BUY PE (bearish fade) when:
    - Close pierces ABOVE the upper band
    - RSI > rsi_overbought
    - then price ticks back DOWN
    TARGET: midline.   STOP: rupee stop.

Mean reversion is DANGEROUS in strong trends (price can stay stretched and keep
going). So we ADD a trend filter that BLOCKS fades against a strong trend:
skip longs when ADX is high AND -DI>+DI (strong downtrend), and vice-versa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import Optional

import pandas as pd

from indicators import ema, rsi, atr, adx
from strategy import Signal  # reuse the same Signal dataclass


@dataclass
class MeanRevParams:
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    atr_period: int = 14
    sl_atr_mult: float = 1.5       # for display only; rupee stop governs risk
    option_delta: float = 0.5
    # Block fading INTO a strong trend (mean-rev's main failure mode)
    adx_period: int = 14
    trend_block_adx: float = 30.0  # if ADX above this, don't fade the trend
    # Time window (IST): mean-rev best early & late per research; keep it wide
    entry_start: dtime = dtime(9, 30)
    entry_end: dtime = dtime(15, 0)
    use_time_filter: bool = True
    # Trailing (off by default, same rationale as trend strat)
    trail_trigger_rs: float = 0.0
    trail_lock_rs: float = 500.0
    # target_atr_mult unused here (target is the band midline) but kept so the
    # shared simulate_trade signature is happy.
    target_atr_mult: float = 0.0


def add_indicators_mr(df: pd.DataFrame, p: MeanRevParams) -> pd.DataFrame:
    out = df.copy()
    mid = out["Close"].rolling(p.bb_period).mean()
    sd = out["Close"].rolling(p.bb_period).std()
    out["bb_mid"] = mid
    out["bb_upper"] = mid + p.bb_std * sd
    out["bb_lower"] = mid - p.bb_std * sd
    out["rsi"] = rsi(out["Close"], p.rsi_period)
    out["atr"] = atr(out, p.atr_period)
    a = adx(out, p.adx_period)
    out["adx"] = a["adx"]
    out["plus_di"] = a["plus_di"]
    out["minus_di"] = a["minus_di"]
    return out


def evaluate_row_mr(
    df: pd.DataFrame, i: int, p: MeanRevParams
) -> Optional[Signal]:
    if i < 1:
        return None
    row = df.iloc[i]
    prev = df.iloc[i - 1]

    if pd.isna(row["bb_lower"]) or pd.isna(row["rsi"]) or pd.isna(row["atr"]):
        return None

    if p.use_time_filter:
        t = df.index[i].time()
        if t < p.entry_start or t > p.entry_end:
            return None

    close = float(row["Close"])
    prev_close = float(prev["Close"])
    _atr = float(row["atr"])
    _rsi = float(row["rsi"])
    _adx = float(row["adx"])
    mid = float(row["bb_mid"])

    strong_down = _adx > p.trend_block_adx and row["minus_di"] > row["plus_di"]
    strong_up = _adx > p.trend_block_adx and row["plus_di"] > row["minus_di"]

    # Bullish bounce: was below lower band, oversold, now ticking up.
    bullish = (
        prev_close <= float(prev["bb_lower"])
        and _rsi < p.rsi_oversold
        and close > prev_close
        and not strong_down          # don't catch a falling knife in a strong downtrend
    )
    # Bearish fade: was above upper band, overbought, now ticking down.
    bearish = (
        prev_close >= float(prev["bb_upper"])
        and _rsi > p.rsi_overbought
        and close < prev_close
        and not strong_up
    )

    if not (bullish or bearish):
        return None

    if bullish:
        side = "CE"
        target_index = mid                       # revert to fair value
        stop_index = close - p.sl_atr_mult * _atr
        note = (
            f"Mean-revert bounce: price pierced lower Bollinger band, "
            f"RSI {_rsi:.0f} oversold, turning up -> target the mean ({mid:.0f})."
        )
    else:
        side = "PE"
        target_index = mid
        stop_index = close + p.sl_atr_mult * _atr
        note = (
            f"Mean-revert fade: price pierced upper Bollinger band, "
            f"RSI {_rsi:.0f} overbought, turning down -> target the mean ({mid:.0f})."
        )

    return Signal(
        timestamp=str(df.index[i]),
        side=side,
        spot=round(close, 2),
        entry=round(close, 2),
        stop_index=round(stop_index, 2),
        target_index=round(target_index, 2),
        atr=round(_atr, 2),
        rsi=round(_rsi, 2),
        note=note,
    )
