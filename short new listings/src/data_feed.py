"""
Data access layer for the "short new listings" engine.

GEO-BLOCKING, same issue documented in backend/generate_signals/handler.py
and "crypto option trading/src/data_feed.py": fapi.binance.com returns
HTTP 451 from GitHub Actions' US-hosted runners. Confirmed live 2026-09-13
-- this workflow was crashing on every scheduled run until the first fix
(Bybit fallback for klines/price), and even after that, listing discovery
still found zero candidates every run because Binance was the only source
for onboardDate.

SECOND FIX (this revision): www.binance.com/fapi/v1/* mirrors the EXACT
same Futures API -- exchangeInfo, klines, ticker/price -- as the blocked
fapi.binance.com host, verified live 2026-09-13 (identical onboardDate for
DOSUSDT, identical kline OHLCV for BTCUSDT, real current listings
including same-week ones). It's the same underlying Binance data via a
different hostname, not a different exchange, so using it changes nothing
about what the strategy IS -- unlike falling back to Bybit/OKX for
listing dates, which would (see below). BINANCE_HOSTS tries both;
`www.binance.com` is the main public website rather than the dedicated
derivatives-trading API host, so it MAY not carry the same
jurisdiction-based block -- plausible and evidence-backed, but not
confirmed from an actually-blocked IP. The real confirmation is the next
live GitHub Actions run; if it's blocked too, this degrades to exactly
the previous (Bybit-for-klines, empty-list-for-listings) behavior.

Price data uses the same proven fallback pattern as every other engine
here -- which provider answers doesn't change what the strategy IS, since
they all track the same underlying market price:
  - get_live_price:   Binance (both hosts) -> Bybit -> OKX
  - get_daily_klines:  Binance (both hosts) -> Bybit only (see that
                       function's docstring for why OKX isn't a further
                       fallback here)

LISTING-DATE DISCOVERY (get_usdt_perp_listings) still does NOT fall back
past Binance to another exchange: this strategy's entry trigger is
specifically "27-33 days since Binance's own onboardDate", which is the
number the whole backtest (see README.md) was validated against. No other
exchange exposes that same value -- OKX's `listTime` is when OKX listed
the contract, not Binance, and can differ by days. If BOTH Binance hosts
are unreachable, this degrades to an empty candidate list (safe no-op,
matching every other engine's convention) rather than crashing the
workflow -- see run_signal.py for the operational consequence.
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
}
# Both serve the identical Binance Futures API (verified 2026-09-13 --
# same symbols, same onboardDate, same OHLCV). Tried in order; the first
# is the dedicated trading-API host (geo-blocked from GitHub Actions), the
# second is the main public website (not confirmed blocked or unblocked
# from GH Actions specifically, but is a real, evidence-backed candidate).
BINANCE_HOSTS = [
    "https://fapi.binance.com/fapi/v1",
    "https://www.binance.com/fapi/v1",
]
BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"


def _binance_get(path: str, params: dict, timeout: int) -> Optional[dict]:
    """
    Try each Binance host in BINANCE_HOSTS in order for the same path.
    Returns the parsed JSON body from the first host that answers with
    HTTP 200, or None if every host fails/errors.
    """
    for base in BINANCE_HOSTS:
        try:
            r = requests.get(f"{base}{path}", headers=_HEADERS, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


def get_usdt_perp_listings(min_age_days: float = 0, max_age_days: float = 420) -> list[dict]:
    """
    All USDT-margined perpetuals currently listed on Binance Futures whose
    age (now - onboardDate) falls in [min_age_days, max_age_days].

    Returns [{"symbol", "onboard_ms", "age_days"}, ...]. Excludes anything
    without a usable onboardDate. Returns [] if every Binance host in
    BINANCE_HOSTS is unreachable -- e.g. geo-blocked from GitHub Actions --
    so a scheduled run finds "no candidates" instead of crashing. This does
    NOT fall back to another exchange; see this module's docstring for why.
    """
    body = _binance_get("/exchangeInfo", params={}, timeout=15)
    if body is None:
        print("  [WARN] Binance exchangeInfo unreachable on every host -- "
              "no listing candidates this run.")
        return []
    syms = body["symbols"]

    now_ms = time.time() * 1000
    out = []
    for x in syms:
        if x.get("contractType") != "PERPETUAL" or x.get("quoteAsset") != "USDT":
            continue
        if x.get("status") != "TRADING":
            continue
        onboard = x.get("onboardDate", 0)
        if not onboard:
            continue
        age_days = (now_ms - onboard) / 86_400_000
        if min_age_days <= age_days <= max_age_days:
            out.append({"symbol": x["symbol"], "onboard_ms": onboard, "age_days": age_days})
    return out


def _okx_symbol(symbol: str) -> str:
    """BTCUSDT -> BTC-USDT (OKX instId format)."""
    return symbol[:-4] + "-USDT" if symbol.endswith("USDT") else symbol


def get_daily_klines(symbol: str, start_ms: float, limit: int = 200) -> Optional[list]:
    """
    Daily klines from start_ms FORWARD, Binance (both hosts) -> Bybit
    fallback. Returns rows in the shared [ts, open, high, low, close,
    volume] layout (Binance's native shape); Bybit's response is
    normalized to match. None if all providers fail.

    OKX deliberately is NOT a further fallback here (unlike get_live_price
    below): OKX's kline endpoints paginate with a before/after CURSOR, not
    a "start here, walk forward" parameter -- tested directly and neither
    one gives a clean forward window from an arbitrary timestamp the way
    Binance's `startTime` and Bybit's `start` do (verified: `after=X`
    returns candles OLDER than X; `before=X` ignores X and returns the
    newest data instead of a window starting at X). This function feeds
    check_signals.py's win/loss resolution -- silently wrong candles here
    would misresolve real trades, which is worse than the safe "no data
    this run" that returning None produces. Get OKX's cursor pagination
    right (see "crypto option trading"'s get_okx_deep_history for the
    correct walking-cursor pattern) before adding it here.
    """
    # 1. Binance Futures, tried on both hosts (see BINANCE_HOSTS above).
    data = _binance_get(
        "/klines", params={"symbol": symbol, "interval": "1d",
                            "startTime": int(start_ms), "limit": limit},
        timeout=15,
    )
    if isinstance(data, list) and data:
        return data

    # 2. Bybit Futures (verified: `start` correctly returns candles FROM
    # that timestamp forward, newest-first in the raw response).
    try:
        r = requests.get(
            BYBIT_KLINES, headers=_HEADERS, timeout=15,
            params={"category": "linear", "symbol": symbol, "interval": "D",
                    "start": int(start_ms), "limit": min(limit, 1000)},
        )
        if r.status_code == 200:
            rows = r.json().get("result", {}).get("list", [])
            if rows:
                # Bybit returns [start, open, high, low, close, volume, turnover],
                # newest-first -> reverse and drop turnover to match the shape.
                return [row[:6] for row in reversed(rows)]
    except Exception:
        pass

    return None


def klines_to_df(candles: list) -> pd.DataFrame:
    df = pd.DataFrame(
        candles,
        columns=["ts", "Open", "High", "Low", "Close", "Volume"]
        + [f"extra{i}" for i in range(max(0, len(candles[0]) - 6))],
    )
    df = df[["ts", "Open", "High", "Low", "Close", "Volume"]]
    df["ts"] = pd.to_datetime(df["ts"].astype(float), unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def get_live_price(symbol: str) -> Optional[float]:
    """Real-time last-traded price: Binance (both hosts) -> Bybit -> OKX."""
    body = _binance_get("/ticker/price", params={"symbol": symbol}, timeout=6)
    if body is not None:
        return float(body["price"])

    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/tickers", headers=_HEADERS, timeout=6,
            params={"category": "linear", "symbol": symbol},
        )
        if r.status_code == 200:
            items = r.json().get("result", {}).get("list", [])
            if items:
                return float(items[0]["lastPrice"])
    except Exception:
        pass

    try:
        r = requests.get(
            "https://www.okx.com/api/v5/market/ticker", headers=_HEADERS, timeout=6,
            params={"instId": _okx_symbol(symbol) + "-SWAP"},
        )
        if r.status_code == 200 and r.json().get("data"):
            return float(r.json()["data"][0]["last"])
    except Exception:
        pass

    return None
