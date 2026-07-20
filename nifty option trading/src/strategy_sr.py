"""
ALTERNATIVE APPROACH: support/resistance BOUNCE on NIFTY.

Levels are built from SWING points (fractal highs/lows), not indicators:

  A bar `i` is a swing HIGH if its High is the max over [i-swing_lookback,
  i+swing_lookback] (and symmetric for swing LOW). This is the classic
  "fractal" pivot definition -- no lookahead once we require the confirming
  bars on the right, i.e. a swing at bar i is only known `swing_lookback`
  bars later, which the level-building step respects.

  Nearby swing points (within `cluster_pct` of each other) are merged into a
  single LEVEL, and a level's strength = how many swings formed it (more
  touches = more respected level). Only the `max_levels` strongest/most
  recent levels are kept, and levels older than `level_lookback_bars` are
  dropped so the map tracks the current regime, not ancient history.

  ENTRY (bounce, mean-reversion style -- same trade shape as
  strategy_meanrev.py, different level source):

    BUY CE near SUPPORT when:
      - Close comes within `touch_pct` of a support level
      - RSI < rsi_oversold                       (momentum exhausted)
      - then price ticks back UP (close > prior close)   -> bounce starting
      - not a strong downtrend (ADX high + -DI>+DI)       (don't fight a trend
        that's about to blow through the level)

    BUY PE near RESISTANCE when the mirror image holds.

  TARGET: the next level in the direction of the trade (or a fixed R:R
  fallback if none is in range). STOP: just beyond the level being traded
  (it failed if price closes through it), floored by a minimum ATR distance
  so the stop is never unrealistically tight.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import List, Optional

import pandas as pd

from indicators import rsi, atr, adx
from strategy import Signal  # reuse the same Signal dataclass


@dataclass
class SRParams:
    swing_lookback: int = 3        # bars on each side to confirm a fractal swing
    cluster_pct: float = 0.15      # merge swings within this % of each other into one level
    level_lookback_bars: int = 400  # ignore swings older than this (~ a few weeks of 15m bars)
    max_levels: int = 8            # keep only the strongest/most recent levels
    touch_pct: float = 0.15        # "near a level" = within this % of it
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    atr_period: int = 14
    min_stop_atr_mult: float = 0.8  # stop can't be tighter than this many ATRs
    stop_buffer_atr_mult: float = 0.3  # extra room beyond the level for the stop
    default_target_atr_mult: float = 4.0  # used when no further level is in range
    option_delta: float = 0.5
    # Block fading INTO a strong trend (bounce's main failure mode)
    adx_period: int = 14
    trend_block_adx: float = 30.0
    # Time window (IST)
    entry_start: dtime = dtime(9, 30)
    entry_end: dtime = dtime(15, 0)
    use_time_filter: bool = True
    # Kept so simulate_trade's shared signature is happy (no trailing / no
    # Supertrend-based reversal exit for this strategy).
    trail_trigger_rs: float = 0.0
    trail_lock_rs: float = 500.0
    target_atr_mult: float = 0.0  # unused; target comes from the level map


@dataclass
class _Level:
    price: float
    touches: int = 1
    last_bar: int = 0


def _find_swings(df: pd.DataFrame, lookback: int) -> List[tuple]:
    """Return [(bar_index, price, kind)] for confirmed fractal swing points.
    kind is 'H' (swing high) or 'L' (swing low)."""
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    n = len(df)
    swings = []
    for i in range(lookback, n - lookback):
        window_hi = highs[i - lookback: i + lookback + 1]
        if highs[i] == window_hi.max() and (window_hi == highs[i]).sum() == 1:
            swings.append((i, float(highs[i]), "H"))
        window_lo = lows[i - lookback: i + lookback + 1]
        if lows[i] == window_lo.min() and (window_lo == lows[i]).sum() == 1:
            swings.append((i, float(lows[i]), "L"))
    return swings


def _cluster_levels(
    swings: List[tuple], upto_bar: int, p: SRParams
) -> List[_Level]:
    """Build merged levels from swings confirmed at or before `upto_bar`,
    dropping ones older than level_lookback_bars. Returns strongest/most
    recent `max_levels` levels, each carrying a touch count."""
    recent = [
        s for s in swings
        if s[0] <= upto_bar and s[0] >= upto_bar - p.level_lookback_bars
    ]
    levels: List[_Level] = []
    for bar_i, price, _kind in sorted(recent, key=lambda s: s[0]):
        merged = False
        for lv in levels:
            if abs(price - lv.price) / lv.price * 100.0 <= p.cluster_pct:
                # running average keeps the level centred on its cluster
                lv.price = (lv.price * lv.touches + price) / (lv.touches + 1)
                lv.touches += 1
                lv.last_bar = bar_i
                merged = True
                break
        if not merged:
            levels.append(_Level(price=price, touches=1, last_bar=bar_i))

    levels.sort(key=lambda lv: (lv.touches, lv.last_bar), reverse=True)
    return levels[: p.max_levels]


def add_indicators_sr(df: pd.DataFrame, p: SRParams) -> pd.DataFrame:
    out = df.copy()
    out["rsi"] = rsi(out["Close"], p.rsi_period)
    out["atr"] = atr(out, p.atr_period)
    a = adx(out, p.adx_period)
    out["adx"] = a["adx"]
    out["plus_di"] = a["plus_di"]
    out["minus_di"] = a["minus_di"]
    # Precompute all confirmed swings once; level maps are built per-bar from
    # this list in evaluate_row_sr (cheap slice + cluster, not a re-scan).
    out.attrs["swings"] = _find_swings(out, p.swing_lookback)
    return out


def evaluate_row_sr(
    df: pd.DataFrame, i: int, p: SRParams
) -> Optional[Signal]:
    if i < 1:
        return None
    row = df.iloc[i]
    prev = df.iloc[i - 1]

    if pd.isna(row["rsi"]) or pd.isna(row["atr"]) or pd.isna(row["adx"]):
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

    # A swing at bar j is only "known" once its confirming right-side bars
    # exist, i.e. at bar j + swing_lookback. Only use levels confirmed by now.
    swings: List[tuple] = df.attrs.get("swings", [])
    knowable_upto = i - p.swing_lookback
    if knowable_upto < 0:
        return None
    levels = _cluster_levels(swings, knowable_upto, p)
    if not levels:
        return None

    strong_down = _adx > p.trend_block_adx and row["minus_di"] > row["plus_di"]
    strong_up = _adx > p.trend_block_adx and row["plus_di"] > row["minus_di"]

    prices = sorted(lv.price for lv in levels)

    def _nearest_below(x: float) -> Optional[float]:
        cands = [pr for pr in prices if pr < x - 1e-9]
        return max(cands) if cands else None

    def _nearest_above(x: float) -> Optional[float]:
        cands = [pr for pr in prices if pr > x + 1e-9]
        return min(cands) if cands else None

    # --- Support bounce (bullish) ---
    support = _nearest_below(close)
    near_support = support is not None and abs(close - support) / support * 100.0 <= p.touch_pct
    bullish = (
        near_support
        and _rsi < p.rsi_oversold
        and close > prev_close
        and not strong_down
    )

    # --- Resistance rejection (bearish) ---
    resistance = _nearest_above(close)
    near_resistance = (
        resistance is not None and abs(close - resistance) / resistance * 100.0 <= p.touch_pct
    )
    bearish = (
        near_resistance
        and _rsi > p.rsi_overbought
        and close < prev_close
        and not strong_up
    )

    if bullish and bearish:
        # Ambiguous bar (rare, tight level clusters) -- skip rather than guess.
        return None
    if not (bullish or bearish):
        return None

    min_stop = p.min_stop_atr_mult * _atr

    if bullish:
        side = "CE"
        stop_index = min(
            support - p.stop_buffer_atr_mult * _atr,
            close - min_stop,
        )
        next_up = _nearest_above(close)
        target_index = (
            next_up if next_up is not None
            else close + p.default_target_atr_mult * _atr
        )
        note = (
            f"S/R bounce: price near support {support:.0f} "
            f"(RSI {_rsi:.0f} oversold), turning up -> target next level "
            f"{target_index:.0f}."
        )
    else:
        side = "PE"
        stop_index = max(
            resistance + p.stop_buffer_atr_mult * _atr,
            close + min_stop,
        )
        next_down = _nearest_below(close)
        target_index = (
            next_down if next_down is not None
            else close - p.default_target_atr_mult * _atr
        )
        note = (
            f"S/R rejection: price near resistance {resistance:.0f} "
            f"(RSI {_rsi:.0f} overbought), turning down -> target next level "
            f"{target_index:.0f}."
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
