"""
monthly_summary — rolls closed trades up into one small row per month/market.

WHY THIS EXISTS
Every signals table has a 90-day TTL (check_signals / check_nifty_signals /
check_stock_signals all delete rows older than that). Without a rollup the
long-run track record is simply lost — after a year you can only ever see
the last three months.

DESIGN
  • One row per (month, market). 3 markets = 36 rows/year, ~100 bytes each,
    so ~3.6 KB/year. It never needs a TTL of its own.
  • Upsert on the (month, market) primary key, so re-running is safe and the
    current month keeps refreshing until it is complete.
  • Recomputes the last RECOMPUTE_MONTHS months each run, not just the
    current one: a trade opened in March can close in April, and late
    closes must land in the month the trade CLOSED.
  • Only closed trades count. Pending ones are excluded entirely so a
    month's numbers cannot drift as open trades resolve.

IMPORTANT — run this BEFORE the TTL cleanup deletes anything. It is
scheduled daily, well inside the 90-day window, so no month can age out
before being summarised.

Trigger: daily via GitHub Actions.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# Re-summarise this many months back on every run. Comfortably covers late
# closes while staying well inside the 90-day TTL.
RECOMPUTE_MONTHS = 4

# Each market: table, the column holding realised P&L, and its unit.
#   crypto         — no stored P&L column, so it is derived from entry vs close_price
#   crypto_options — pnl_usd is already USD
#   stocks         — pnl_pct is already a percentage
MARKETS = {
    "crypto": {"table": "trade_signals", "unit": "pct"},
    "crypto_options": {"table": "crypto_option_signals", "unit": "usd"},
    "stocks": {"table": "stock_signals", "unit": "pct"},
}


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _month_key(d: datetime) -> str:
    return d.replace(day=1).strftime("%Y-%m-%d")


def trade_pnl(market: str, row: dict) -> float | None:
    """Realised P&L for one closed trade, in that market's natural unit."""
    if market == "crypto_options":
        v = row.get("pnl_usd")
        return float(v) if v is not None else None

    if market == "stocks":
        v = row.get("pnl_pct")
        return float(v) if v is not None else None

    # crypto: derive the % move from entry -> close_price, signed by direction.
    entry = row.get("entry") or row.get("entry_price")
    close = row.get("close_price")
    if entry in (None, 0) or close is None:
        return None
    entry, close = float(entry), float(close)
    if entry == 0:
        return None
    move = (close - entry) / entry * 100
    return move if row.get("direction") != "short" else -move


def summarise(market: str, rows: list, since: datetime) -> list[dict]:
    """Group closed trades into per-month summary rows."""
    buckets: dict[str, list] = defaultdict(list)

    for r in rows:
        result = r.get("result")
        if result == "pending":
            continue          # only closed trades count
        # Bucket by when the trade CLOSED, falling back to its creation time
        # for older rows written before closed_at existed.
        when = _parse(r.get("closed_at")) or _parse(r.get("timestamp"))
        if when is None or when < since:
            continue
        buckets[_month_key(when)].append(r)

    out = []
    for month, trades in buckets.items():
        wins = sum(1 for t in trades if t.get("result") == "win")
        losses = sum(1 for t in trades if t.get("result") == "loss")
        expired = sum(1 for t in trades if t.get("result") == "expired")
        decided = wins + losses

        pnls = [p for p in (trade_pnl(market, t) for t in trades)
                if p is not None]

        out.append({
            "month": month,
            "market": market,
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "win_rate": round(100 * wins / decided, 1) if decided else None,
            "pnl": round(sum(pnls), 2) if pnls else 0.0,
            "pnl_unit": MARKETS[market]["unit"],
            "best": round(max(pnls), 2) if pnls else None,
            "worst": round(min(pnls), 2) if pnls else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=31 * RECOMPUTE_MONTHS)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)

    print(f"\n[monthly_summary] {now:%Y-%m-%d %H:%M UTC}")
    print(f"[monthly_summary] recomputing months from {since:%Y-%m}")

    written = 0
    for market, cfg in MARKETS.items():
        table = cfg["table"]
        try:
            rows = (supabase.table(table).select("*")
                    .gte("timestamp", since.isoformat()).execute()).data or []
        except Exception as exc:
            # A market whose table does not exist yet must not break the rest.
            print(f"  [SKIP] {market:<7} ({table}): {exc}")
            continue

        summaries = summarise(market, rows, since)
        if not summaries:
            print(f"  {market:<7} no closed trades in range")
            continue

        for s in sorted(summaries, key=lambda x: x["month"]):
            try:
                supabase.table("monthly_summary").upsert(
                    s, on_conflict="month,market").execute()
                written += 1
                unit = "%" if s["pnl_unit"] == "pct" else "Rs."
                pnl = f"{unit}{s['pnl']}" if unit == "Rs." else f"{s['pnl']}{unit}"
                print(f"  {market:<7} {s['month'][:7]}  "
                      f"trades={s['trades']:<3} W/L={s['wins']}/{s['losses']} "
                      f"win={s['win_rate']}%  pnl={pnl}")
            except Exception as exc:
                print(f"  [DB ERR] {market} {s['month']}: {exc}")

    print(f"\n[monthly_summary] wrote {written} row(s)")
    return {"statusCode": 200, "body": json.dumps({"rows": written})}


if __name__ == "__main__":
    print(json.dumps(json.loads(handler()["body"]), indent=2))
