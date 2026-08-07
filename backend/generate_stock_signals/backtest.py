"""
Backtest for the US stock swing strategy (handler.py).

Reuses the LIVE handler's indicator and scoring functions directly, so the
backtest cannot drift from what actually trades — the usual failure mode
where a strategy is tuned on a reimplementation that no longer matches.

Two evaluations:
  --windows   3 / 6 / 9-month trailing windows (what you asked for). These
              OVERLAP and share an end date, so treat them as a recency
              check, not independent evidence.
  --walk      N non-overlapping blocks. This is the honest test: a strategy
              that only wins on one block is fitted, not robust.

Costs: SLIPPAGE_BPS per side covers spread + commission-free broker fees on
mega-caps. Fills are modelled at bar prices; a real fill may be worse.

Run:  python backend/generate_stock_signals/backtest.py --walk 6
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the live strategy pieces. handler.py reads Supabase env vars at
# import time, so satisfy them with harmless placeholders when absent —
# the backtest never touches the database.
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "backtest")

from handler import (  # noqa: E402
    UNIVERSE, METALS, BENCHMARK, MIN_SCORE, ADX_TREND_MIN,
    ATR_SL_MULT, TP_R_MULT, MAX_HOLD_DAYS, MAX_SIGNALS, MAX_METAL_SIGNALS,
    add_indicators,
)

SLIPPAGE_BPS = 5 / 10_000     # 5 basis points per side


def load(period: str = "3y") -> dict[str, pd.DataFrame]:
    import yfinance as yf
    raw = yf.download(UNIVERSE + [BENCHMARK], period=period, interval="1d",
                      progress=False, auto_adjust=True, group_by="ticker",
                      threads=True)
    out = {}
    for t in UNIVERSE + [BENCHMARK]:
        try:
            sub = raw[t][["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(sub) > 250:
                out[t] = add_indicators(sub)
        except Exception:
            continue
    return out


def score_row(r) -> int:
    """Vote score for one bar — mirrors handler.analyze()'s scoring."""
    if any(pd.isna(v) for v in (r["ema200"], r["ema50"], r["ema20"],
                                r["adx"], r["atr"], r["rsi"])):
        return -1
    if r["adx"] < ADX_TREND_MIN:
        return -1
    if not (r["Close"] > r["ema50"] > r["ema200"]):
        return -1
    s = 0
    s += 1 if r["Close"] > r["ema200"] else -1
    s += 1 if r["Close"] > r["ema50"] else -1
    s += 1 if r["ema20"] > r["ema50"] else -1
    s += 1 if r["rsi"] > 50 else -1
    if r["vol_avg20"] and r["Volume"] / r["vol_avg20"] >= 1.5:
        s += 1
    return s


def simulate(ind: dict, days: list, use_regime: bool = True) -> list[dict]:
    spy = ind[BENCHMARK]
    tickers = [t for t in ind if t != BENCHMARK]
    trades: list[dict] = []
    open_pos: dict[str, dict] = {}

    for d in days:
        # 1) manage open positions
        for t in list(open_pos):
            x = ind[t]
            if d not in x.index:
                continue
            r = x.loc[d]
            p = open_pos[t]
            exit_px = reason = None
            if r["Low"] <= p["sl"]:
                exit_px, reason = p["sl"], "STOP"
            elif r["High"] >= p["tp"]:
                exit_px, reason = p["tp"], "TARGET"
            elif p["bars"] >= MAX_HOLD_DAYS:
                exit_px, reason = r["Close"], "TIME"
            if exit_px is not None:
                fill = exit_px * (1 - SLIPPAGE_BPS)
                trades.append({
                    "ticker": t, "in": p["date"], "out": d, "reason": reason,
                    "entry": p["entry"], "exit": fill,
                    "ret": (fill - p["entry"]) / p["entry"],
                    "R": (fill - p["entry"]) / (p["entry"] - p["sl"]),
                })
                del open_pos[t]
            else:
                p["bars"] += 1

        # 2) market regime gate
        if use_regime:
            if d not in spy.index:
                continue
            sr = spy.loc[d]
            if pd.isna(sr["ema200"]) or sr["Close"] <= sr["ema200"]:
                continue

        # 3) new entries — equities and metals fill SEPARATE slots, mirroring
        #    handler.py. A shared pool never trades metals (50 equities crowd
        #    them out), so modelling one pool would overstate diversification.
        eq_open = len([t for t in open_pos if t not in METALS])
        mt_open = len([t for t in open_pos if t in METALS])
        eq_room = MAX_SIGNALS - eq_open
        mt_room = MAX_METAL_SIGNALS - mt_open
        if eq_room <= 0 and mt_room <= 0:
            continue
        eq_c, mt_c = [], []
        for t in tickers:
            if t in open_pos or d not in ind[t].index:
                continue
            r = ind[t].loc[d]
            sc = score_row(r)
            if sc >= MIN_SCORE:
                (mt_c if t in METALS else eq_c).append((sc, t, r))
        eq_c.sort(key=lambda z: -z[0])
        mt_c.sort(key=lambda z: -z[0])
        for sc, t, r in eq_c[:max(0, eq_room)] + mt_c[:max(0, mt_room)]:
            if pd.isna(r["atr"]) or r["atr"] <= 0:
                continue
            entry = r["Close"] * (1 + SLIPPAGE_BPS)
            sl = entry - ATR_SL_MULT * r["atr"]
            open_pos[t] = {"entry": entry, "sl": sl,
                           "tp": entry + TP_R_MULT * (entry - sl),
                           "date": d, "bars": 0}
    return trades


