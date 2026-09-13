"""
Tests for the Binance-geo-block fallback fix in data_feed.py.

Reproduces the actual live failure (fapi.binance.com -> 451 from GitHub
Actions) and verifies, in order of preference:
  1. www.binance.com/fapi/v1/* -- the SAME Binance data via a different
     hostname (verified live against the real API before shipping) --
     answers first when fapi.binance.com fails.
  2. get_daily_klines falls back further to Bybit (correct forward-time
     order) if BOTH Binance hosts fail.
  3. get_usdt_perp_listings degrades to [] instead of raising when every
     Binance host is unreachable, so run_signal.py exits cleanly instead
     of crashing the workflow.

Run:  python -m pytest tests/ -q      (from "short new listings/")
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_feed as df  # noqa: E402


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code != 200:
            import requests
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._p


def _blocked(*a, **kw):
    """Simulates the real fapi.binance.com -> 451 failure."""
    raise Exception("451 Client Error: Unavailable For Legal Reasons")


def test_get_usdt_perp_listings_degrades_to_empty_when_binance_blocked():
    with patch.object(df.requests, "get", _blocked):
        result = df.get_usdt_perp_listings()
    assert result == []  # does not raise -- this was the actual bug


def test_get_daily_klines_falls_back_to_www_binance_when_fapi_blocked():
    """www.binance.com mirrors the same Binance data -- should be preferred
    over jumping straight to a different exchange (Bybit)."""
    www_rows = [[1725494400000, "1.0", "1.1", "0.9", "1.05", "500"]]

    def _get(url, params=None, timeout=None, **kw):
        if url.startswith("https://fapi.binance.com"):
            raise Exception("451 Client Error")
        if url.startswith("https://www.binance.com"):
            return _Resp(www_rows)
        raise AssertionError(f"unexpected url {url}")

    with patch.object(df.requests, "get", _get):
        result = df.get_daily_klines("XYZUSDT", start_ms=1725494400000)

    assert result == www_rows


def test_get_daily_klines_falls_back_to_bybit_when_both_binance_hosts_blocked():
    bybit_rows = [
        # Bybit shape, newest-first: [start, open, high, low, close, volume, turnover]
        ["1725580800000", "1.10", "1.15", "1.05", "1.12", "1000", "1100"],
        ["1725494400000", "1.05", "1.12", "1.00", "1.10", "900", "950"],
    ]

    def _get(url, params=None, timeout=None, **kw):
        if "binance.com" in url:
            raise Exception("451 Client Error")
        if "bybit.com" in url:
            return _Resp({"result": {"list": bybit_rows}})
        raise AssertionError(f"unexpected url {url}")

    with patch.object(df.requests, "get", _get):
        result = df.get_daily_klines("XYZUSDT", start_ms=1725494400000, limit=200)

    assert result is not None
    # Must be returned OLDEST-first (forward chronological order), matching
    # Binance's native shape -- Bybit's raw response is newest-first.
    assert result[0][0] == "1725494400000"
    assert result[1][0] == "1725580800000"
    # Each row must be the 6-field [ts, o, h, l, c, v] shape, turnover dropped.
    assert len(result[0]) == 6


def test_get_daily_klines_returns_none_when_all_providers_fail():
    with patch.object(df.requests, "get", _blocked):
        assert df.get_daily_klines("XYZUSDT", start_ms=0) is None


def test_get_daily_klines_uses_binance_directly_when_reachable():
    binance_rows = [[1725494400000, "1.0", "1.1", "0.9", "1.05", "500"]]

    def _get(url, params=None, timeout=None, **kw):
        if "fapi.binance.com" in url:
            return _Resp(binance_rows)
        raise AssertionError("should not have called a fallback provider")

    with patch.object(df.requests, "get", _get):
        result = df.get_daily_klines("XYZUSDT", start_ms=1725494400000)

    assert result == binance_rows


def test_get_live_price_falls_back_to_www_binance_when_fapi_blocked():
    def _get(url, params=None, timeout=None, **kw):
        if url.startswith("https://fapi.binance.com"):
            raise Exception("451")
        if url.startswith("https://www.binance.com"):
            return _Resp({"price": "42.5", "symbol": "XYZUSDT"})
        raise AssertionError(f"unexpected url {url}")

    with patch.object(df.requests, "get", _get):
        price = df.get_live_price("XYZUSDT")
    assert price == 42.5


def test_get_live_price_falls_back_through_every_provider():
    def _get(url, params=None, timeout=None, **kw):
        if "binance.com" in url:
            raise Exception("451")
        if "bybit.com" in url:
            raise Exception("blocked too")
        if "okx.com" in url:
            return _Resp({"data": [{"last": "1.2345"}]})
        raise AssertionError(f"unexpected url {url}")

    with patch.object(df.requests, "get", _get):
        price = df.get_live_price("XYZUSDT")
    assert price == 1.2345


def test_get_usdt_perp_listings_falls_back_to_www_binance_when_fapi_blocked():
    body = {
        "symbols": [
            {"symbol": "XYZUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT",
             "status": "TRADING", "onboardDate": int(time.time() * 1000) - 30 * 86_400_000},
        ]
    }

    def _get(url, params=None, timeout=None, **kw):
        if url.startswith("https://fapi.binance.com"):
            raise Exception("451")
        if url.startswith("https://www.binance.com"):
            return _Resp(body)
        raise AssertionError(f"unexpected url {url}")

    with patch.object(df.requests, "get", _get):
        result = df.get_usdt_perp_listings(min_age_days=27, max_age_days=33)

    assert len(result) == 1
    assert result[0]["symbol"] == "XYZUSDT"


def test_binance_hosts_tried_in_order():
    """fapi.binance.com must be tried before www.binance.com, not the reverse."""
    assert df.BINANCE_HOSTS[0] == "https://fapi.binance.com/fapi/v1"
    assert df.BINANCE_HOSTS[1] == "https://www.binance.com/fapi/v1"


def test_okx_symbol_conversion():
    assert df._okx_symbol("BTCUSDT") == "BTC-USDT"
    assert df._okx_symbol("DOSUSDT") == "DOS-USDT"
