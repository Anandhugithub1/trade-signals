"""
Quick parameter sweep to find settings that are profitable UNDER the hard
constraints: rupee stop-loss (Rs.1000-1500) and intraday-only exits.

We vary the target distance and the RSI filter strength, keeping the rupee
stop fixed. Prints a ranked table by total P&L / profit factor.
"""
from __future__ import annotations

import itertools

from data_feed import get_index_history
from strategy import StrategyParams, add_indicators, evaluate_row
from backtest import simulate_trade, summarize
import pandas as pd


def backtest_with(df: pd.DataFrame, p: StrategyParams, max_loss: float,
                  max_hold_bars: int):
    trades = []
    i = 1
    n = len(df)
    while i < n:
        sig = evaluate_row(df, i, p)
        if sig is not None:
            tr = simulate_trade(df, i, sig, p, max_loss, max_hold_bars)
            trades.append(tr)
            if tr.exit_time in df.index:
                i = df.index.get_loc(pd.Timestamp(tr.exit_time)) + 1
            else:
                i += 1
        else:
            i += 1
    return trades


def main():
    max_loss = 1250
    max_hold = 26  # a full 15m trading day is ~25 bars
    base = get_index_history("60d", "15m")

    results = []
    target_mults = [3.0, 4.0, 5.0, 6.0, 8.0]
    rsi_mids = [50.0, 52.0, 55.0]     # require stronger momentum
    st_mults = [2.0, 3.0]

    for tm, rmid, stm in itertools.product(target_mults, rsi_mids, st_mults):
        p = StrategyParams(
            target_atr_mult=tm, rsi_mid=rmid, st_mult=stm
        )
        df = add_indicators(base, p)
        trades = backtest_with(df, p, max_loss, max_hold)
        s = summarize(trades, max_loss)
        if s.get("trades", 0) >= 8:  # ignore too-few-trade configs
            results.append((tm, rmid, stm, s))

    results.sort(key=lambda r: r[3]["total_pnl"], reverse=True)

    print(f"\n{'target':>7} {'rsi':>5} {'st':>4} | "
          f"{'trades':>6} {'win%':>5} {'PF':>5} {'totPnL':>9} {'avgPnL':>7}")
    print("-" * 60)
    for tm, rmid, stm, s in results[:12]:
        print(f"{tm:>7} {rmid:>5} {stm:>4} | "
              f"{s['trades']:>6} {s['win_rate_pct']:>5} {s['profit_factor']:>5} "
              f"{s['total_pnl']:>9,.0f} {s['avg_pnl_per_trade']:>7,.0f}")


if __name__ == "__main__":
    main()
