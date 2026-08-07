"""
check_stock_signals — closes out open US stock signals.

Counterpart to generate_stock_signals, and the same role check_signals plays
for crypto. Without it every row stays result='pending' forever and the app's
win-rate / P&L cards are computed over an empty closed set.

Per open signal, walking DAILY bars from the signal date forward:
  1. Entry fill  — the stock must trade at/below `entry` (signals are posted
     at the prior close, so a gap-up open can mean the limit never fills).
  2. STOP / TARGET — stop is checked first on any bar that touches both:
     intrabar order is unknowable from OHLC, and assuming the good fill
     would inflate the win rate.
  3. TIME — past expires_at the position is closed at the last close, and
     booked win/loss on the sign of the move.

Trigger: once per weekday after the US close, right after generation.
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SEP = "-" * 60
TTL_DAYS = 90


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def evaluate(row: dict, bars: pd.DataFrame, now: datetime) -> dict | None:
    """Return the columns to write back, or None while genuinely still open."""
    created = _parse(row.get("timestamp"))
    expires = _parse(row.get("expires_at"))
    if created is None or bars.empty:
        return None

    entry = float(row["entry"])
    sl = float(row["stop_loss"])
    tp = float(row["take_profit"])

    window = bars[bars.index > created]
    if expires is not None:
        window = window[window.index <= expires]
    if window.empty:
        if expires is not None and now >= expires:
            return {"result": "expired", "exit_reason": "TIME",
                    "closed_at": expires.isoformat(), "exit_price": entry,
                    "pnl_pct": 0.0}
        return None

    filled = bool(row.get("entry_confirmed"))
    entry_at = _parse(row.get("entry_at"))
    last_close = float(window["Close"].iloc[-1])

    def out(result, reason, ts, price):
        return {
            "result": result, "exit_reason": reason,
            "closed_at": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            "entry_at": entry_at.isoformat() if entry_at else None,
            "entry_confirmed": True,
            "exit_price": round(price, 4),
            "pnl_pct": round((price - entry) / entry * 100, 2),
        }

    for ts, bar in window.iterrows():
        hi, lo = float(bar["High"]), float(bar["Low"])
        if not filled:
            if lo <= entry <= hi:
                filled, entry_at = True, ts
            else:
                continue
        if lo <= sl:
            return out("loss", "STOP", ts, sl)
        if hi >= tp:
            return out("win", "TARGET", ts, tp)

    if expires is not None and now >= expires:
        if not filled:
            return {"result": "expired", "exit_reason": "NO_FILL",
                    "closed_at": expires.isoformat(),
                    "entry_confirmed": False,
                    "exit_price": round(last_close, 4), "pnl_pct": 0.0}
        pnl = (last_close - entry) / entry * 100
        return out("win" if pnl > 0 else "loss", "TIME", expires, last_close)

    return {"_open": True, "entry_confirmed": filled,
            "entry_at": entry_at.isoformat() if entry_at else None,
            "latest_price": round(last_close, 4)}


def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    now = datetime.now(timezone.utc)
    print(f"\n[check_stock_signals] {now:%Y-%m-%d %H:%M UTC}")

    rows = (supabase.table("stock_signals").select("*")
            .eq("result", "pending").execute()).data or []
    print(f"[check_stock_signals] {len(rows)} open signal(s)")
    if not rows:
        return {"statusCode": 200, "body": json.dumps({"open": 0})}

    import yfinance as yf
    tickers = sorted({r["ticker"] for r in rows})
    raw = yf.download(tickers, period="6mo", interval="1d", progress=False,
                      auto_adjust=True, group_by="ticker", threads=True)

    def frame(t):
        try:
            sub = raw[t][["Open", "High", "Low", "Close"]].dropna() \
                if len(tickers) > 1 else raw[["Open", "High", "Low", "Close"]].dropna()
        except Exception:
            return pd.DataFrame()
        if sub.index.tz is None:
            sub.index = sub.index.tz_localize(timezone.utc)
        else:
            sub.index = sub.index.tz_convert(timezone.utc)
        return sub

    closed = still_open = errors = 0
    for row in rows:
        try:
            verdict = evaluate(row, frame(row["ticker"]), now)
            if verdict is None:
                still_open += 1
                continue
            if verdict.pop("_open", False):
                payload = {k: v for k, v in verdict.items() if v is not None}
                if payload:
                    supabase.table("stock_signals").update(payload) \
                        .eq("id", row["id"]).execute()
                still_open += 1
                continue
            payload = {k: v for k, v in verdict.items() if v is not None}
            supabase.table("stock_signals").update(payload) \
                .eq("id", row["id"]).execute()
            closed += 1
            print(f"  {SEP}")
            print(f"  {row['ticker']:<6} -> {verdict['result'].upper()} "
                  f"({verdict['exit_reason']}) exit=${verdict.get('exit_price')} "
                  f"pnl={verdict.get('pnl_pct')}%")
        except Exception as exc:
            errors += 1
            print(f"  [ERR] {row['ticker']}: {type(exc).__name__}: {exc}")

    try:
        cutoff = (now - pd.Timedelta(days=TTL_DAYS)).isoformat()
        supabase.table("stock_signals").delete().lt("timestamp", cutoff).execute()
    except Exception as exc:
        print(f"  [TTL ERR] {exc}")

    print(f"\n[check_stock_signals] closed={closed} open={still_open} errors={errors}")
    return {"statusCode": 200,
            "body": json.dumps({"closed": closed, "open": still_open,
                                "errors": errors})}


if __name__ == "__main__":
    print(json.dumps(json.loads(handler()["body"]), indent=2))
