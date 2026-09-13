"""
Backtest for the "short new listings" strategy -- formalizes the exact
scripts run interactively to validate this engine before it went live.
Re-run this any time to check the rule still holds up on fresh data.

Unlike "crypto option trading"'s backtest, there's no delta/premium
approximation here: this is a plain perpetual-futures short, so P&L is the
raw price move. See strategy.py's module docstring for the full research
history and the outstanding control-group caveat.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Optional

from data_feed import get_usdt_perp_listings, get_daily_klines
from strategy import StrategyParams


@dataclass
class TradeResult:
    symbol: str
    entry_price: float
    exit_price: float
    pnl_pct: float          # positive = short made money
    exit_reason: str        # STOP | LOCK | TIME
    entry_ms: float
    exit_ms: float


def simulate_trade(symbol: str, onboard_ms: float, p: StrategyParams,
                    entry_day: int = 30) -> Optional[TradeResult]:
    candles = get_daily_klines(symbol, onboard_ms, limit=entry_day + p.max_hold_days + 5)
    if not candles or len(candles) < entry_day + p.max_hold_days:
        return None

    entry_price = float(candles[entry_day][4])
    if entry_price <= 0:
        return None

    stop_price = entry_price * (1 + p.stop_pct)
    lock_price = entry_price * (1 - p.lock_pct)

    exit_price, exit_reason, exit_ms = None, "TIME", None
    for i in range(entry_day + 1, min(entry_day + 1 + p.max_hold_days, len(candles))):
        high, low = float(candles[i][2]), float(candles[i][3])
        if high >= stop_price:
            exit_price, exit_reason, exit_ms = stop_price, "STOP", candles[i][0]
            break
        if low <= lock_price:
            exit_price, exit_reason, exit_ms = lock_price, "LOCK", candles[i][0]
            break

    if exit_price is None:
        end_idx = min(entry_day + p.max_hold_days, len(candles) - 1)
        exit_price = float(candles[end_idx][4])
        exit_ms = candles[end_idx][0]

    pnl_pct = (entry_price - exit_price) / entry_price
    return TradeResult(
        symbol=symbol, entry_price=entry_price, exit_price=exit_price,
        pnl_pct=round(pnl_pct * 100, 2), exit_reason=exit_reason,
        entry_ms=candles[entry_day][0], exit_ms=exit_ms,
    )


def run_backtest(p: StrategyParams, entry_day: int = 30,
                  min_age_days: float = 65, max_age_days: float = 420) -> List[TradeResult]:
    listings = get_usdt_perp_listings(min_age_days=min_age_days, max_age_days=max_age_days)
    results = []
    for L in listings:
        r = simulate_trade(L["symbol"], L["onboard_ms"], p, entry_day=entry_day)
        if r:
            results.append(r)
    return results


def summarize(results: List[TradeResult]) -> dict:
    if not results:
        return {"trades": 0}
    wins = [r for r in results if r.pnl_pct > 0]
    losses = [r for r in results if r.pnl_pct <= 0]
    total = sum(r.pnl_pct for r in results)
    return {
        "trades": len(results),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(results), 1),
        "avg_pnl_pct": round(total / len(results), 2),
        "avg_win_pct": round(sum(r.pnl_pct for r in wins) / len(wins), 2) if wins else 0,
        "avg_loss_pct": round(sum(r.pnl_pct for r in losses) / len(losses), 2) if losses else 0,
        "exit_reasons": {
            k: sum(1 for r in results if r.exit_reason == k)
            for k in ("STOP", "LOCK", "TIME")
        },
    }


def compounded_single_account(results: List[TradeResult], start_capital: float = 10_000.0) -> float:
    """
    Realistic ONE-account, one-trade-at-a-time result: only take a signal if
    it doesn't overlap the still-open previous position. This is the number
    that matters -- the flat per-trade average hides that most "signals"
    can't actually be taken with a single account (see README).
    """
    ordered = sorted(results, key=lambda r: r.entry_ms)
    balance = start_capital
    last_exit_ms = 0
    for r in ordered:
        if r.entry_ms < last_exit_ms:
            continue
        balance *= (1 + r.pnl_pct / 100)
        last_exit_ms = r.exit_ms
        if balance <= 0:
            return 0.0
    return balance


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest: short new Binance listings")
    ap.add_argument("--stop-pct", type=float, default=0.30)
    ap.add_argument("--lock-pct", type=float, default=0.50)
    ap.add_argument("--max-hold-days", type=int, default=30)
    ap.add_argument("--entry-day", type=int, default=30)
    ap.add_argument("--start-capital", type=float, default=10_000.0)
    args = ap.parse_args()

    p = StrategyParams(stop_pct=args.stop_pct, lock_pct=args.lock_pct,
                        max_hold_days=args.max_hold_days)

    print(f"\nFetching Binance USDT-perp listings and backtesting "
          f"(entry day {args.entry_day}, stop {p.stop_pct*100:.0f}%, "
          f"lock {p.lock_pct*100:.0f}%, max hold {p.max_hold_days}d) ...")
    results = run_backtest(p, entry_day=args.entry_day)

    s = summarize(results)
    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for k, v in s.items():
        print(f"  {k:>16}: {v}")

    final = compounded_single_account(results, args.start_capital)
    ret_pct = (final / args.start_capital - 1) * 100
    print(f"\n  ONE ${args.start_capital:,.0f} account, one trade at a time, compounded:")
    print(f"    final balance: ${final:,.0f}  ({'+' if ret_pct >= 0 else ''}{ret_pct:.1f}%)")

    print("\nNOTE: no control-group re-check on this exact rule set yet -- see "
          "strategy.py's docstring before treating this as a confirmed edge.\n")


if __name__ == "__main__":
    main()
