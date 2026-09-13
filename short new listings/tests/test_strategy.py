"""
Tests for the "short new listings" strategy and backtest logic.

Run:  python -m pytest tests/ -q      (from "short new listings/")
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from strategy import StrategyParams, evaluate_listing  # noqa: E402
import backtest as bt  # noqa: E402


# --------------------------- evaluate_listing ------------------------------ #

def test_fires_inside_the_entry_window():
    p = StrategyParams()
    sig = evaluate_listing("XYZUSDT", onboard_ms=0, age_days=30, live_price=1.0, p=p)
    assert sig is not None
    assert sig.symbol == "XYZUSDT"
    assert sig.entry == 1.0
    assert sig.stop_price == 1.30   # +30% adverse
    assert sig.lock_price == 0.50   # -50% favourable


def test_does_not_fire_before_the_window():
    p = StrategyParams()
    assert evaluate_listing("XYZUSDT", 0, age_days=20, live_price=1.0, p=p) is None


def test_does_not_fire_after_the_window():
    p = StrategyParams()
    assert evaluate_listing("XYZUSDT", 0, age_days=40, live_price=1.0, p=p) is None


def test_window_boundaries_are_inclusive():
    p = StrategyParams()  # 27-33 days
    assert evaluate_listing("XYZUSDT", 0, age_days=27, live_price=1.0, p=p) is not None
    assert evaluate_listing("XYZUSDT", 0, age_days=33, live_price=1.0, p=p) is not None
    assert evaluate_listing("XYZUSDT", 0, age_days=26.9, live_price=1.0, p=p) is None
    assert evaluate_listing("XYZUSDT", 0, age_days=33.1, live_price=1.0, p=p) is None


def test_returns_none_without_a_live_price():
    p = StrategyParams()
    assert evaluate_listing("XYZUSDT", 0, age_days=30, live_price=None, p=p) is None
    assert evaluate_listing("XYZUSDT", 0, age_days=30, live_price=0, p=p) is None


def test_stop_and_lock_scale_with_custom_params():
    p = StrategyParams(stop_pct=0.20, lock_pct=0.40)
    sig = evaluate_listing("XYZUSDT", 0, age_days=30, live_price=100.0, p=p)
    assert sig.stop_price == 120.0
    assert sig.lock_price == 60.0


# ------------------------------ simulate_trade ------------------------------ #

def _candles(prices, start_ms=0, day_ms=86_400_000):
    """[open, high, low, close] identical for simplicity, one per day."""
    return [[start_ms + i * day_ms, p, p, p, p, 0] for i, p in enumerate(prices)]


def test_simulate_trade_stop_loss():
    # 30 warm-up days at $1, entry day30 = $1, then it spikes +30%+ (stopped).
    prices = [1.0] * 31 + [1.35] + [1.0] * 40
    candles = _candles(prices)
    with patch.object(bt, "get_daily_klines", return_value=candles):
        p = StrategyParams(stop_pct=0.30, lock_pct=0.50, max_hold_days=30)
        r = bt.simulate_trade("XYZUSDT", 0, p, entry_day=30)
    assert r.exit_reason == "STOP"
    assert r.pnl_pct < 0


def test_simulate_trade_profit_lock():
    prices = [1.0] * 31 + [0.45] + [1.0] * 40
    candles = _candles(prices)
    with patch.object(bt, "get_daily_klines", return_value=candles):
        p = StrategyParams(stop_pct=0.30, lock_pct=0.50, max_hold_days=30)
        r = bt.simulate_trade("XYZUSDT", 0, p, entry_day=30)
    assert r.exit_reason == "LOCK"
    assert r.pnl_pct == 50.0


def test_simulate_trade_time_exit_when_neither_triggers():
    prices = [1.0] * 31 + [0.9] * 30  # drifts down 10%, never hits stop or lock
    candles = _candles(prices)
    with patch.object(bt, "get_daily_klines", return_value=candles):
        p = StrategyParams(stop_pct=0.30, lock_pct=0.50, max_hold_days=30)
        r = bt.simulate_trade("XYZUSDT", 0, p, entry_day=30)
    assert r.exit_reason == "TIME"
    assert r.pnl_pct == 10.0


def test_stop_checked_before_lock_on_the_same_bar():
    # A single bar that touches BOTH the stop and the lock level (impossible
    # in real daily data for a short, but the priority must still be
    # deterministic and match check_signals.py's "worse case first" rule).
    candles = (_candles([1.0] * 31)
               + [[31 * 86_400_000, 1.0, 1.35, 0.45, 1.0, 0]]
               + _candles([1.0] * 40, start_ms=32 * 86_400_000))
    with patch.object(bt, "get_daily_klines", return_value=candles):
        p = StrategyParams(stop_pct=0.30, lock_pct=0.50, max_hold_days=30)
        r = bt.simulate_trade("XYZUSDT", 0, p, entry_day=30)
    assert r.exit_reason == "STOP"


def test_simulate_trade_returns_none_on_insufficient_history():
    with patch.object(bt, "get_daily_klines", return_value=None):
        p = StrategyParams()
        assert bt.simulate_trade("XYZUSDT", 0, p, entry_day=30) is None


def test_simulate_trade_returns_none_on_zero_entry_price():
    candles = _candles([0.0] * 65)
    with patch.object(bt, "get_daily_klines", return_value=candles):
        p = StrategyParams()
        assert bt.simulate_trade("XYZUSDT", 0, p, entry_day=30) is None


# --------------------------- compounded_single_account ---------------------- #

def test_compounding_skips_overlapping_trades():
    r1 = bt.TradeResult("A", 1.0, 0.5, 50.0, "LOCK", entry_ms=0, exit_ms=10)
    r2 = bt.TradeResult("B", 1.0, 0.5, 50.0, "LOCK", entry_ms=5, exit_ms=20)  # overlaps r1
    r3 = bt.TradeResult("C", 1.0, 0.5, 50.0, "LOCK", entry_ms=15, exit_ms=25)  # after r1 closes
    final = bt.compounded_single_account([r1, r2, r3], start_capital=10_000.0)
    # Only r1 then r3 should be taken (r2 overlaps r1's open position).
    assert final == 10_000.0 * 1.5 * 1.5


def test_compounding_stops_at_zero():
    r1 = bt.TradeResult("A", 1.0, 2.0, -100.0, "STOP", entry_ms=0, exit_ms=10)
    r2 = bt.TradeResult("B", 1.0, 0.5, 50.0, "LOCK", entry_ms=20, exit_ms=30)
    final = bt.compounded_single_account([r1, r2], start_capital=10_000.0)
    assert final == 0.0


def test_summarize_empty():
    assert bt.summarize([]) == {"trades": 0}


def test_summarize_counts_exit_reasons():
    results = [
        bt.TradeResult("A", 1, 1.3, -30.0, "STOP", 0, 1),
        bt.TradeResult("B", 1, 0.5, 50.0, "LOCK", 0, 1),
        bt.TradeResult("C", 1, 0.9, 10.0, "TIME", 0, 1),
    ]
    s = bt.summarize(results)
    assert s["trades"] == 3
    assert s["wins"] == 2
    assert s["losses"] == 1
    assert s["exit_reasons"] == {"STOP": 1, "LOCK": 1, "TIME": 1}
