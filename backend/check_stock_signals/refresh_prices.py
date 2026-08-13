"""
refresh_prices — updates `latest_price` on OPEN US stock signals using a
live/intraday quote, every 4h during the trading day.

WHY THIS IS A SEPARATE SCRIPT FROM handler.py
handler.py (check_stock_signals) runs once/day and works entirely off
COMPLETED DAILY BARS (yf.download(..., interval="1d")) — that's correct
for its job, deciding win/loss/expiry against the strategy's own daily-bar
backtest. Running handler.py itself more often would mostly re-fetch the
same unchanged daily bar until the next close, producing nothing new.

This script does ONE thing handler.py doesn't: fetch a cheap, genuinely
live price (yfinance's fast_info, not a full OHLC history) and update
`latest_price` on rows that are still open — so the app's displayed price
moves during the day instead of only refreshing once at close.

IT DOES NOT CLOSE TRADES. Stop-loss / take-profit / expiry decisions stay
exactly where they already are, in handler.py's once-daily run, using its
already-validated daily-bar logic. Wiring intraday exits here would
change the STRATEGY's actual behavior (which bar's high/low decides a
stop hit — a live quote isn't a bar at all), not just its display, and
that needs the same backtest scrutiny every other engine change in this
project has gotten — deliberately out of scope for this script.

Trigger: every 4h during roughly the trading day, via GitHub Actions —
see .github/workflows/refresh_stock_prices.yml. Harmless to run outside
market hours too (yfinance just returns the last known price, which is
already what's stored), so no market-hours gating is needed here.
"""

import os
from datetime import datetime, timezone

import yfinance as yf
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# Same mapping check_stock_signals/handler.py uses (FEED_SYMBOL there) —
# duplicated rather than imported to keep this script standalone and
# because handler.py isn't packaged as an importable module.
FEED_SYMBOL = {
    "XAUUSD": "GC=F",   # gold
    "XAGUSD": "SI=F",   # silver
}


def feed_symbol(ticker: str) -> str:
    return FEED_SYMBOL.get(ticker, ticker)


def fetch_live_price(ticker: str) -> float | None:
    try:
        price = yf.Ticker(feed_symbol(ticker)).fast_info.last_price
        return float(price) if price else None
    except Exception as exc:
        print(f"  [WARN] {ticker}: {exc}")
        return None


def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    now = datetime.now(timezone.utc)
    print(f"\n[refresh_prices] {now.strftime('%Y-%m-%d %H:%M UTC')}")

    open_rows = (
        supabase.table("stock_signals")
        .select("id, ticker")
        .eq("result", "pending")
        .execute()
    ).data or []

    if not open_rows:
        print("[refresh_prices] No open signals — nothing to refresh.")
        return {"statusCode": 200, "body": "no open signals"}

    updated, errors = 0, 0
    for row in open_rows:
        ticker = row["ticker"]
        price = fetch_live_price(ticker)
        if price is None:
            errors += 1
            continue
        try:
            supabase.table("stock_signals").update(
                {"latest_price": round(price, 4)}
            ).eq("id", row["id"]).execute()
            print(f"  [OK] {ticker:<8} latest_price=${price:,.2f}")
            updated += 1
        except Exception as exc:
            print(f"  [ERR] {ticker}: {exc}")
            errors += 1

    print(f"\n[refresh_prices] updated={updated} errors={errors} "
          f"of {len(open_rows)} open signal(s)")
    return {"statusCode": 200, "body": f"updated={updated} errors={errors}"}


if __name__ == "__main__":
    handler()
