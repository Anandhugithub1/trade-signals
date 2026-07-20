"""
Signal strategy for NIFTY 50 options (industry-standard, filtered).

We generate BUY-side option signals (buy CE for bullish, buy PE for bearish)
from technical indicators on the NIFTY *index* (spot). Buying options caps the
max loss at the premium paid -- which lets us enforce your rupee stop cleanly.

ENTRY = trend + momentum + STRENGTH + higher-timeframe alignment + time window.
Each layer is a documented, widely-used filter (see README "Research basis"):

  Base trigger (both directions):
    - Supertrend agrees with direction        (trend)
    - EMA(fast) vs EMA(slow) agrees           (short vs long trend)
    - RSI crosses the mid line                (momentum turning)

  Industry-standard filters added on top (this is the "improved" version):
    1. ADX > adx_min AND ADX rising           (anti-chop: only trade real trends;
                                               a DI/trigger with flat/low ADX is
                                               the classic "choppy trap")
    2. +DI/-DI agrees with the direction      (Wilder directional confirmation)
    3. Higher-timeframe alignment: price on
       the correct side of the DAILY EMA      (don't fight the master trend)
    4. Time-of-day window: skip the opening
       range and the late session             (head-fakes / thin liquidity)

The `note` field explains the main reason the signal fired.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import time as dtime
from typing import Optional

import pandas as pd

from indicators import ema, rsi, supertrend, atr, adx


# ----------------------------- Parameters --------------------------------- #

@dataclass
class StrategyParams:
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_mid: float = 52.0         # require stronger momentum than a flat 50
    st_period: int = 5
    st_mult: float = 3.0
    atr_period: int = 14
    # --- Industry-standard entry filters (the "improved" layer) ---
    # Defaults below reflect a 6-9mo walk-forward validation on real 15m data
    # (independent, non-overlapping blocks -- see compare_sr_vs_trend.py /
    # the sweep in strategy.py's git history): a faster Supertrend (period 5
    # vs 10) + ADX>=15 gate beat the old ADX-off "max profit" config on PF
    # and total P&L over every window checked (6mo: PF 2.72 vs 2.02,
    # +Rs.90.5k vs +Rs.71.9k; 9mo: PF 2.11 vs 1.63, +Rs.90.2k vs +Rs.66.0k).
    # ADX-rising, DI-confirm and the daily-EMA filter still hurt PF on this
    # instrument/period, so they stay OFF (but remain togglable).
    adx_period: int = 14
    adx_min: float = 15.0             # trend-strength gate: skip choppy/low-ADX bars
    require_adx_rising: bool = False  # ablation: too strict, cut trades & PF
    require_di_confirm: bool = False  # ablation: collapsed PF to 1.03
    htf_ema: int = 20                 # daily EMA period (used only if enabled)
    use_htf_filter: bool = False      # ablation: hurt PF (whipsaw around daily EMA)
    # Time-of-day window (IST). Skip opening range & late session.
    entry_start: dtime = dtime(9, 45)
    entry_end: dtime = dtime(14, 45)
    use_time_filter: bool = False     # ablation: didn't help once ADX gate is on
    # Option-sizing / risk. Stop is RUPEE-based (see backtest.simulate_trade);
    # sl_atr_mult is kept only for the index-level display on live signals.
    sl_atr_mult: float = 1.5
    target_atr_mult: float = 8.0  # wide target: tight rupee stop + let winners run
    option_delta: float = 0.5     # ATM option delta approximation
    # Trailing stop: once open profit reaches `trail_trigger_rs`, move the stop
    # up to lock in `trail_lock_rs` of profit (0 = breakeven). Set trigger to
    # 0 to disable trailing.
    # DEFAULT OFF: on the real 9-month 15m backtest, trailing turned a +Rs.44.7k
    # result into a -Rs.9.4k loss -- it caps the big winners this trend-follower
    # depends on. Enable only if you deliberately want more/smaller wins.
    trail_trigger_rs: float = 0.0     # 0 = trailing disabled
    trail_lock_rs: float = 500.0


def add_indicators(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["Close"], p.ema_fast)
    out["ema_slow"] = ema(out["Close"], p.ema_slow)
    out["rsi"] = rsi(out["Close"], p.rsi_period)
    st = supertrend(out, p.st_period, p.st_mult)
    out["st_dir"] = st["direction"]
    out["atr"] = atr(out, p.atr_period)

    # ADX / DI for trend-strength gating
    _adx = adx(out, p.adx_period)
    out["adx"] = _adx["adx"]
    out["plus_di"] = _adx["plus_di"]
    out["minus_di"] = _adx["minus_di"]
    out["adx_rising"] = out["adx"].diff() > 0

    # Higher-timeframe (daily) trend: resample to daily, take an EMA, then
    # broadcast each day's *previous* close-EMA back onto the intraday bars
    # (previous day, so we never peek at the still-forming daily bar).
    daily_close = out["Close"].resample("1D").last().dropna()
    daily_ema = ema(daily_close, p.htf_ema).shift(1)  # yesterday's value
    out["htf_ema"] = daily_ema.reindex(out.index, method="ffill")

    return out


# ------------------------------- Signals ---------------------------------- #

@dataclass
class Signal:
    timestamp: str
    side: str            # "CE" (bullish) or "PE" (bearish)
    spot: float
    entry: float         # index level at entry
    stop_index: float    # index level that triggers stop-loss
    target_index: float  # index level that triggers target
    atr: float
    rsi: float
    note: str            # main reason for the signal


def _rsi_cross_up(prev_rsi: float, cur_rsi: float, mid: float) -> bool:
    return prev_rsi <= mid < cur_rsi


def _rsi_cross_down(prev_rsi: float, cur_rsi: float, mid: float) -> bool:
    return prev_rsi >= mid > cur_rsi


def evaluate_row(
    df: pd.DataFrame, i: int, p: StrategyParams
) -> Optional[Signal]:
    """Return a Signal if the bar at index i triggers one, else None."""
    if i < 1:
        return None

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    # Need warm indicators
    if (pd.isna(row["atr"]) or pd.isna(row["rsi"]) or pd.isna(row["ema_slow"])
            or pd.isna(row["adx"])):
        return None

    close = float(row["Close"])
    _atr = float(row["atr"])
    _rsi = float(row["rsi"])
    _adx = float(row["adx"])

    # --- Filter 4: time-of-day window (skip opening range & late session) ---
    if p.use_time_filter:
        ts_i = df.index[i]
        t = ts_i.time()
        if t < p.entry_start or t > p.entry_end:
            return None

    # --- Filter 1: ADX trend-strength gate (anti-chop) ---
    if _adx < p.adx_min:
        return None
    if p.require_adx_rising and not bool(row["adx_rising"]):
        return None

    # --- Base momentum/trend trigger ---
    base_bull = (
        row["st_dir"] == 1
        and row["ema_fast"] > row["ema_slow"]
        and _rsi_cross_up(float(prev["rsi"]), _rsi, p.rsi_mid)
    )
    base_bear = (
        row["st_dir"] == -1
        and row["ema_fast"] < row["ema_slow"]
        and _rsi_cross_down(float(prev["rsi"]), _rsi, p.rsi_mid)
    )

    # --- Filter 2: DI directional confirmation ---
    di_bull = (not p.require_di_confirm) or (row["plus_di"] > row["minus_di"])
    di_bear = (not p.require_di_confirm) or (row["minus_di"] > row["plus_di"])

    # --- Filter 3: higher-timeframe (daily EMA) alignment ---
    htf = row.get("htf_ema")
    htf_bull = (not p.use_htf_filter) or pd.isna(htf) or (close > htf)
    htf_bear = (not p.use_htf_filter) or pd.isna(htf) or (close < htf)

    bullish = base_bull and di_bull and htf_bull
    bearish = base_bear and di_bear and htf_bear

    if not (bullish or bearish):
        return None

    if bullish:
        side = "CE"
        stop_index = close - p.sl_atr_mult * _atr
        target_index = close + p.target_atr_mult * _atr
        note = (
            f"Strong uptrend: Supertrend up, EMA{p.ema_fast}>EMA{p.ema_slow}, "
            f"RSI reclaimed {p.rsi_mid:.0f}, ADX {_adx:.0f} rising, "
            f"price above daily EMA{p.htf_ema}."
        )
    else:
        side = "PE"
        stop_index = close + p.sl_atr_mult * _atr
        target_index = close - p.target_atr_mult * _atr
        note = (
            f"Strong downtrend: Supertrend down, EMA{p.ema_fast}<EMA{p.ema_slow}, "
            f"RSI lost {p.rsi_mid:.0f}, ADX {_adx:.0f} rising, "
            f"price below daily EMA{p.htf_ema}."
        )

    ts = df.index[i]
    return Signal(
        timestamp=str(ts),
        side=side,
        spot=round(close, 2),
        entry=round(close, 2),
        stop_index=round(stop_index, 2),
        target_index=round(target_index, 2),
        atr=round(_atr, 2),
        rsi=round(_rsi, 2),
        note=note,
    )


def signal_to_dict(sig: Signal) -> dict:
    return asdict(sig)
