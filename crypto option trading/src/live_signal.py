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

# A signal is held up to MAX_HOLD_HOURS (72h, see run_signal.py) before
# check_signals.py force-closes it. The contract we name must outlive that
# window, plus a buffer: an option's theta decay accelerates sharply in its
# final day, so expiring "just barely" after the trade closes still bleeds
# premium for the whole back half of the hold.
#
# This was a real bug: the original code took Deribit's NEAREST expiry
# (`min(expiration_timestamp)`), which is routinely <24h out. The live
# 2026-08-26 BTCUSDT PUT was written against BTC-27AUG26 — an option
# expiring ~25h after a signal designed to be held for up to 72h. It would
# have expired worthless mid-trade regardless of whether the call was right.
MIN_EXPIRY_BUFFER_HOURS = 84  # 72h max hold + 12h buffer
MAX_HOLD_HOURS_DISPLAY = 72   # for log text only; run_signal.MAX_HOLD_HOURS is source of truth


def _deribit_currency(symbol: str) -> str:
    return "BTC" if symbol.startswith("BTC") else "ETH"


def get_deribit_atm_context(symbol: str, spot: float) -> Optional[dict]:
    """
    Best-effort fetch of the ATM call/put contract for the first Deribit
    expiry that outlives the trade's max hold (see MIN_EXPIRY_BUFFER_HOURS).
    Deribit is the standard venue for BTC/ETH options (deepest liquidity),
    and this endpoint needs no API key. Returns None on any failure --
    caller must degrade gracefully, same pattern as the NIFTY module's NSE
    option-chain fetch.

    STRIKE = ATM (nearest listed strike to spot). This is deliberate on two
    independent grounds: (1) the backtest prices P&L with option_delta=0.5,
    which *is* an ATM option -- buying ITM/OTM instead would silently break
    the correspondence between the published backtest expectancy and what
    you actually trade; (2) empirically ATM is where the liquidity is. A
    live 2026-09-04 BTC chain check showed open interest 25.0 at the ATM
    strike vs 0.0-1.4 at every neighbouring strike, so an OTM "cheaper"
    fill is often not fillable at a sane spread at all.
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

        # First expiry that survives the whole hold (not merely the nearest).
        now_ms = time.time() * 1000
        cutoff_ms = now_ms + MIN_EXPIRY_BUFFER_HOURS * 3600 * 1000
        eligible = sorted({i["expiration_timestamp"] for i in instruments
                           if i["expiration_timestamp"] >= cutoff_ms})
        if not eligible:
            # Nothing dated far enough out (very unusual). Fall back to the
            # longest-dated listed contract rather than silently naming one
            # that expires mid-trade.
            eligible = [max(i["expiration_timestamp"] for i in instruments)]
        nearest_expiry = eligible[0]
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

        # Deribit quotes BTC/ETH options in UNITS OF THE UNDERLYING, not USD:
        # a BTC put with mark_price 0.0117 costs 0.0117 BTC (~$950 at 81k),
        # not $0.01. The previous keys were named `*_usd` while carrying the
        # raw coin-denominated number, so anything downstream that showed
        # them as dollars was off by ~5 orders of magnitude. Convert here and
        # keep BOTH denominations, explicitly named.
        def _prices(summary: Optional[dict]) -> tuple:
            if not summary or summary.get("mark_price") is None:
                return None, None
            coin = float(summary["mark_price"])
            return coin, round(coin * spot, 2)

        call_coin, call_usd = _prices(call_summary)
        put_coin, put_usd = _prices(put_summary)

        return {
            "spot": spot,
            "atm_strike": atm_strike,
            "expiry_ts_ms": nearest_expiry,
            "expiry_hours_out": round((nearest_expiry - now_ms) / 3600000, 1),
            "call_instrument": call_name,
            "put_instrument": put_name,
            # Premium per 1 contract (= 1 unit of underlying) in both units.
            "call_premium_coin": call_coin,
            "put_premium_coin": put_coin,
            "call_premium_usd": call_usd,
            "put_premium_usd": put_usd,
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
        coin_unit = args.symbol[:-4]
        print(f"  ATM strike:      {ctx['atm_strike']:,.0f}")
        print(f"  Instrument:      {ctx[leg + 'instrument']}")
        print(f"  Expires in:      {ctx['expiry_hours_out']}h "
              f"(must outlive the {MAX_HOLD_HOURS_DISPLAY}h max hold)")
        coin = ctx.get(leg + "premium_coin")
        usd = ctx.get(leg + "premium_usd")
        iv = ctx.get(leg + "mark_iv")
        if coin is not None:
            print(f"  Premium/contract: {coin:.6f} {coin_unit}  (~${usd:,.2f})")
            print(f"  Cost for {size:.4f} {coin_unit}: ~${usd * size:,.2f}")
        else:
            print("  Premium:         unavailable")
        print(f"  Mark IV:         {iv}%" if iv is not None else "  Mark IV:         unavailable")


if __name__ == "__main__":
    main()
