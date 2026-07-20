"""
Backtest / simulation for the NIFTY option signal strategy.

IMPORTANT — read this to understand what the numbers mean:

NSE does not give free HISTORICAL option prices. So we cannot replay real
option premiums. Instead we:

  1. Backtest the SIGNAL LOGIC on real NIFTY index history (from yfinance).
  2. Walk each trade forward bar-by-bar until the index hits the stop or the
     target (or the data ends).
  3. Convert the index move into an approximate OPTION P&L using a delta model:

        option_pnl_per_lot = (index_move_in_favour) * delta * lot_size

     For an ATM option, delta ~= 0.5. This is a first-order approximation:
     it IGNORES theta (time decay) and gamma/vega. Real option P&L on winners
     is usually a bit HIGHER (gamma helps) and on losers a bit WORSE (theta
     bleeds), so treat the expectancy as indicative, not exact.

POSITION SIZING to your rupee risk limit:

  Max loss per trade is capped at MAX_LOSS (default range 1000-1500).
  Risk per 1 lot = (stop distance in index points) * delta * LOT_SIZE.
  lots = floor(MAX_LOSS / risk_per_lot), clamped to >= 1.
  If 1 lot already risks more than MAX_LOSS we still take 1 lot but flag it,
  because you cannot trade a fractional lot.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Callable, List, Optional

import pandas as pd

from data_feed import get_index_history
from strategy import StrategyParams, add_indicators, evaluate_row, Signal

# NIFTY contract spec (as of 2024-25). One lot = 75 (was 50 pre-Apr-2024,
# 25 for some periods). Adjust here if the exchange revises it.
LOT_SIZE = 75


@dataclass
class TradeResult:
    entry_time: str
    exit_time: str
    side: str
    entry_index: float
    exit_index: float
    outcome: str          # "TARGET", "STOP", or "EOD/EXPIRE"
    lots: int
    index_move: float     # signed, in favour of the position
    pnl: float            # rupees, after sizing
    risk_at_entry: float  # rupees risked on this trade


def simulate_trade(
    df: pd.DataFrame,
    start_i: int,
    sig: Signal,
    p,
    max_loss: float,
    max_hold_bars: int,
    reversal_exit: bool = False,
    fixed_target_rs: float = 0.0,
) -> TradeResult:
    """
    Walk forward from the signal bar until stop/target/timeout.

    Stop-loss is RUPEE-BASED: we exit the moment the option's approximate loss
    reaches `max_loss` (your Rs.1000-1500 budget). We convert that rupee stop
    back into an index level so we can test it against the OHLC bars:

        stop_index_move = max_loss / (delta * LOT_SIZE)   [always 1 lot]

    Exit priority on each bar:
      1. Rupee stop-loss hit  -> "STOP"      (your capital protection floor)
      2. If reversal_exit: Supertrend flips against the position at bar close
         -> "REVERSAL" (trend/sentiment changed, book what's there)
      3. Fixed ATR target hit -> "TARGET"    (only when reversal_exit is off)
      4. End of day / max hold -> "EOD/SQUAREOFF"

    With reversal_exit=True there is NO fixed target: we ride the trend and let
    the Supertrend flip tell us to get out, capped by the rupee stop.
    """
    delta = p.option_delta
    entry = sig.entry
    is_ce = sig.side == "CE"
    lots = 1  # 1 lot; the rupee stop is what caps the loss, not lot count
    rs_per_point = delta * LOT_SIZE  # rupee value of 1 index point (1 lot)

    # Index distance that corresponds to a `max_loss` rupee loss on 1 lot
    stop_move = max_loss / rs_per_point
    if is_ce:
        rupee_stop_index = entry - stop_move
    else:
        rupee_stop_index = entry + stop_move
    # Target: either a fixed rupee-profit level (high win-rate style) or the
    # signal's own index target (trend/mean-rev default).
    if fixed_target_rs > 0:
        tgt_move = fixed_target_rs / rs_per_point
        target_index = entry + tgt_move if is_ce else entry - tgt_move
    else:
        target_index = sig.target_index
    risk_at_entry = stop_move * rs_per_point * lots  # ~= max_loss

    # Trailing-stop config: once open profit >= trigger, ratchet the stop to a
    # level that locks in `trail_lock_rs`. Only ever tightens (never loosens).
    trail_on = bool(getattr(p, "trail_trigger_rs", 0))
    trail_trigger_rs = getattr(p, "trail_trigger_rs", 0) or 0.0
    trail_lock_rs = getattr(p, "trail_lock_rs", 0) or 0.0
    trail_trigger_pts = trail_trigger_rs / rs_per_point
    trail_lock_pts = trail_lock_rs / rs_per_point
    trailed = False  # becomes True once the trail has armed

    # Intraday only: never hold past the signal's own trading day.
    entry_day = df.index[start_i].date()
    # Last bar index that is still on the same calendar day as the entry.
    same_day_end = start_i
    for k in range(start_i + 1, len(df)):
        if df.index[k].date() == entry_day:
            same_day_end = k
        else:
            break

    # Force-exit at the earlier of: max_hold_bars, end-of-day, or data end.
    hard_exit = min(start_i + max_hold_bars, same_day_end, len(df) - 1)

    exit_i = hard_exit
    outcome = "EOD/SQUAREOFF"
    exit_index = float(df.iloc[exit_i]["Close"])

    has_st_dir = "st_dir" in df.columns
    for j in range(start_i + 1, hard_exit + 1):
        hi = float(df.iloc[j]["High"])
        lo = float(df.iloc[j]["Low"])
        # st_dir only needed for reversal exit; strategies without a
        # Supertrend column (mean-rev, S/R) simply can't reversal-exit.
        st_dir = df.iloc[j]["st_dir"] if (reversal_exit and has_st_dir) else 0

        # 0. Arm/advance the trailing stop using the favourable extreme so far.
        #    For a CE the best-case move is the bar HIGH; for a PE, the LOW.
        if trail_on:
            fav_pts = (hi - entry) if is_ce else (entry - lo)
            if fav_pts >= trail_trigger_pts:
                if is_ce:
                    new_stop = entry + trail_lock_pts
                    rupee_stop_index = max(rupee_stop_index, new_stop)
                else:
                    new_stop = entry - trail_lock_pts
                    rupee_stop_index = min(rupee_stop_index, new_stop)
                trailed = True

        # 1. Stop-loss (initial rupee stop, or the trailed level) — first priority.
        if is_ce:
            if lo <= rupee_stop_index:
                outcome = "TRAIL" if trailed else "STOP"
                exit_index, exit_i = rupee_stop_index, j
                break
        else:
            if hi >= rupee_stop_index:
                outcome = "TRAIL" if trailed else "STOP"
                exit_index, exit_i = rupee_stop_index, j
                break

        # 2. Reversal exit: trend flipped against us -> book at this bar close.
        if reversal_exit and has_st_dir:
            reversed_against = (is_ce and st_dir == -1) or (
                not is_ce and st_dir == 1
            )
            if reversed_against:
                outcome = "REVERSAL"
                exit_index = float(df.iloc[j]["Close"])
                exit_i = j
                break
        # 3. Fixed ATR target (only when not using reversal exit).
        else:
            if is_ce and hi >= target_index:
                outcome, exit_index, exit_i = "TARGET", target_index, j
                break
            if not is_ce and lo <= target_index:
                outcome, exit_index, exit_i = "TARGET", target_index, j
                break

    # Signed index move in favour of the option holder
    if is_ce:
        index_move = exit_index - entry
    else:
        index_move = entry - exit_index

    pnl = index_move * delta * LOT_SIZE * lots

    return TradeResult(
        entry_time=sig.timestamp,
        exit_time=str(df.index[exit_i]),
        side=sig.side,
        entry_index=round(entry, 2),
        exit_index=round(exit_index, 2),
        outcome=outcome,
        lots=lots,
        index_move=round(index_move, 2),
        pnl=round(pnl, 2),
        risk_at_entry=round(risk_at_entry, 2),
    )


def run_backtest(
    period: str,
    interval: str,
    max_loss: float,
    max_hold_bars: int,
    p,
    reversal_exit: bool = False,
    source: str = "yfinance",
    months: int = 9,
    add_indicators_fn: Optional[Callable] = None,
    evaluate_row_fn: Optional[Callable] = None,
) -> List[TradeResult]:
    """
    add_indicators_fn/evaluate_row_fn let this harness run ANY strategy that
    produces the shared `Signal` dataclass (see strategy_meanrev.py /
    strategy_sr.py) -- default to the trend strategy in strategy.py so
    existing callers are unaffected.
    """
    add_indicators_fn = add_indicators_fn or add_indicators
    evaluate_row_fn = evaluate_row_fn or evaluate_row

    if source == "upstox":
        from upstox_feed import get_upstox_history
        # Upstox interval names differ ("15minute" vs yfinance "15m").
        up_interval = {"15m": "15minute", "30m": "30minute",
                       "60m": "60minute", "1h": "60minute",
                       "1d": "day"}.get(interval, "15minute")
        df = get_upstox_history(interval=up_interval, months=months)
    else:
        df = get_index_history(period=period, interval=interval)
    df = add_indicators_fn(df, p)

    trades: List[TradeResult] = []
    i = 1
    n = len(df)
    while i < n:
        sig = evaluate_row_fn(df, i, p)
        if sig is not None:
            tr = simulate_trade(
                df, i, sig, p, max_loss, max_hold_bars, reversal_exit
            )
            trades.append(tr)
            # Skip past the trade so we don't overlap positions
            i = df.index.get_loc(pd.Timestamp(tr.exit_time)) + 1 \
                if tr.exit_time in df.index else i + 1
        else:
            i += 1
    return trades


def summarize(trades: List[TradeResult], max_loss: float) -> dict:
    if not trades:
        return {"trades": 0}

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    total_pnl = sum(t.pnl for t in trades)
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1),
        "total_pnl": round(total_pnl, 0),
        "avg_pnl_per_trade": round(total_pnl / len(trades), 0),
        "avg_win": round(gross_win / len(wins), 0) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 0) if losses else 0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "max_single_loss": round(min((t.pnl for t in trades), default=0), 0),
        "max_single_win": round(max((t.pnl for t in trades), default=0), 0),
        "risk_cap_per_trade": max_loss,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest NIFTY option signals")
    ap.add_argument("--period", default="60d", help="yfinance period, e.g. 60d")
    ap.add_argument("--interval", default="15m", help="bar interval, e.g. 15m")
    ap.add_argument("--max-loss", type=float, default=3000,
                    help="rupee stop-loss per trade. 3000 was the profit peak "
                         "on 9m data (wider = bigger losses, not more wins)")
    ap.add_argument("--max-hold-bars", type=int, default=26,
                    help="force-exit after this many bars (26x15m ~= 1 day)")
    ap.add_argument("--no-reversal-exit", dest="reversal_exit",
                    action="store_false",
                    help="use a fixed ATR target instead of reversal exit")
    ap.set_defaults(reversal_exit=True)  # reversal exit is the chosen default
    ap.add_argument("--source", choices=["yfinance", "upstox"],
                    default="yfinance",
                    help="data source. upstox = free 15m data up to ~1yr+")
    ap.add_argument("--months", type=int, default=9,
                    help="months of history when --source upstox")
    args = ap.parse_args()

    p = StrategyParams()
    src_desc = (f"upstox {args.months}mo @ {args.interval}"
                if args.source == "upstox"
                else f"yfinance {args.period} @ {args.interval}")
    print(f"\nFetching NIFTY history ({src_desc}) ...")
    trades = run_backtest(
        args.period, args.interval, args.max_loss, args.max_hold_bars, p,
        reversal_exit=args.reversal_exit, source=args.source, months=args.months,
    )

    print(f"\n{'='*70}")
    print(f"BACKTEST RESULTS  (max loss/trade = Rs.{args.max_loss:.0f}, "
          f"lot size = {LOT_SIZE})")
    print(f"{'='*70}")

    try:
        from tabulate import tabulate
        rows = [
            [t.entry_time[5:16], t.side, t.entry_index, t.exit_index,
             t.outcome, t.lots, t.index_move, f"{t.pnl:,.0f}"]
            for t in trades
        ]
        print(tabulate(
            rows,
            headers=["Entry", "Side", "In", "Out", "Result",
                     "Lots", "IdxMove", "P&L Rs"],
            tablefmt="simple",
        ))
    except ImportError:
        for t in trades:
            print(t)

    s = summarize(trades, args.max_loss)
    print(f"\n{'-'*70}\nSUMMARY")
    for k, v in s.items():
        print(f"  {k:>22}: {v}")

    print(f"\nNOTE: Option P&L is a delta-based approximation (delta="
          f"{p.option_delta}). It ignores theta/vega. Treat expectancy as "
          f"indicative. See docstring in backtest.py.\n")


if __name__ == "__main__":
    main()
