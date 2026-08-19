"""
Signal strategy for crypto (BTC/ETH) options (industry-standard, filtered).

We generate BUY-side option signals (buy CALL for bullish, buy PUT for
bearish) from technical indicators on the underlying perpetual-futures price.
Buying options caps the max loss at the premium paid -- which lets us enforce
a clean USD risk cap per trade, same approach as buying NIFTY CE/PE options.

ENTRY = trend + momentum + STRENGTH (no session/time-of-day filter -- crypto
trades 24/7, there is no opening range or close to avoid):

  Base trigger (both directions):
    - Supertrend agrees with direction        (trend)
    - EMA(fast) vs EMA(slow) agrees           (short vs long trend)
    - RSI crosses the mid line                (momentum turning)

  Industry-standard filter added on top:
    1. ADX > adx_min                          (anti-chop: only trade real
                                               trends; a trigger during a flat
                                               ADX regime is the classic
                                               "choppy trap")
    2. +DI/-DI agrees with the direction      (Wilder directional confirm,
                                               optional, off by default)

The `note` field explains the main reason the signal fired.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd

from indicators import ema, rsi, supertrend, atr, adx


# ----------------------------- Parameters --------------------------------- #

@dataclass
class StrategyParams:
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    # Defaults below reflect a 24-month walk-forward parameter sweep on real
    # BTCUSDT + ETHUSDT 1h perp data (see backtest.py / README "Research
    # basis"). rsi_mid=50 (flat midline, not 52) + adx_min=25 (stricter
    # trend-strength gate than the NIFTY version's 15-20) + a *tighter*
    # target (2.5x ATR) than stop (2.0x ATR) beat every wider-target config
    # tried: PF 1.32 combined, and — importantly — profitable on BOTH BTC
    # (PF 1.30) and ETH (PF 1.34) individually, not just in aggregate. Wide
    # targets (3.5-6x ATR, the NIFTY-style "let winners run" shape) all lost
    # money here: crypto's 24/7 chop reverses trades before a distant target
    # is reached far more often than NIFTY's session-bounded moves did.
    rsi_mid: float = 50.0
    st_period: int = 10
    st_mult: float = 3.0
    atr_period: int = 14
    # --- Industry-standard entry filters ---
    adx_period: int = 14
    adx_min: float = 25.0             # trend-strength gate: skip choppy/low-ADX bars
    require_di_confirm: bool = False  # ablation: hurt PF in the sweep, off by default
    # Option-sizing / risk. Stop is USD-based (see backtest.simulate_trade);
    # sl_atr_mult/target_atr_mult are underlying-price distances used to
    # derive it. Unlike NIFTY (wide 8x target, tight rupee stop), the
    # winning crypto config uses a NARROWER target than stop distance --
    # verified by sweep, not copied from the NIFTY assumption.
    sl_atr_mult: float = 2.0
    target_atr_mult: float = 2.5
    option_delta: float = 0.5     # ATM option delta approximation
    # Trailing stop: once open profit reaches `trail_trigger_usd`, move the
    # stop up to lock in `trail_lock_usd` of profit. 0 = trailing disabled.
    trail_trigger_usd: float = 0.0
    trail_lock_usd: float = 0.0
    # Minimum bars between the trend flipping and a signal firing again in
    # the SAME direction -- crypto has no session boundary to reset chatter,
    # so without this a strong trend can retrigger on every RSI wobble.
    cooldown_bars: int = 4


def add_indicators(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["Close"], p.ema_fast)
    out["ema_slow"] = ema(out["Close"], p.ema_slow)
    out["rsi"] = rsi(out["Close"], p.rsi_period)
    st = supertrend(out, p.st_period, p.st_mult)
    out["st_dir"] = st["direction"]
    out["atr"] = atr(out, p.atr_period)

    _adx = adx(out, p.adx_period)
    out["adx"] = _adx["adx"]
    out["plus_di"] = _adx["plus_di"]
    out["minus_di"] = _adx["minus_di"]

    return out


# ------------------------------- Signals ---------------------------------- #

@dataclass
class Signal:
    timestamp: str
    side: str            # "CALL" (bullish) or "PUT" (bearish)
    spot: float
    entry: float         # underlying price at entry
    stop_index: float    # underlying price that triggers stop-loss
    target_index: float  # underlying price that triggers target
    atr: float
    rsi: float
    note: str


def _rsi_cross_up(prev_rsi: float, cur_rsi: float, mid: float) -> bool:
    return prev_rsi <= mid < cur_rsi


def _rsi_cross_down(prev_rsi: float, cur_rsi: float, mid: float) -> bool:
    return prev_rsi >= mid > cur_rsi


def evaluate_row(
    df: pd.DataFrame, i: int, p: StrategyParams, last_signal_i: dict = None
) -> Optional[Signal]:
    """
    Return a Signal if the bar at index i triggers one, else None.

    `last_signal_i` (optional, {"CALL": int, "PUT": int}) lets the caller
    enforce `cooldown_bars` between same-direction signals; the backtest
    harness threads this through, live_signal.py can ignore it (only ever
    evaluates the latest bar once).
    """
    if i < 1:
        return None

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    if (pd.isna(row["atr"]) or pd.isna(row["rsi"]) or pd.isna(row["ema_slow"])
            or pd.isna(row["adx"])):
        return None

    close = float(row["Close"])
    _atr = float(row["atr"])
    _rsi = float(row["rsi"])
    _adx = float(row["adx"])

    # --- Filter: ADX trend-strength gate (anti-chop) ---
    if _adx < p.adx_min:
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

    # --- DI directional confirmation (optional) ---
    di_bull = (not p.require_di_confirm) or (row["plus_di"] > row["minus_di"])
    di_bear = (not p.require_di_confirm) or (row["minus_di"] > row["plus_di"])

    bullish = base_bull and di_bull
    bearish = base_bear and di_bear

    if not (bullish or bearish):
        return None

    side = "CALL" if bullish else "PUT"

    # --- Cooldown: avoid retriggering the same direction every few bars ---
    if last_signal_i is not None and p.cooldown_bars > 0:
        prev_i = last_signal_i.get(side)
        if prev_i is not None and (i - prev_i) < p.cooldown_bars:
            return None

    if bullish:
        stop_index = close - p.sl_atr_mult * _atr
        target_index = close + p.target_atr_mult * _atr
        note = (
            f"Uptrend: Supertrend up, EMA{p.ema_fast}>EMA{p.ema_slow}, "
            f"RSI reclaimed {p.rsi_mid:.0f}, ADX {_adx:.0f}."
        )
    else:
        stop_index = close + p.sl_atr_mult * _atr
        target_index = close - p.target_atr_mult * _atr
        note = (
            f"Downtrend: Supertrend down, EMA{p.ema_fast}<EMA{p.ema_slow}, "
            f"RSI lost {p.rsi_mid:.0f}, ADX {_adx:.0f}."
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
