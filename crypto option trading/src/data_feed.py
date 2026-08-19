"""
Data access layer for crypto perpetual-futures OHLC history.

Three free sources, no API key, same provider-fallback chain already proven
in backend/generate_signals/handler.py (see PROJECT_CONTEXT.md — Binance and
Bybit are geo-blocked on some cloud/CI IPs, OKX is the reliable final leg):

  1. Binance Futures  fapi.binance.com   — deepest history, blocked in US/India
  2. Bybit Futures    api.bybit.com      — blocked on some cloud IPs (Azure)
  3. OKX               www.okx.com       — always reachable, used for deep
                                           history via history-candles + `after`
                                           cursor pagination (this module's
                                           primary path for 24mo+ backtests)

There is no official free options-chain endpoint for Deribit-style historical
IV/premium data, so — exactly like the NIFTY module used NSE spot + a delta
approximation for option P&L — this feeds the perpetual-futures price into a
delta-based option P&L model (see backtest.py).
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1/klines"
BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"
OKX_KLINES = "https://www.okx.com/api/v5/market/candles"
OKX_HISTORY_KLINES = "https://www.okx.com/api/v5/market/history-candles"

_INTERVAL_MS = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


def _okx_symbol(pair: str) -> str:
    """BTCUSDT -> BTC-USDT (OKX instId format)."""
    return pair[:-4] + "-USDT"


def _okx_bar(interval: str) -> str:
    return {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}[interval]


def _fetch_okx_history_page(inst_id: str, bar: str, after_ms: Optional[int] = None,
                             limit: int = 300) -> list:
    """
    One page of OKX history-candles. `after` = only return candles with
    timestamp < after_ms (OKX paginates backwards in time), so we walk
    from "now" back to the start of our desired window.
    """
    params = {"instId": inst_id, "bar": bar, "limit": limit}
    if after_ms is not None:
        params["after"] = str(after_ms)
    r = requests.get(OKX_HISTORY_KLINES, params=params, headers=_HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    return data  # newest-first


def get_okx_deep_history(symbol: str, interval: str = "1h",
                          months: int = 24) -> pd.DataFrame:
    """
    Walk OKX's history-candles endpoint backwards with `after` cursor
    pagination to assemble `months` of history at the given interval.
    Public endpoint, no key needed, ~300 candles/page.
    """
    inst_id = _okx_symbol(symbol) + "-SWAP"
    bar = _okx_bar(interval)
    step_ms = _INTERVAL_MS[interval]
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - months * 30 * 24 * 60 * 60 * 1000

    all_rows: list = []
    cursor = None
    seen_oldest = now_ms
    for _ in range(400):  # hard cap so a bug can't loop forever
        page = _fetch_okx_history_page(inst_id, bar, after_ms=cursor)
        if not page:
            break
        all_rows.extend(page)
        oldest_ts = int(page[-1][0])
        if oldest_ts >= seen_oldest:
            break  # not making progress
        seen_oldest = oldest_ts
        cursor = oldest_ts
        if oldest_ts <= start_ms:
            break
        time.sleep(0.12)  # be polite to the public endpoint

    if not all_rows:
        raise RuntimeError(f"OKX returned no history for {inst_id} ({bar})")

    df = _rows_to_df(all_rows, source="okx")
    df = df[df.index >= pd.Timestamp(start_ms, unit="ms", tz="UTC")]
    return df.sort_index()


def _rows_to_df(rows: list, source: str) -> pd.DataFrame:
    """
    Normalize provider-specific kline rows into a DataFrame with
    Open/High/Low/Close/Volume, indexed by a UTC DatetimeIndex.

    Binance: [openTime, open, high, low, close, volume, ...]
    Bybit:   [start, open, high, low, close, volume, turnover] (newest-first)
    OKX:     [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
             (newest-first)
    """
    out = pd.DataFrame(
        rows,
        columns=(
            ["ts", "Open", "High", "Low", "Close", "Volume"]
            + [f"extra{i}" for i in range(max(0, len(rows[0]) - 6))]
        ) if rows else [],
    )
    out = out[["ts", "Open", "High", "Low", "Close", "Volume"]]
    out["ts"] = pd.to_datetime(out["ts"].astype(float), unit="ms", utc=True)
    out = out.set_index("ts").sort_index()
    out = out[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    out = out[~out.index.duplicated(keep="last")]
    return out


def get_perp_history(symbol: str, interval: str = "1h", months: int = 24) -> pd.DataFrame:
    """
    Fetch perpetual-futures OHLC history for `symbol` (e.g. "BTCUSDT"),
    trying the shallow single-call providers first (fast, but capped at
    ~1000 bars) and falling back to OKX's paginated deep-history endpoint
    when the requested window needs more bars than that.

    Returns columns: Open, High, Low, Close, Volume, indexed by UTC time.
    """
    step_ms = _INTERVAL_MS[interval]
    bars_needed = int((months * 30 * 24 * 60 * 60 * 1000) / step_ms)

    if bars_needed <= 1000:
        df = _get_shallow_history(symbol, interval, limit=min(bars_needed + 5, 1000))
        if df is not None and not df.empty:
            return df

    # Deep history: OKX history-candles with pagination.
    return get_okx_deep_history(symbol, interval, months=months)


def _get_shallow_history(symbol: str, interval: str, limit: int = 1000) -> Optional[pd.DataFrame]:
    """Single-call fetch (<=1000 bars) with the Binance -> Bybit -> OKX fallback chain."""
    binance_iv, bybit_iv, okx_iv = {
        "15m": ("15m", "15", "15m"),
        "1h": ("1h", "60", "1H"),
        "4h": ("4h", "240", "4H"),
        "1d": ("1d", "D", "1D"),
    }[interval]

    try:
        r = requests.get(
            BINANCE_FUTURES,
            params={"symbol": symbol, "interval": binance_iv, "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            rows = r.json()
            if rows:
                return _rows_to_df(rows, source="binance")
    except Exception:
        pass

    try:
        r = requests.get(
            BYBIT_KLINES,
            params={"category": "linear", "symbol": symbol,
                    "interval": bybit_iv, "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            rows = list(reversed(r.json()["result"]["list"]))
            if rows:
                return _rows_to_df(rows, source="bybit")
    except Exception:
        pass

    try:
        r = requests.get(
            OKX_KLINES,
            params={"instId": _okx_symbol(symbol), "bar": okx_iv, "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            rows = list(reversed(r.json()["data"]))
            if rows:
                return _rows_to_df(rows, source="okx")
    except Exception:
        pass

    return None


def get_live_price(symbol: str) -> Optional[float]:
    """Real-time last-traded price, same fallback chain as history fetch."""
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": symbol}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass

    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": symbol}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            items = r.json().get("result", {}).get("list", [])
            if items:
                return float(items[0]["lastPrice"])
    except Exception:
        pass

    try:
        r = requests.get(
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": _okx_symbol(symbol) + "-SWAP"}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200 and r.json().get("data"):
            return float(r.json()["data"][0]["last"])
    except Exception:
        pass

    return None
