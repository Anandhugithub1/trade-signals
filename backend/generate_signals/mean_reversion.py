"""
mean_reversion — range-fade strategy for crypto (replacement candidate for
the "legacy" vote-based momentum engine).

WHY THIS EXISTS
The legacy engine is momentum: it only trades WITH a confirmed trend
(ADX>=20 gate) and is arithmetically thin by its own docstring — 35.2%
win rate against a 2R target needs 33.3% to break even, a 1.9-point
margin that live fees/spread mostly consume (see generate_signals/
handler.py's module docstring). Trend-following systems are SUPPOSED to
have a modest win rate — Donchian's 30% is normal for the genre, made
profitable by a 3R target, not by winning often. If the goal is a
meaningfully HIGHER win rate, that requires a different mechanism, not a
better-tuned momentum system: mean reversion.

STRATEGY
  Regime gate   ADX(14) < ADX_MAX_TREND — the OPPOSITE of Donchian's and
                the legacy engine's gate. Momentum wants a trend to ride;
                mean reversion wants the ABSENCE of one, because a real
                trend can carry price through the entry level without
                ever reverting (mean reversion's mirror-image failure to
                momentum's "chopped up in a ranging market" — here it's
                "caught a falling knife in a real trend").
  Entry         RSI(14) < RSI_OVERSOLD and close near/below the lower
                Bollinger Band (long) — mirrored for short. Both must
                agree; neither alone is a strong enough edge.
  Falling-knife
  guard         Price must be on the FAVOURABLE side of EMA_GUARD_PERIOD
                (200) on a HIGHER timeframe check than the entry — i.e.
                only fade a dip when the larger trend isn't already
                pointed the same way as the "oversold" reading, since
                that's exactly the setup where reversion doesn't happen.
                This is the single most load-bearing guard in mean-
                reversion research: without it, "buy the dip" degrades
                into "catch the falling knife" the moment a real
                downtrend starts.
  Target        the middle Bollinger Band (the 20-period SMA) — NOT a
                stretch R-multiple. Reversion trades target the mean,
                not a breakout continuation.
  Stop          TIGHT: STOP_BAND_FRACTION x the CURRENT Bollinger Band
                width — not an independent ATR measure (see HONEST
                LIMITS: decoupling stop sizing from the same volatility
                measure the target uses was the first version's bug).
                Deliberately tighter than Donchian's stop — a mean-
                reversion trade that keeps moving against you has
                already falsified its own premise (see falling-knife
                note above), so there is no reason to give it Donchian's
                room to breathe.
  Hold          up to MAX_HOLD_BARS bars; if the mean isn't reached by
                then, close at market — reversion that hasn't happened
                by then usually isn't going to.

REWARD:RISK IS DELIBERATELY COMPRESSED, NOT A BUG
  Unlike Donchian's 3R target (needs only 25% win rate to break even),
  this engine's target-to-mean is typically close to 1:1-1:1.5 R. That
  means win rate carries the load here — this engine's own honest bar is
  a WIN RATE comfortably above 50%, not a stretch reward, because at
  ~1:1 R:R the breakeven win rate before costs is already ~50%. If this
  engine cannot clear roughly that bar in backtest, it isn't a small
  tuning problem — the premise doesn't hold on this data and it should
  not replace the legacy engine on vibes.

HONEST LIMITS (same discipline as donchian.py's own section)
  - Crypto trends more violently and reverses regime faster than equities
    (research basis: higher volatility, retail/leverage-driven cascades),
    so the ADX<20 gate will reject more candles here than in a calmer
    market, and "looks like a range" immediately before a breakout is a
    known false-positive mode. ADX is a LAGGING indicator — it can still
    read <20 for several bars after a real move has already started,
    which is exactly the false-positive window this engine is most
    exposed to.
  - FIRST VERSION BUG, caught by backtest (see test_scripts/
    backtest_mean_reversion.py): entry required price merely PAST the
    band edge with no cap on how far past, while the stop was sized off
    short-term ATR independent of how wide the bands themselves had
    become. When volatility expanded, the bands widened faster than the
    ATR-based stop did, so "oversold at the lower band" could mean price
    was already 1-2% beyond a band that had blown out during a real
    move — the falling-knife case the EMA guard was supposed to catch,
    slipping through because the EMA guard only checks DIRECTION, not
    HOW FAR price has run. Backtest result with that bug: 19.5% win rate
    over 41 trades, 24mo/15 pairs — worse than either engine it was
    meant to improve on. Fixed in two rounds: (1) capping entry to within
    MAX_BAND_OVERSHOOT band-widths of the edge (a genuine "at the edge"
    read, not "already broken out past it"); (2) a flat band-width stop
    fraction STILL let RR drift up to ~1.9-2.2 as overshoot increased,
    because entry-to-target distance grows with overshoot while a flat
    stop fraction doesn't — fixed by sizing the stop directly off the
    ACTUAL reward distance (entry to mid-band) instead, so RR lands at
    STOP_BAND_FRACTION's reciprocal by construction, not as an
    approximation that degrades with overshoot.
  - Funding-rate-based reversal signals are a real, evidenced effect in
    perpetual futures research, but funding rate is NOT computable from
    OHLCV candles alone — this v1 is candle-only and does not use it.
  - VALIDATED, 36 months / 15 pairs, after the sizing fix above:
    RSI_OVERSOLD/RSI_OVERBOUGHT at the tight 30/70 threshold gave 61.9%
    win rate / PF 1.62 but only ~14 trades/year — too rare to matter much
    annually (~Rs 3,333/yr at 1% risk on Rs 1,00,000, since 100 trades
    takes years to accumulate at that rate). Loosened to 35/65 (current
    defaults): 52.5% win rate / PF 1.11, ~73 trades/year — lower win
    rate but ~5x the volume, netting slightly HIGHER annualized profit
    (~Rs 3,667/yr) because frequency compounds a real edge better than
    rarity does. ADX_MAX_TREND must stay tight at 20, not loosened
    alongside RSI — tested ADX<25 and ADX<30 combined with the loosened
    RSI and both degraded PF toward 1.0-1.1 (legacy-engine-grade
    break-even) despite even more trades; the ADX gate is the one that
    actually protects this engine from the falling-knife failure mode,
    RSI threshold is the one that's safe to loosen for frequency.
  - The annualized profit either configuration produces is genuinely
    modest (single-digit percent of capital per year at 1% risk/trade) —
    this is a real, small, validated edge, not a significant income
    source on its own. It scales roughly linearly with risk-per-trade
    (3% risk ~= 3x the profit AND 3x the drawdown on the same historical
    losing quarters — there is no way to get the upside without the
    proportional downside).

This module only PRODUCES signals; generate_signals.handler owns fetching,
ranking, the daily cap and DB writes — same division of responsibility as
donchian.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import numpy as np

# Backtest-validated, 36mo/15 pairs — see HONEST LIMITS above for the
# frequency-vs-quality sweep that landed on these specific values.
ADX_MAX_TREND     = 20     # ONLY trade when ADX is BELOW this (ranging) —
                            # do NOT loosen this one, see HONEST LIMITS
RSI_PERIOD        = 14
RSI_OVERSOLD      = 35     # loosened from a stricter 30 — trades 5x more
RSI_OVERBOUGHT    = 65     # often at a small win-rate cost, net positive
BB_PERIOD         = 20
EMA_GUARD_PERIOD  = 200    # higher-trend filter — the falling-knife guard
MAX_BAND_OVERSHOOT = 0.5   # entry must be within this many band-widths of
                            # the band edge — see HONEST LIMITS below for why
# Stop = this fraction of the ACTUAL reward distance (entry to mid-band),
# not an independent ATR measure or a flat band-width fraction — see
# HONEST LIMITS for two rounds of why that was wrong. RR = 1/this value
# by construction, so 1.0 targets this engine's intended ~1:1 R:R
# directly, without hardcoding a target multiple the way donchian.py
# hardcodes 3R.
STOP_BAND_FRACTION = 1.0
MAX_HOLD_BARS     = 20     # shorter hold than Donchian — reversion is a quick thesis
                            # or it's wrong; 20 x 4h = ~3.3 days

STRATEGY_TAG = "mean_reversion"  # written to the `strategy` column


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """Wilder ADX — identical formula to generate_signals.handler.calc_adx,
    duplicated here (not imported) so this module stays self-contained like
    donchian.py, which duplicates its own indicator helpers rather than
    importing handler."""
    high, low, close = high.astype(float), low.astype(float), close.astype(float)
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    def _wilder(x: np.ndarray, n: int) -> np.ndarray:
        out = np.zeros(len(x))
        if len(x) < n:
            return out
        out[n - 1] = x[:n].sum()
        for i in range(n, len(x)):
            out[i] = out[i - 1] - out[i - 1] / n + x[i]
        return out

    tr_s = _wilder(tr, period)
    pdm_s = _wilder(plus_dm, period)
    mdm_s = _wilder(minus_dm, period)
    plus_di = 100 * np.divide(pdm_s, tr_s, out=np.zeros_like(tr_s), where=tr_s != 0)
    minus_di = 100 * np.divide(mdm_s, tr_s, out=np.zeros_like(tr_s), where=tr_s != 0)
    di_sum = plus_di + minus_di
    dx = 100 * np.abs(plus_di - minus_di) / np.where(di_sum == 0, 1, di_sum)
    return float(np.mean(dx[-period:]))


def _rsi(close: np.ndarray, period: int = 14) -> float:
    delta = np.diff(close.astype(float))
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_g = np.mean(gains[:period])
    avg_l = np.mean(losses[:period])
    for i in range(period, len(delta)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def _bollinger(close: np.ndarray, period: int = BB_PERIOD):
    window = close[-period:]
    mid = float(np.mean(window))
    std = float(np.std(window))
    upper = mid + 2 * std
    lower = mid - 2 * std
    return upper, mid, lower


def analyze_mean_reversion(pair: str, candles: list,
                            live_price: float | None = None) -> dict | None:
    """
    Evaluate the most recent bar for a range-fade (mean-reversion) setup.

    `candles` must be oldest-first with the layout the handler already uses:
    [0] open_time_ms [1] open [2] high [3] low [4] close [5] volume.

    Returns a signal dict ready for insertion, or None when no setup fires.
    """
    need = max(EMA_GUARD_PERIOD, BB_PERIOD, RSI_PERIOD) + 5
    if len(candles) < need:
        return None

    high = np.array([float(c[2]) for c in candles])
    low = np.array([float(c[3]) for c in candles])
    close = np.array([float(c[4]) for c in candles])

    adx = _adx(high, low, close)
    if adx >= ADX_MAX_TREND:
        return None   # a real trend is running — sit this one out, don't fade it

    rsi = _rsi(close, RSI_PERIOD)
    upper, mid, lower = _bollinger(close, BB_PERIOD)
    band_width = upper - lower
    if band_width <= 0:
        return None

    ema_guard = _ema(close, EMA_GUARD_PERIOD)[-1]
    last_close = float(close[-1])

    # Falling-knife guard, PART 1 (direction): only fade a dip when price
    # is NOT already below the higher-trend EMA (that combination is a
    # real downtrend, not a range dip). Mirror for shorts.
    #
    # Falling-knife guard, PART 2 (distance): price must be NEAR the band
    # edge, not arbitrarily far past it. An unbounded "beyond the band"
    # check let a first version of this engine fire on price that had
    # already blown 1-2% past a band still catching up to a real move —
    # ADX is a lagging indicator, so it can still read "ranging" for a
    # few bars after a real trend has started. Capping overshoot to
    # MAX_BAND_OVERSHOOT band-widths keeps this a genuine "at the edge"
    # read, not "already broken out."
    if last_close <= lower and rsi < RSI_OVERSOLD and last_close > ema_guard:
        overshoot = (lower - last_close) / band_width
        if overshoot > MAX_BAND_OVERSHOOT:
            return None
        direction = "long"
        target = mid
    elif last_close >= upper and rsi > RSI_OVERBOUGHT and last_close < ema_guard:
        overshoot = (last_close - upper) / band_width
        if overshoot > MAX_BAND_OVERSHOOT:
            return None
        direction = "short"
        target = mid
    else:
        return None

    entry = float(live_price) if live_price else last_close
    reward_dist = abs(target - entry)
    if reward_dist <= 0:
        return None

    # Stop sized as a FRACTION OF THE ACTUAL REWARD DISTANCE (entry to
    # mid-band), not a flat band-width fraction — this is the core fix,
    # v2. A flat band-width stop looked right at zero overshoot but grew
    # mismatched from the target as overshoot increased: entry starts
    # further from the edge (more overshoot) AND ends up further from the
    # target (edge-to-mid is roughly constant, but entry-to-target grows
    # with overshoot), while a flat stop fraction doesn't grow with it —
    # so RR crept up to 1.9-2.2 instead of the intended ~1:1 even after
    # capping overshoot. Sizing the stop directly off reward_dist makes
    # RR land at STOP_BAND_FRACTION's reciprocal by construction,
    # regardless of how much overshoot is present.
    sl_dist = STOP_BAND_FRACTION * reward_dist
    if sl_dist <= 0:
        return None

    if direction == "long":
        sl = entry - sl_dist
        tp = target
    else:
        sl = entry + sl_dist
        tp = target

    reward = abs(tp - entry)
    risk = abs(entry - sl)
    rr_ratio = reward / risk if risk > 0 else 0.0

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=4 * MAX_HOLD_BARS)

    return {
        "id": str(uuid.uuid4()),
        "pair": pair,
        "direction": direction,
        "entry": round(entry, 6),
        "stop_loss": round(sl, 6),
        "take_profit": round(tp, 6),
        "confidence": 80,   # fixed, same convention as donchian.py — not a vote score
        "rr_ratio": round(rr_ratio, 2),
        "timestamp": now.isoformat(),
        "expires_at": expires.isoformat(),
        "result": "pending",
        "close_price": None,
        "entry_confirmed": False,
        "strategy": STRATEGY_TAG,
        "note": (f"RSI {rsi:.0f} {'oversold' if direction == 'long' else 'overbought'} "
                 f"at {'lower' if direction == 'long' else 'upper'} Bollinger Band, "
                 f"ADX {adx:.1f} (ranging), targeting mid-band {mid:,.4f} "
                 f"({rr_ratio:.2f}R)."),
        "_rank": abs(50 - rsi),   # further from neutral RSI = ranked higher; ranking only
    }
