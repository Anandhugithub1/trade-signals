"""
Backtest / simulation for the crypto (BTC/ETH) option signal strategy.

IMPORTANT -- read this to understand what the numbers mean:

There is no free source of HISTORICAL Deribit option premiums at the strike/
expiry granularity we'd need. So, exactly like the NIFTY module before it:

  1. Backtest the SIGNAL LOGIC on real perpetual-futures price history
     (Binance/Bybit/OKX -- see data_feed.py).
  2. Walk each trade forward bar-by-bar until price hits the stop or the
     target (or the data ends).
  3. Convert the underlying's move into an approximate OPTION P&L using a
     delta model:

        option_pnl = (price_move_in_favour) * delta * contracts

     For an ATM option, delta ~= 0.5. This is a first-order approximation:
     it IGNORES theta (time decay) and gamma/vega. Real option P&L on
     winners is usually a bit HIGHER (gamma helps) and on losers a bit WORSE
     (theta bleeds), so treat the expectancy as indicative, not exact.

POSITION SIZING to a fixed USD risk budget (no lot size -- crypto options are
sized in underlying units, e.g. 1 BTC or fractions of it):

  Max loss per trade is capped at MAX_LOSS_USD.
  Risk per 1 unit of underlying = (stop distance in price) * delta.
  size = MAX_LOSS_USD / risk_per_unit.

MARKET STRUCTURE: crypto trades 24/7. There is no exchange close, so unlike
the NIFTY module there is no EOD square-off -- positions are held until
stop/target/max_hold_bars regardless of time of day or weekday.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, List, Optional

import pandas as pd

from data_feed import get_perp_history
from strategy import StrategyParams, add_indicators, evaluate_row, Signal


@dataclass
class TradeResult:
    symbol: str
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    exit_price: float
    outcome: str          # "TARGET", "STOP", "TRAIL", or "TIMEOUT"
    size: float            # underlying units (e.g. BTC)
    price_move: float      # signed, in favour of the position
    pnl: float              # USD, after sizing
    risk_at_entry: float   # USD risked on this trade


def simulate_trade(
    df: pd.DataFrame,
    start_i: int,
    sig: Signal,
    p,
    max_loss_usd: float,
    max_hold_bars: int,
    symbol: str = "",
) -> TradeResult:
    """
    Walk forward from the signal bar until stop/target/timeout.

    Stop-loss is USD-BASED: we exit the moment the option's approximate loss
    reaches `max_loss_usd`. We convert that USD stop back into a price level
    so we can test it against the OHLC bars:

        stop_move = max_loss_usd / (delta * size)     where size solves
        risk_at_entry ~= max_loss_usd

    Exit priority on each bar:
      1. USD stop-loss hit          -> "STOP"    (capital protection floor)
      2. Trailing stop (if armed)   -> "TRAIL"
      3. ATR target hit             -> "TARGET"
      4. max_hold_bars reached      -> "TIMEOUT"  (crypto never force-closes
                                                    for a session close --
                                                    only for a max hold)
    """
    delta = p.option_delta
    entry = sig.entry
    is_call = sig.side == "CALL"

    # Underlying units bought so that hitting the stop loses ~max_loss_usd.
    stop_move_price = p.sl_atr_mult * sig.atr
    risk_per_unit = stop_move_price * delta
    size = max_loss_usd / risk_per_unit if risk_per_unit > 0 else 0.0

    if is_call:
        stop_price = entry - stop_move_price
    else:
        stop_price = entry + stop_move_price
    target_price = sig.target_index
    risk_at_entry = stop_move_price * delta * size  # ~= max_loss_usd

    trail_on = bool(getattr(p, "trail_trigger_usd", 0))
    trail_trigger_pts = (getattr(p, "trail_trigger_usd", 0) or 0.0) / (delta * size) if size else 0.0
    trail_lock_pts = (getattr(p, "trail_lock_usd", 0) or 0.0) / (delta * size) if size else 0.0
    trailed = False

    hard_exit = min(start_i + max_hold_bars, len(df) - 1)

    exit_i = hard_exit
    outcome = "TIMEOUT"
    exit_price = float(df.iloc[exit_i]["Close"])

    for j in range(start_i + 1, hard_exit + 1):
        hi = float(df.iloc[j]["High"])
        lo = float(df.iloc[j]["Low"])

        if trail_on:
            fav_pts = (hi - entry) if is_call else (entry - lo)
            if fav_pts >= trail_trigger_pts:
                if is_call:
                    new_stop = entry + trail_lock_pts
                    stop_price = max(stop_price, new_stop)
                else:
                    new_stop = entry - trail_lock_pts
                    stop_price = min(stop_price, new_stop)
                trailed = True

        if is_call:
            if lo <= stop_price:
                outcome = "TRAIL" if trailed else "STOP"
                exit_price, exit_i = stop_price, j
                break
        else:
            if hi >= stop_price:
                outcome = "TRAIL" if trailed else "STOP"
                exit_price, exit_i = stop_price, j
                break

        if is_call and hi >= target_price:
            outcome, exit_price, exit_i = "TARGET", target_price, j
            break
        if not is_call and lo <= target_price:
            outcome, exit_price, exit_i = "TARGET", target_price, j
            break

    price_move = (exit_price - entry) if is_call else (entry - exit_price)
    pnl = price_move * delta * size

    return TradeResult(
        symbol=symbol,
        entry_time=sig.timestamp,
        exit_time=str(df.index[exit_i]),
        side=sig.side,
        entry_price=round(entry, 2),
        exit_price=round(exit_price, 2),
        outcome=outcome,
        size=round(size, 6),
        price_move=round(price_move, 2),
        pnl=round(pnl, 2),
        risk_at_entry=round(risk_at_entry, 2),
    )


def run_backtest(
    symbol: str,
    interval: str,
    max_loss_usd: float,
    max_hold_bars: int,
    p,
    months: int = 24,
    add_indicators_fn: Optional[Callable] = None,
    evaluate_row_fn: Optional[Callable] = None,
) -> List[TradeResult]:
    add_indicators_fn = add_indicators_fn or add_indicators
    evaluate_row_fn = evaluate_row_fn or evaluate_row

    df = get_perp_history(symbol, interval=interval, months=months)
    df = add_indicators_fn(df, p)

    trades: List[TradeResult] = []
    last_signal_i: dict = {}
    i = 1
    n = len(df)
    while i < n:
        sig = evaluate_row_fn(df, i, p, last_signal_i)
        if sig is not None:
            last_signal_i[sig.side] = i
            tr = simulate_trade(df, i, sig, p, max_loss_usd, max_hold_bars, symbol=symbol)
            trades.append(tr)
            # Skip past the trade so we don't overlap positions.
            next_loc = df.index.get_indexer([pd.Timestamp(tr.exit_time)])[0]
            i = (next_loc + 1) if next_loc != -1 else (i + 1)
        else:
            i += 1
    return trades


def summarize(trades: List[TradeResult], max_loss_usd: float) -> dict:
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
        "total_pnl_usd": round(total_pnl, 0),
        "avg_pnl_per_trade": round(total_pnl / len(trades), 0),
        "avg_win": round(gross_win / len(wins), 0) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 0) if losses else 0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "max_single_loss": round(min((t.pnl for t in trades), default=0), 0),
        "max_single_win": round(max((t.pnl for t in trades), default=0), 0),
        "risk_cap_per_trade_usd": max_loss_usd,
    }


def monthly_breakdown(trades: List[TradeResult]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    rows = [{"month": t.exit_time[:7], "pnl": t.pnl} for t in trades]
    df = pd.DataFrame(rows)
    g = df.groupby("month").agg(trades=("pnl", "count"), pnl=("pnl", "sum"))
    g["cumulative"] = g["pnl"].cumsum()
    return g.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest crypto option signals")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT",
                     help="comma-separated perp symbols, e.g. BTCUSDT,ETHUSDT")
    ap.add_argument("--interval", default="1h", help="bar interval: 15m/1h/4h")
    ap.add_argument("--max-loss", type=float, default=200.0,
                     help="USD stop-loss per trade")
    ap.add_argument("--max-hold-bars", type=int, default=72,
                     help="force-exit after this many bars (72x1h = 3 days)")
    ap.add_argument("--months", type=int, default=24,
                     help="months of history to backtest")
    args = ap.parse_args()

    p = StrategyParams()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    all_trades: List[TradeResult] = []
    for symbol in symbols:
        print(f"\nFetching {symbol} history ({args.months}mo @ {args.interval}) ...")
        trades = run_backtest(
            symbol, args.interval, args.max_loss, args.max_hold_bars, p,
            months=args.months,
        )
        print(f"  {symbol}: {len(trades)} trades")
        all_trades.extend(trades)

    print(f"\n{'='*78}")
    print(f"BACKTEST RESULTS  (max loss/trade = ${args.max_loss:.0f}, "
          f"{args.months} months, {'+'.join(symbols)})")
    print(f"{'='*78}")

    try:
        from tabulate import tabulate
        rows = [
            [t.symbol, t.entry_time[:16], t.side, t.entry_price, t.exit_price,
             t.outcome, t.size, t.price_move, f"{t.pnl:,.0f}"]
            for t in all_trades
        ]
        print(tabulate(
            rows,
            headers=["Symbol", "Entry", "Side", "In", "Out", "Result",
                     "Size", "Move", "P&L $"],
            tablefmt="simple",
        ))
    except ImportError:
        for t in all_trades:
            print(t)

    s = summarize(all_trades, args.max_loss)
    print(f"\n{'-'*78}\nSUMMARY (combined, {'+'.join(symbols)})")
    for k, v in s.items():
        print(f"  {k:>24}: {v}")

    mb = monthly_breakdown(all_trades)
    if not mb.empty:
        print(f"\n{'-'*78}\nMONTHLY BREAKDOWN")
        try:
            from tabulate import tabulate
            print(tabulate(mb.values.tolist(), headers=list(mb.columns),
                            tablefmt="simple", floatfmt=",.0f"))
        except ImportError:
            print(mb.to_string(index=False))

    print(f"\nNOTE: Option P&L is a delta-based approximation (delta="
          f"{p.option_delta}). It ignores theta/vega. Treat expectancy as "
          f"indicative. See docstring in backtest.py.\n")


if __name__ == "__main__":
    main()
