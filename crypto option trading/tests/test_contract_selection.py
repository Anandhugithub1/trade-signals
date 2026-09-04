"""
Tests for option CONTRACT selection (expiry + strike + premium conversion).

These cover the two live bugs found on 2026-09-04:

  1. Expiry: the original code took Deribit's NEAREST expiry, which is
     routinely <24h out, for a trade held up to 72h -- so the named contract
     could expire worthless mid-trade regardless of direction.
  2. Denomination: Deribit quotes BTC/ETH options in units of the UNDERLYING,
     but the returned keys were named `*_usd` while holding the raw coin
     figure (off by ~5 orders of magnitude).

Run:  python -m pytest tests/ -q      (from "crypto option trading/")
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import live_signal  # noqa: E402
from live_signal import get_deribit_atm_context, MIN_EXPIRY_BUFFER_HOURS  # noqa: E402

HOUR_MS = 3600 * 1000


def _instruments(now_ms: float):
    """A Deribit-shaped instrument list with a realistic expiry ladder."""
    out = []
    for hours in (21, 45, 69, 93, 165):           # mirrors the real ladder
        exp = now_ms + hours * HOUR_MS
        for strike in (79000, 80000, 81000, 82000):
            for opt in ("call", "put"):
                suffix = "C" if opt == "call" else "P"
                out.append({
                    "instrument_name": f"BTC-{hours}H-{strike}-{suffix}",
                    "expiration_timestamp": exp,
                    "strike": float(strike),
                    "option_type": opt,
                })
    return out


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._p


def _fake_get(now_ms, mark=0.0117):
    def _get(url, params=None, timeout=None, **kw):
        if "get_instruments" in url:
            return _Resp({"result": _instruments(now_ms)})
        if "get_book_summary_by_instrument" in url:
            return _Resp({"result": [{
                "instrument_name": params["instrument_name"],
                "mark_price": mark,
                "mark_iv": 31.2,
            }]})
        raise AssertionError(f"unexpected url {url}")
    return _get


@pytest.fixture
def now_ms():
    return time.time() * 1000


def test_picks_expiry_that_outlives_the_hold(now_ms):
    """Must skip the 21/45/69h contracts and take the first >= 84h."""
    with patch.object(live_signal.requests, "get", _fake_get(now_ms)):
        ctx = get_deribit_atm_context("BTCUSDT", 81100.0)
    assert ctx is not None
    assert ctx["expiry_hours_out"] >= MIN_EXPIRY_BUFFER_HOURS
    # 93h is the first one clearing the 84h bar.
    assert 92 <= ctx["expiry_hours_out"] <= 94
    assert "-93H-" in ctx["put_instrument"]


def test_does_not_pick_the_nearest_expiry(now_ms):
    """Regression: the original bug picked min(expiration_timestamp)."""
    with patch.object(live_signal.requests, "get", _fake_get(now_ms)):
        ctx = get_deribit_atm_context("BTCUSDT", 81100.0)
    assert "-21H-" not in ctx["put_instrument"], "picked the nearest expiry again"
    assert ctx["expiry_hours_out"] > 72, "contract would expire mid-trade"


def test_falls_back_to_longest_when_nothing_clears_the_buffer(now_ms):
    """If every listed expiry is too soon, take the furthest, not the nearest."""
    def _short_ladder(url, params=None, timeout=None, **kw):
        if "get_instruments" in url:
            ins = [i for i in _instruments(now_ms)
                   if i["expiration_timestamp"] < now_ms + 70 * HOUR_MS]
            return _Resp({"result": ins})
        return _fake_get(now_ms)(url, params, timeout, **kw)

    with patch.object(live_signal.requests, "get", _short_ladder):
        ctx = get_deribit_atm_context("BTCUSDT", 81100.0)
    assert "-69H-" in ctx["put_instrument"], "should take the furthest available"


def test_selects_atm_strike(now_ms):
    """Strike must be the listed strike nearest spot (delta ~= 0.5)."""
    with patch.object(live_signal.requests, "get", _fake_get(now_ms)):
        assert get_deribit_atm_context("BTCUSDT", 81100.0)["atm_strike"] == 81000.0
        assert get_deribit_atm_context("BTCUSDT", 79900.0)["atm_strike"] == 80000.0
        assert get_deribit_atm_context("BTCUSDT", 81600.0)["atm_strike"] == 82000.0


def test_premium_is_converted_to_usd(now_ms):
    """0.0117 BTC at 81,100 spot is ~$949 -- not $0.0117."""
    spot = 81100.0
    with patch.object(live_signal.requests, "get", _fake_get(now_ms, mark=0.0117)):
        ctx = get_deribit_atm_context("BTCUSDT", spot)
    assert ctx["put_premium_coin"] == pytest.approx(0.0117)
    assert ctx["put_premium_usd"] == pytest.approx(0.0117 * spot, rel=1e-6)
    assert ctx["put_premium_usd"] > 900, "premium still coin-denominated"


def test_eth_premium_scales_to_eth_price(now_ms):
    """Same conversion must hold at ETH's very different price scale."""
    spot = 2521.55
    with patch.object(live_signal.requests, "get", _fake_get(now_ms, mark=0.0153)):
        ctx = get_deribit_atm_context("ETHUSDT", spot)
    # USD is deliberately rounded to cents by the implementation.
    assert ctx["put_premium_usd"] == pytest.approx(0.0153 * spot, abs=0.01)
    assert 20 < ctx["put_premium_usd"] < 100


def test_returns_none_on_api_failure(now_ms):
    """Caller must be able to degrade gracefully, not crash the CI run."""
    def _boom(*a, **kw):
        raise RuntimeError("deribit down")
    with patch.object(live_signal.requests, "get", _boom):
        assert get_deribit_atm_context("BTCUSDT", 81100.0) is None


def test_handles_empty_instrument_list(now_ms):
    with patch.object(live_signal.requests, "get",
                      lambda *a, **kw: _Resp({"result": []})):
        assert get_deribit_atm_context("BTCUSDT", 81100.0) is None


def test_missing_book_summary_leaves_premium_none(now_ms):
    """A contract with no quote must yield None premium, not a crash or 0."""
    def _no_summary(url, params=None, timeout=None, **kw):
        if "get_instruments" in url:
            return _Resp({"result": _instruments(now_ms)})
        return _Resp({"result": []})
    with patch.object(live_signal.requests, "get", _no_summary):
        ctx = get_deribit_atm_context("BTCUSDT", 81100.0)
    assert ctx is not None
    assert ctx["put_premium_usd"] is None
    assert ctx["put_premium_coin"] is None
