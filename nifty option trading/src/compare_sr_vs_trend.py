"""
6-month comparison: current trend strategy (strategy.py) vs the new
support/resistance bounce strategy (strategy_sr.py), same data, same harness.

Run:  python src/compare_sr_vs_trend.py
"""
from __future__ import annotations

import argparse

from backtest import LOT_SIZE, run_backtest, summarize
from strategy import StrategyParams, add_indicators, evaluate_row
from strategy_sr import SRParams, add_indicators_sr, evaluate_row_sr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--max-loss", type=float, default=3000)
    ap.add_argument("--max-hold-bars", type=int, default=26)
    args = ap.parse_args()

    print(f"\nFetching {args.months}mo of NIFTY {args.interval} bars via Upstox ...")

    print(f"\n{'='*70}\nTREND STRATEGY (strategy.py, current live logic)\n{'='*70}")
    trend_trades = run_backtest(
        period="", interval=args.interval, max_loss=args.max_loss,
        max_hold_bars=args.max_hold_bars, p=StrategyParams(),
        reversal_exit=True, source="upstox", months=args.months,
        add_indicators_fn=add_indicators, evaluate_row_fn=evaluate_row,
    )
    trend_summary = summarize(trend_trades, args.max_loss)
    for k, v in trend_summary.items():
        print(f"  {k:>22}: {v}")

    print(f"\n{'='*70}\nS/R BOUNCE STRATEGY (strategy_sr.py, new)\n{'='*70}")
    sr_trades = run_backtest(
        period="", interval=args.interval, max_loss=args.max_loss,
        max_hold_bars=args.max_hold_bars, p=SRParams(),
        reversal_exit=False, source="upstox", months=args.months,
        add_indicators_fn=add_indicators_sr, evaluate_row_fn=evaluate_row_sr,
    )
    sr_summary = summarize(sr_trades, args.max_loss)
    for k, v in sr_summary.items():
        print(f"  {k:>22}: {v}")

    print(f"\n{'='*70}\nSIDE-BY-SIDE  (last {args.months} months, Rs.{args.max_loss:.0f} stop/trade)\n{'='*70}")
    keys = ["trades", "win_rate_pct", "total_pnl", "avg_pnl_per_trade",
            "profit_factor", "max_single_loss", "max_single_win"]
    print(f"  {'metric':<22}{'Trend':>14}{'S/R Bounce':>14}")
    for k in keys:
        tv = trend_summary.get(k, "-")
        sv = sr_summary.get(k, "-")
        print(f"  {k:<22}{str(tv):>14}{str(sv):>14}")

    print(f"\nNOTE: option P&L is a delta-based approximation (see backtest.py "
          f"docstring). Lot size = {LOT_SIZE}.\n")


if __name__ == "__main__":
    main()
