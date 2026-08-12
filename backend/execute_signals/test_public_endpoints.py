"""
test_public_endpoints.py — no API key needed. Hits CoinDCX's PUBLIC
futures data endpoints to confirm real pair names, fee rates, quantity
rules, and price limits BEFORE writing or trusting any order-placement
code against a guess.

This is the cheapest possible verification step: these endpoints require
no authentication at all, so there is zero risk of anything being
executed — it can only read. Run this first, always, before touching
handler.py's order-building logic.

Confirms, for each of this project's traded pairs:
  - the real CoinDCX pair string (e.g. "B-ETH_USDT") vs the DB's
    Binance-style "ETHUSDT" — the mapping handler.py must implement
  - maker_fee / taker_fee — should read 0.025 / 0.075 per CoinDCX's
    docs (checked 2026-08); if this project's assumption in
    handler.py drifts from what's actually returned here, that's a
    real bug to fix before anything goes live
  - min_quantity / quantity_increment / min_notional — position sizing
    must round to these or CoinDCX will reject the order
  - max_leverage_long / max_leverage_short — handler.py's
    EXECUTE_LEVERAGE must not exceed this

Usage:
    python test_public_endpoints.py
    python test_public_endpoints.py --pairs ETHUSDT,DOGEUSDT,SOLUSDT
"""

import argparse
import json

import requests

BASE = "https://api.coindcx.com"
ACTIVE_INSTRUMENTS_PATH = "/exchange/v1/derivatives/futures/data/active_instruments"
INSTRUMENT_DETAIL_PATH = "/exchange/v1/derivatives/futures/data/instrument"

DEFAULT_PAIRS = [
    "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "TONUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "UNIUSDT",
]


def to_coindcx_pair(db_pair: str) -> str:
    """'ETHUSDT' -> 'B-ETH_USDT'. Splits on the trailing 'USDT' since every
    pair this project trades is USDT-quoted; this would need a smarter
    split (or a lookup table) if a non-USDT pair were ever added."""
    if not db_pair.endswith("USDT"):
        raise ValueError(f"Unexpected pair format (not USDT-quoted): {db_pair}")
    base = db_pair[:-4]
    return f"B-{base}_USDT"


def fetch_active_instruments() -> list:
    r = requests.get(
        BASE + ACTIVE_INSTRUMENTS_PATH,
        params={"margin_currency_short_name[]": "USDT"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def fetch_instrument_detail(coindcx_pair: str) -> dict:
    r = requests.get(
        BASE + INSTRUMENT_DETAIL_PATH,
        params={"pair": coindcx_pair, "margin_currency_short_name": "USDT"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=str, default=None,
                     help="Comma-separated DB-style pairs, e.g. ETHUSDT,DOGEUSDT")
    args = ap.parse_args()
    pairs = args.pairs.split(",") if args.pairs else DEFAULT_PAIRS

    print("Fetching active USDT futures instruments (public, no key needed)...")
    active = fetch_active_instruments()
    print(f"  {len(active)} active instruments found.\n")

    print(f"{'DB pair':<12} {'CoinDCX pair':<16} {'active?':<8} {'maker/taker':<14} "
          f"{'min_qty':<10} {'qty_step':<10} {'min_notional':<12} {'max_lev':<8}")
    print("-" * 100)

    for db_pair in pairs:
        try:
            coindcx_pair = to_coindcx_pair(db_pair)
        except ValueError as e:
            print(f"{db_pair:<12} [SKIP] {e}")
            continue

        is_active = coindcx_pair in active
        marker = "YES" if is_active else "NO — not listed!"

        try:
            detail = fetch_instrument_detail(coindcx_pair)
            inst = detail.get("instrument", {})
            maker = inst.get("maker_fee")
            taker = inst.get("taker_fee")
            min_qty = inst.get("min_quantity")
            step = inst.get("quantity_increment")
            min_notional = inst.get("min_notional")
            max_lev = inst.get("max_leverage_long")
            print(f"{db_pair:<12} {coindcx_pair:<16} {marker:<8} "
                  f"{f'{maker}/{taker}':<14} {str(min_qty):<10} {str(step):<10} "
                  f"{str(min_notional):<12} {str(max_lev):<8}")
        except requests.HTTPError as e:
            print(f"{db_pair:<12} {coindcx_pair:<16} {marker:<8} [ERR fetching detail: {e}]")

    print("\nRaw instrument detail for the FIRST pair, for eyeballing the full shape:")
    if pairs:
        first = to_coindcx_pair(pairs[0])
        detail = fetch_instrument_detail(first)
        print(json.dumps(detail, indent=2))


if __name__ == "__main__":
    main()
