"""
Data access layer for the "short new listings" engine.

GEO-BLOCKING, same issue documented in backend/generate_signals/handler.py
and "crypto option trading/src/data_feed.py": fapi.binance.com returns
HTTP 451 from GitHub Actions' US-hosted runners. Confirmed live 2026-09-xx
-- this workflow was crashing on every scheduled run until this fix.

Price data uses the same proven fallback pattern as every other engine
here -- which provider answers doesn't change what the strategy IS, since
they all track the same underlying market price:
  - get_live_price:   Binance -> Bybit -> OKX (3-way; simple ticker lookup)
  - get_daily_klines:  Binance -> Bybit only (see that function's docstring
                       for why OKX isn't a third fallback here)

LISTING-DATE DISCOVERY (get_usdt_perp_listings) is a harder case and is
NOT silently swapped to another exchange: this strategy's entry trigger is
specifically "27-33 days since Binance's own onboardDate", which is the
number the whole backtest (see README.md) was validated against. No other
exchange exposes that same value -- OKX's `listTime` is when OKX listed
the contract, not Binance, and can differ by days. Binance Futures has no
alternate non-geo-blocked host either (data-api.binance.vision only
mirrors SPOT paths, confirmed 404 on /fapi/v1/*). So this call is
Binance-only, degrading to an empty candidate list (safe no-op, matching
every other engine's convention) rather than crashing the workflow when
blocked -- see run_signal.py for the operational consequence and options.
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
BINANCE_BASE = "https://fapi.binance.com/fapi/v1"
BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"


def get_usdt_perp_listings(min_age_days: float = 0, max_age_days: float = 420) -> list[dict]:
    """
    All USDT-margined perpetuals currently listed on Binance Futures whose
    age (now - onboardDate) falls in [min_age_days, max_age_days].

    Returns [{"symbol", "onboard_ms", "age_days"}, ...]. Excludes anything
    without a usable onboardDate. Returns [] (does not raise) if Binance's
    exchangeInfo is unreachable -- e.g. geo-blocked from GitHub Actions --
    so a scheduled run finds "no candidates" instead of crashing. This does
    NOT fall back to another exchange; see this module's docstring for why.
    """
    try:
        r = requests.get(f"{BINANCE_BASE}/exchangeInfo", headers=_HEADERS, timeout=15)
        r.raise_for_status()
        syms = r.json()["symbols"]
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] Binance exchangeInfo unreachable ({e}) -- "
              f"no listing candidates this run.")
        return []

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
    Daily klines from start_ms FORWARD, Binance -> Bybit fallback. Returns
    rows in the shared [ts, open, high, low, close, volume] layout
    (Binance's native shape); Bybit's response is normalized to match.
    None if both fail.

    OKX deliberately is NOT a third fallback here (unlike get_live_price
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
    # 1. Binance Futures (primary; blocked from GitHub Actions -- fall through)
    try:
        r = requests.get(
            f"{BINANCE_BASE}/klines", headers=_HEADERS, timeout=15,
            params={"symbol": symbol, "interval": "1d",
                    "startTime": int(start_ms), "limit": limit},
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass

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
    """Real-time last-traded price, same Binance -> Bybit -> OKX fallback chain."""
    try:
        r = requests.get(
            f"{BINANCE_BASE}/ticker/price", headers=_HEADERS, timeout=6,
            params={"symbol": symbol},
        )
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass

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