def stats(tr: list[dict]) -> dict:
    if not tr:
        return {"trades": 0}
    R = [t["R"] for t in tr]
    rets = [t["ret"] for t in tr]
    wins = [r for r in R if r > 0]
    losses = [r for r in R if r <= 0]
    return {
        "trades": len(tr),
        "win_pct": round(100 * len(wins) / len(tr), 1),
        "avg_R": round(float(np.mean(R)), 3),
        "total_R": round(float(sum(R)), 1),
        "profit_factor": (round(sum(wins) / abs(sum(losses)), 2)
                          if losses and sum(losses) != 0 else float("inf")),
        "total_ret_pct": round(100 * sum(rets), 1),
        "avg_hold_days": round(float(np.mean([(t["out"] - t["in"]).days for t in tr])), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--walk", type=int, default=0,
                    help="run N non-overlapping walk-forward blocks")
    ap.add_argument("--period", default="3y")
    args = ap.parse_args()

    print(f"Loading {args.period} of daily bars for "
          f"{len(UNIVERSE)} instruments + {BENCHMARK} ...")
    ind = load(args.period)
    print(f"  usable: {len(ind)}")

    days = [d for d in ind[BENCHMARK].index][250:]   # skip EMA200 warm-up
    print(f"  tradeable range: {days[0].date()} -> {days[-1].date()} "
          f"({len(days)} sessions)\n")

    if args.walk:
        k = len(days) // args.walk
        print(f"WALK-FORWARD — {args.walk} independent non-overlapping blocks")
        print(f"  {'block':<26}{'trades':>8}{'win%':>7}{'PF':>7}{'total_R':>9}")
        tot = 0.0
        pos = 0
        for i in range(args.walk):
            b = days[i * k:(i + 1) * k]
            s = stats(simulate(ind, b))
            tot += s.get("total_R", 0) or 0
            if (s.get("total_R", 0) or 0) > 0:
                pos += 1
            print(f"  {str(b[0].date()) + '..' + str(b[-1].date()):<26}"
                  f"{s.get('trades', 0):>8}{s.get('win_pct', '-'):>7}"
                  f"{s.get('profit_factor', '-'):>7}{s.get('total_R', 0):>9.1f}")
        print(f"\n  profitable blocks: {pos}/{args.walk}   total {tot:+.1f}R")
        return

    print("TRAILING WINDOWS (overlapping — recency check, not independent)")
    for months in (3, 6, 9):
        sub = [d for d in days if d >= days[-1] - pd.Timedelta(days=months * 30)]
        s = stats(simulate(ind, sub))
        print(f"\n  === last {months} months "
              f"({sub[0].date()} -> {sub[-1].date()}) ===")
        for k, v in s.items():
            print(f"      {k:>16}: {v}")


if __name__ == "__main__":
    main()
