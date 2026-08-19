"""
Latest actionable signal for BTC/ETH options, with a real ATM premium pulled
from Deribit's public (no-auth) options API where available.

Usage:
    python live_signal.py --symbol BTCUSDT --max-loss 200
"""
from __future__ import annotations

import argparse
import time
from typing import Optional

import requests

from data_feed import get_perp_history, get_live_price
from strategy import StrategyParams, add_indicators, evaluate_row

DERIBIT_BASE = "https://www.deribit.com/api/v2/public"


def _deribit_currency(symbol: str) -> str:
    return "BTC" if symbol.startswith("BTC") else "ETH"


def get_deribit_atm_context(symbol: str, spot: float) -> Optional[dict]:
    """
    Best-effort fetch of the nearest-expiry ATM call/put mark price from
    Deribit's public book-summary endpoint. Deribit is the standard venue
    for BTC/ETH options (deepest liquidity), and this endpoint needs no
    API key. Returns None on any failure -- caller must degrade gracefully,
    same pattern as the NIFTY module's NSE option-chain fetch.
    """
    currency = _deribit_currency(symbol)
    try:
        r = requests.get(
            f"{DERIBIT_BASE}/get_instruments",
            params={"currency": currency, "kind": "option", "expired": "false"},
            timeout=8,
        )
        r.raise_for_status()
        instruments = r.json().get("result", [])
        if not instruments:
            return None

        # Nearest expiry only.
        nearest_expiry = min(i["expiration_timestamp"] for i in instruments)
        near = [i for i in instruments if i["expiration_timestamp"] == nearest_expiry]

        # ATM strike = nearest to spot among this expiry's strikes.
        strikes = sorted({i["strike"] for i in near})
        atm_strike = min(strikes, key=lambda k: abs(k - spot))

        call_name = next((i["instrument_name"] for i in near
                           if i["strike"] == atm_strike and i["option_type"] == "call"), None)
        put_name = next((i["instrument_name"] for i in near
                          if i["strike"] == atm_strike and i["option_type"] == "put"), None)

        def _summary(instrument_name: str) -> Optional[dict]:
            if not instrument_name:
                return None
            rs = requests.get(
                f"{DERIBIT_BASE}/get_book_summary_by_instrument",
                params={"instrument_name": instrument_name}, timeout=8,
            )
            if rs.status_code != 200:
                return None
            res = rs.json().get("result", [])
            return res[0] if res else None

        call_summary = _summary(call_name)
        put_summary = _summary(put_name)

        return {
            "spot": spot,
            "atm_strike": atm_strike,
            "expiry_ts_ms": nearest_expiry,
            "call_instrument": call_name,
            "put_instrument": put_name,
            "call_mark_price_usd": (call_summary or {}).get("mark_price", None),
            "put_mark_price_usd": (put_summary or {}).get("mark_price", None),
            "call_mark_iv": (call_summary or {}).get("mark_iv", None),
            "put_mark_iv": (put_summary or {}).get("mark_iv", None),
        }
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Latest crypto option signal")
    ap.add_argument("--symbol", default="BTCUSDT", help="perp symbol, e.g. BTCUSDT")
    ap.add_argument("--interval", default="1h", help="bar interval")
    ap.add_argument("--max-loss", type=float, default=200.0, help="USD stop-loss budget")
    args = ap.parse_args()

    p = StrategyParams()
    print(f"Fetching {args.symbol} history ...")
    df = get_perp_history(args.symbol, interval=args.interval, months=2)
    df = add_indicators(df, p)

    i = len(df) - 1
    sig = evaluate_row(df, i, p)

    live_price = get_live_price(args.symbol) or float(df.iloc[-1]["Close"])

    if sig is None:
        print(f"\nNo signal on the latest {args.interval} bar for {args.symbol}.")
        print(f"Live price: {live_price:,.2f}")
        return

    print(f"\n{'='*60}\nSIGNAL: {sig.side} {args.symbol}\n{'='*60}")
    print(f"  Time (bar):      {sig.timestamp}")
    print(f"  Live price:      {live_price:,.2f}")
    print(f"  Entry (signal):  {sig.entry:,.2f}")
    print(f"  Stop (index):    {sig.stop_index:,.2f}")
    print(f"  Target (index):  {sig.target_index:,.2f}")
    print(f"  ATR:             {sig.atr:,.2f}")
    print(f"  RSI:             {sig.rsi:.1f}")
    print(f"  Note:            {sig.note}")

    stop_move = abs(sig.entry - sig.stop_index)
    risk_per_unit = stop_move * p.option_delta
    size = args.max_loss / risk_per_unit if risk_per_unit > 0 else 0.0
    print(f"\n  Sizing @ ${args.max_loss:.0f} max loss, delta={p.option_delta}:")
    print(f"    underlying size: {size:.4f} {args.symbol[:-4]}")

    print(f"\nFetching Deribit ATM option context ...")
    ctx = get_deribit_atm_context(args.symbol, live_price)
    if ctx is None:
        print("  Deribit lookup failed/unavailable -- no live premium.")
    else:
        leg = "call_" if sig.side == "CALL" else "put_"
        print(f"  ATM strike:      {ctx['atm_strike']:,.0f}")
        print(f"  Instrument:      {ctx[leg + 'instrument']}")
        mark = ctx.get(leg + "mark_price_usd")
        iv = ctx.get(leg + "mark_iv")
        print(f"  Mark price:      {mark} BTC/ETH-denominated" if mark is not None else "  Mark price:      unavailable")
        print(f"  Mark IV:         {iv}%" if iv is not None else "  Mark IV:         unavailable")


if __name__ == "__main__":
    main()
