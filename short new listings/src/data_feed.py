"""
Data access layer for the "short new listings" engine.

Uses Binance Futures directly (no fallback chain needed here, unlike the
main crypto engine): this strategy's entry trigger IS "how long ago did
Binance list this perp", which only Binance's own exchangeInfo can answer.
If Binance is unreachable the run simply finds no eligible listings that
cycle -- a safe no-op, same philosophy as every other engine's degrade path.
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
BASE = "https://fapi.binance.com/fapi/v1"


def get_usdt_perp_listings(min_age_days: float = 0, max_age_days: float = 420) -> list[dict]:
    """
    All USDT-margined perpetuals currently listed on Binance Futures whose
    age (now - onboardDate) falls in [min_age_days, max_age_days].

    Returns [{"symbol", "onboard_ms", "age_days"}, ...]. Excludes anything
    without a usable onboardDate (a handful of very old contracts predate
    the field being populated).
    """
    r = requests.get(f"{BASE}/exchangeInfo", headers=_HEADERS, timeout=15)
    r.raise_for_status()
    syms = r.json()["symbols"]
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


def get_daily_klines(symbol: str, start_ms: float, limit: int = 200) -> Optional[list]:
    """Raw Binance Futures daily klines from start_ms. None on any failure."""
    try:
        r = requests.get(
            f"{BASE}/klines", headers=_HEADERS, timeout=15,
            params={"symbol": symbol, "interval": "1d",
                    "startTime": int(start_ms), "limit": limit},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, list) and data else None
    except Exception:
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
    try:
        r = requests.get(
            f"{BASE}/ticker/price", headers=_HEADERS, timeout=6,
            params={"symbol": symbol},
        )
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass
    return None
