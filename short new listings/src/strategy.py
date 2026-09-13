"""
Strategy for shorting newly-listed Binance USDT perpetuals.

THIS IS THE EXACT RULE THAT WAS BACKTESTED -- nothing extra was bolted on.
Deliberately NOT implemented (despite being part of the original idea this
engine grew out of): FDV/circulating-supply filters, token-unlock calendars,
"wait for a breakdown" technical confirmation. None of those were backtested
-- they also need data Binance's API doesn't provide (FDV, unlock dates),
which would mean depending on CoinGecko/CMC per-coin, a real fragility cost
for an unproven benefit. If you want to add them later, backtest first.

RULE (validated on 163 Binance listings, Aug 2025-Sep 2026):
  ENTRY:  short at the close of the bar ~30 days after listing.
  EXIT, whichever comes first:
    - STOP: price rises 30% above entry (adverse move)      -> loss
    - LOCK: price falls 50% below entry (early profit-take) -> win, locked in
    - TIME: 30 days pass with neither triggered              -> exit at close

RESULTS (real backtest, not simulated):
  163 signals, 61.3% win rate, +$786 avg per $10k trade.
  Realistic ONE $10k account, one position at a time, compounded:
    - WITHOUT the profit-lock rule: $10,017 (+0.2%) over ~13 months
    - WITH the profit-lock rule:    $26,057 (+160.6%) over ~13 months
  The profit-lock rule is what makes this worth running -- without it the
  realistic account-level result is statistical noise.

IMPORTANT CAVEAT, not yet re-closed: a control-group test (shorting OLD,
established coins over the same calendar dates) showed statistically
INDISTINGUISHABLE performance to the raw 30-day-hold version of this rule --
meaning the apparent edge in that version was mostly "the altcoin market
fell broadly during this period", not something specific to new listings.
The profit-lock version above has NOT yet been re-tested against that same
control group. Treat the live signals from this engine as a disciplined,
defined-risk way to express a bearish view on hyped new listings -- not as
a confirmed, market-neutral edge. See README.md for the full history.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd


@dataclass
class StrategyParams:
    # Entry window, in days since listing. A WINDOW rather than an exact
    # day-30 match, deliberately: this repo already learned the hard way
    # (see "crypto option trading"'s README) that GitHub Actions cron does
    # not run reliably enough to catch an exact single day -- a coin
    # crossing day 30 between two delayed runs would otherwise be missed
    # entirely. The backtest used exactly day 30; this window tolerates
    # +/-3 days of cron jitter around that target.
    entry_window_min_days: int = 27
    entry_window_max_days: int = 33

    stop_pct: float = 0.30     # adverse move that stops the trade out
    lock_pct: float = 0.50     # favourable move that locks in profit early
    max_hold_days: int = 30    # force-exit if neither triggers


@dataclass
class Signal:
    symbol: str
    listing_date: str          # ISO date the perp was listed
    days_since_listing: float
    entry: float
    stop_price: float          # price level that stops the trade out (above entry)
    lock_price: float          # price level that locks in profit (below entry)
    note: str


def evaluate_listing(symbol: str, onboard_ms: float, age_days: float,
                      live_price: float, p: StrategyParams) -> Optional[Signal]:
    """
    A listing is eligible exactly once: when its age first falls inside the
    entry window. Callers are responsible for not re-signaling a symbol that
    already has a row (see run_signal.py) -- this function only answers
    "is this symbol in the window right now", not "have we already acted".
    """
    if not (p.entry_window_min_days <= age_days <= p.entry_window_max_days):
        return None
    if live_price is None or live_price <= 0:
        return None

    from datetime import datetime, timezone
    listing_date = datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc).date().isoformat()

    entry = live_price
    stop_price = entry * (1 + p.stop_pct)
    lock_price = entry * (1 - p.lock_pct)

    return Signal(
        symbol=symbol,
        listing_date=listing_date,
        days_since_listing=round(age_days, 1),
        entry=round(entry, 8),
        stop_price=round(stop_price, 8),
        lock_price=round(lock_price, 8),
        note=(f"Listed {round(age_days)}d ago. Short at {entry:.6g}, "
              f"stop +{p.stop_pct*100:.0f}% ({stop_price:.6g}), "
              f"lock profit at -{p.lock_pct*100:.0f}% ({lock_price:.6g}), "
              f"else close after {p.max_hold_days}d."),
    )


def signal_to_dict(sig: Signal) -> dict:
    return asdict(sig)
