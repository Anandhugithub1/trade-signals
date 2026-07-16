"""
Data access layer.

Two free sources, both without an API key:

1. yfinance  -> NIFTY 50 index OHLC history (spot). Used for backtesting the
   signal logic and for the "current spot" during live signal generation.
   Symbol: ^NSEI

2. NSE public option-chain JSON -> live ATM strikes, LTP, OI, PCR.
   URL: https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY
   This is UNOFFICIAL. It needs browser-like headers and a warm-up cookie,
   is rate-limited, and can break at any time. All calls are wrapped so a
   failure degrades gracefully instead of crashing the app.
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

NSE_OPTION_CHAIN_URL = (
    "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
)
NSE_HOME = "https://www.nseindia.com/option-chain"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
}


# ----------------------------- Index history ------------------------------ #

def get_index_history(period: str = "60d", interval: str = "15m") -> pd.DataFrame:
    """
    NIFTY 50 spot OHLC history via yfinance.

    interval: yfinance supports '1m'(7d max), '5m','15m'(60d max), '1h', '1d'.
    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    """
    import yfinance as yf

    df = yf.download(
        "^NSEI",
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
    )
    if df.empty:
        raise RuntimeError(
            "yfinance returned no data for ^NSEI. "
            "Check your internet connection or try a different interval."
        )

    # yfinance may return a MultiIndex column set for a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


# --------------------------- NSE option chain ----------------------------- #

def _nse_session() -> Optional[requests.Session]:
    """Warm up a session so NSE hands us the cookies its API requires."""
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        s.get(NSE_HOME, timeout=8)
        time.sleep(0.6)
        return s
    except requests.RequestException:
        return None


def get_option_chain() -> Optional[dict]:
    """
    Fetch the live NIFTY option chain.

    Returns the parsed JSON dict, or None if NSE blocked/failed the request
    (caller must handle None -- this is expected occasionally).
    """
    s = _nse_session()
    if s is None:
        return None
    for _ in range(3):
        try:
            r = s.get(NSE_OPTION_CHAIN_URL, timeout=8)
            if r.status_code == 200 and r.text.strip():
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.2)
    return None


def parse_atm_context(chain: dict) -> Optional[dict]:
    """
    From a raw option-chain dict, extract the spot, ATM strike, ATM CE/PE
    premiums and the overall Put-Call Ratio (a directional sentiment gauge).
    """
    if not chain or "records" not in chain:
        return None

    records = chain["records"]
    spot = records.get("underlyingValue")
    data = records.get("data", [])
    if not spot or not data:
        return None

    # ATM strike = strike nearest to spot
    strikes = sorted({row["strikePrice"] for row in data})
    atm = min(strikes, key=lambda k: abs(k - spot))

    ce_ltp = pe_ltp = None
    total_ce_oi = total_pe_oi = 0
    for row in data:
        ce = row.get("CE")
        pe = row.get("PE")
        if ce:
            total_ce_oi += ce.get("openInterest", 0)
            if row["strikePrice"] == atm:
                ce_ltp = ce.get("lastPrice")
        if pe:
            total_pe_oi += pe.get("openInterest", 0)
            if row["strikePrice"] == atm:
                pe_ltp = pe.get("lastPrice")

    pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi else None

    return {
        "spot": spot,
        "atm_strike": atm,
        "atm_ce_ltp": ce_ltp,
        "atm_pe_ltp": pe_ltp,
        "pcr": pcr,
        "strikes": strikes,
        "raw_data": data,
    }


# NIFTY strikes are 50 points apart.
STRIKE_STEP = 50


def select_strike(ctx: dict, side: str, style: str = "ATM") -> Optional[dict]:
    """
    Pick WHICH call/put to buy for a signal.

    side  : "CE" (bullish) or "PE" (bearish)
    style : "ITM" | "ATM" | "OTM"  -- how far from spot to buy.

    Selection rules (1 step = 50 pts):
      ATM  -> strike nearest spot          (delta ~0.50; our backtest baseline)
      ITM  -> one step in-the-money        (delta ~0.60-0.65; moves like index,
                                            least theta, costs more premium)
      OTM  -> one step out-of-the-money    (delta ~0.30-0.35; cheap, but theta
                                            bleeds fast -> WORSE than backtest)

    For a CE, ITM = lower strike, OTM = higher strike. For a PE it's mirrored.
    Returns {strike, premium, style, note} or None if the chain lacks it.
    """
    if not ctx or "raw_data" not in ctx:
        return None
    atm = ctx["atm_strike"]

    # Direction of "in the money" per side.
    if side == "CE":
        itm_strike = atm - STRIKE_STEP   # lower strike is ITM for a call
        otm_strike = atm + STRIKE_STEP
    else:  # PE
        itm_strike = atm + STRIKE_STEP   # higher strike is ITM for a put
        otm_strike = atm - STRIKE_STEP

    target_strike = {"ITM": itm_strike, "ATM": atm, "OTM": otm_strike}.get(
        style.upper(), atm
    )

    leg = "CE" if side == "CE" else "PE"
    premium = None
    for row in ctx["raw_data"]:
        if row["strikePrice"] == target_strike and row.get(leg):
            premium = row[leg].get("lastPrice")
            break

    delta_hint = {"ITM": "~0.65", "ATM": "~0.50", "OTM": "~0.30"}[style.upper()]
    note = {
        "ITM": "moves closest to the index, least theta decay, higher premium",
        "ATM": "balanced; matches the backtest's delta=0.5 assumption",
        "OTM": "cheapest but theta bleeds fast -- expect WORSE than backtest",
    }[style.upper()]

    return {
        "strike": target_strike,
        "side": side,
        "premium": premium,
        "style": style.upper(),
        "delta_hint": delta_hint,
        "note": note,
    }
