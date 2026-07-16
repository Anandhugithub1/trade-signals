"""
Upstox historical-candle loader for NIFTY 50 index.

Upstox v2 HISTORICAL candles (past days, not today's live intraday) are served
WITHOUT authentication from:

  GET https://api.upstox.com/v2/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}

For NIFTY 50 index the instrument key is:  NSE_INDEX|Nifty 50

This gives us 15-minute bars going back well over a year -- exactly what the
free yfinance feed could not provide (it caps 15m at ~60 days).

Usage:
    from upstox_feed import get_upstox_history
    df = get_upstox_history(interval="15minute", months=9)

Returns a DataFrame with columns Open, High, Low, Close, Volume indexed by an
IST-localized DatetimeIndex -- same shape as data_feed.get_index_history, so it
is a drop-in replacement for the backtest.

If you need TODAY's still-forming candles too, that endpoint DOES require an
access token; set UPSTOX_ACCESS_TOKEN and we append the intraday feed.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests

NIFTY_KEY = "NSE_INDEX|Nifty 50"
# v3 historical-candle endpoint (v2 path returns 404).
BASE = "https://api.upstox.com/v3"

# Upstox uses unit + interval, e.g. minutes/15, days/1. Map friendly names.
_INTERVAL_MAP = {
    "1minute": ("minutes", "1"),
    "5minute": ("minutes", "5"),
    "15minute": ("minutes", "15"),
    "30minute": ("minutes", "30"),
    "60minute": ("minutes", "60"),
    "day": ("days", "1"),
}


def _to_df(candles: list) -> pd.DataFrame:
    """Upstox candle = [timestamp, open, high, low, close, volume, oi]."""
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(
        candles,
        columns=["ts", "Open", "High", "Low", "Close", "Volume", "OI"],
    )
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts").sort_index()
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df


def get_upstox_history(
    interval: str = "15minute",
    months: int = 9,
    instrument_key: str = NIFTY_KEY,
) -> pd.DataFrame:
    """
    Fetch `months` of historical candles at `interval` from Upstox.

    Upstox limits how wide a single historical request can be, so we page the
    request in ~90-day windows and concatenate.
    """
    if interval not in _INTERVAL_MAP:
        raise ValueError(
            f"interval must be one of {list(_INTERVAL_MAP)}, got {interval!r}"
        )
    unit, num = _INTERVAL_MAP[interval]

    end = date.today()
    start = end - timedelta(days=int(months * 31))

    # Upstox caps the span of a single historical request by interval:
    # sub-hour (minute) data is limited to ~1 month per call; days/hours allow
    # much wider. Page accordingly so we never trip a 400.
    chunk_days = 27 if unit == "minutes" else 300

    frames = []
    window_end = end
    while window_end > start:
        window_start = max(start, window_end - timedelta(days=chunk_days))
        url = (
            f"{BASE}/historical-candle/{instrument_key}/"
            f"{unit}/{num}/{window_end.isoformat()}/{window_start.isoformat()}"
        )
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
            r.raise_for_status()
            payload = r.json()
            candles = payload.get("data", {}).get("candles", [])
            frame = _to_df(candles)
            if not frame.empty:
                frames.append(frame)
        except (requests.RequestException, ValueError) as e:
            print(f"  [warn] Upstox window {window_start}->{window_end} failed: {e}")
        window_end = window_start - timedelta(days=1)

    if not frames:
        raise RuntimeError(
            "Upstox returned no candles. Check the instrument key / interval, "
            "or the API may be temporarily unreachable."
        )

    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def _append_live_intraday(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Optionally append today's forming candles (needs an access token)."""
    token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        return df
    unit, num = _INTERVAL_MAP[interval]
    url = f"{BASE}/historical-candle/intraday/{NIFTY_KEY}/{unit}/{num}"
    # (intraday uses the same v3 base and unit/interval path shape)
    try:
        r = requests.get(
            url,
            headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        today = _to_df(r.json().get("data", {}).get("candles", []))
        if not today.empty:
            df = pd.concat([df, today]).sort_index()
            df = df[~df.index.duplicated(keep="last")]
    except (requests.RequestException, ValueError) as e:
        print(f"  [warn] intraday append failed: {e}")
    return df


def get_history(interval: str = "15minute", months: int = 9,
                with_live: bool = False) -> pd.DataFrame:
    """Convenience: historical + optionally today's live candles."""
    df = get_upstox_history(interval=interval, months=months)
    if with_live:
        df = _append_live_intraday(df, interval)
    return df


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Test the Upstox NIFTY loader")
    ap.add_argument("--interval", default="15minute")
    ap.add_argument("--months", type=int, default=9)
    args = ap.parse_args()

    df = get_upstox_history(interval=args.interval, months=args.months)
    print(f"Fetched {len(df)} bars: {df.index[0]} -> {df.index[-1]}")
    print(df.tail())
