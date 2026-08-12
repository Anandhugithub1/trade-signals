"""
execute_signals — places real CoinDCX futures orders for donchian signals.

STATUS: DRY-RUN ONLY. Do not remove the DRY_RUN default without reading
the whole "BEFORE GOING LIVE" section below first.

WHY THIS EXISTS
CoinDCX has no public sandbox/testnet for their futures API (confirmed —
their docs describe live trading endpoints only). This module is the
self-built substitute: it reads REAL Donchian signals already sitting in
trade_signals, builds the REAL order payload CoinDCX's API would receive,
and by default only LOGS that payload instead of sending it.

SCOPE: donchian signals only, matching the user's explicit ask — not
mean_reversion.

CoinDCX Futures API — shapes CONFIRMED against the real docs (not the
earlier truncated fetch this module first guessed from; see git history
for that first, wrong version — wrong endpoint paths, wrong flat body
shape, wrong pair format guess). Verified via:
  (a) the full docs pasted by the user, and
  (b) test_public_endpoints.py actually hitting CoinDCX's public,
      unauthenticated instrument-data endpoints for this project's real
      pairs — RUN THAT SCRIPT before trusting anything below has not
      drifted from what CoinDCX actually returns today.

  Create Order
    POST https://api.coindcx.com/exchange/v1/derivatives/futures/orders/create
    body: {"timestamp": ..., "order": {side, pair, order_type, price,
           stop_price, total_quantity, leverage, notification,
           time_in_force, margin_currency_short_name, take_profit_price,
           stop_loss_price}}
    NOTE the body is NESTED under "order" — an earlier version of this
    module sent a flat body, which the real API would have rejected.
    take_profit_price / stop_loss_price can be set in THIS SAME call —
    no separate TP/SL request needed for a plain market-entry trade,
    contradicting the earlier (truncated-docs) guess that a second
    create_take_profit_stop_loss call was required.
  Auth: HMAC-SHA256 of the JSON body, hex digest, in X-AUTH-SIGNATURE;
        API key in X-AUTH-APIKEY; timestamp lives IN the body (seconds,
        per the real docs' EPOCH-seconds examples — NOT milliseconds,
        which the earlier wrong version used).
  Pair format: "B-ETH_USDT" (exchange-prefixed, underscore) — confirmed
        by test_public_endpoints.py against real active instruments.
  Quantity: total_quantity is in the UNDERLYING asset (e.g. ETH), NOT
        USDT notional or contracts — confirmed by the real docs' Create
        Order response ("total_quantity":2.86 alongside "price":89.97
        for what is clearly a small position, not 2.86 USDT worth).

STILL WORTH DOUBLE-CHECKING BEFORE REAL MONEY (lower-severity than the
items above, which are now resolved)
  - This module assumes cross margin is NOT explicitly requested
    (position_margin_type omitted -> account default applies). Confirm
    your account's default margin mode matches what you want before
    going live; see the Change Position Margin Type endpoint in the docs
    if it needs to be explicit.
  - Real fee rates DRIFT from the docs' example figures — this project's
    fee assumption in test_scripts/backtest_donchian_profit.py used
    0.075% taker from a generic doc example; test_public_endpoints.py
    showed this project's actual live pairs charge 0.059% taker /
    0.0236% maker right now. Numbers here use the REAL per-pair rate
    (fetched live), not a hardcoded guess, but note the backtest itself
    has NOT been re-run with the corrected rate yet.

BEFORE GOING LIVE (in order)
  1. Run test_public_endpoints.py and confirm every pair you intend to
     trade shows "active? YES" — TONUSDT does NOT (confirmed 2026-08),
     despite still being in generate_signals' TOP_PAIRS. This module
     refuses to build an order for a pair that isn't an active
     instrument (see _get_instrument()) rather than fail inside CoinDCX.
  2. Run this module in DRY_RUN mode against recent CLOSED donchian
     signals (known outcome) and manually check every logged payload:
     right pair, right side, right quantity (rounded to the pair's real
     quantity_increment), right leverage (under the pair's real
     max_leverage), right TP/SL.
  3. Flip DRY_RUN off ONLY with a tiny real position size on ONE signal,
     verify the fill on CoinDCX's own UI matches what was logged.
  4. Only then consider unattended/scheduled execution.

RISK CONTROLS ALREADY IN PLACE (do not remove without a reason)
  - DRY_RUN defaults True; requires an explicit env var AND a CLI flag to
    disable (two independent switches, not one — see main()).
  - MAX_POSITION_USDT hard-caps notional per order regardless of what the
    sizing math computes.
  - Refuses to build an order for a pair CoinDCX doesn't list as an
    active instrument (catches the TONUSDT case, and any future pair
    that gets delisted).
  - Quantity is rounded to the pair's REAL quantity_increment (fetched
    live from CoinDCX, not assumed) — an unrounded quantity would be
    rejected by the exchange.
  - Leverage is capped at the pair's REAL max_leverage_long/short,
    whichever is lower, regardless of EXECUTE_LEVERAGE's configured value.
  - Only ever acts on strategy='donchian', result='pending' signals that
    have NOT already been executed (tracked via the executed_orders
    table this module owns — see ensure_schema()).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

COINDCX_API_KEY = os.environ.get("COINDCX_API_KEY", "")
COINDCX_API_SECRET = os.environ.get("COINDCX_API_SECRET", "")

COINDCX_BASE = "https://api.coindcx.com"
CREATE_ORDER_PATH = "/exchange/v1/derivatives/futures/orders/create"
ACTIVE_INSTRUMENTS_PATH = "/exchange/v1/derivatives/futures/data/active_instruments"
INSTRUMENT_DETAIL_PATH = "/exchange/v1/derivatives/futures/data/instrument"

# ── risk controls ────────────────────────────────────────────────────────────
MAX_POSITION_USDT = float(os.environ.get("MAX_POSITION_USDT", "50"))
DEFAULT_LEVERAGE = int(os.environ.get("EXECUTE_LEVERAGE", "2"))
MARGIN_CURRENCY = "USDT"

RISK_PCT = float(os.environ.get("EXECUTE_RISK_PCT", "0.01"))
ACCOUNT_CAPITAL_USDT = float(os.environ.get("EXECUTE_ACCOUNT_CAPITAL_USDT", "1000"))


# ── CoinDCX request signing ───────────────────────────────────────────────────

def _sign(body: dict) -> tuple[str, str]:
    """Signs the exact JSON string sent on the wire — re-serializing after
    signing would change the string and invalidate the signature."""
    body_str = json.dumps(body, separators=(",", ":"))
    sig = hmac.new(
        COINDCX_API_SECRET.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return body_str, sig


def _post(path: str, body: dict, dry_run: bool) -> dict:
    body = dict(body)
    # EPOCH SECONDS, not milliseconds — every example in CoinDCX's real
    # docs uses Math.floor(Date.now()) in JS (ms) EXCEPT the futures
    # derivatives examples, which are explicitly documented as "EPOCH
    # timestamp in seconds". Getting this wrong doesn't corrupt the
    # signature (the signed string still matches what's sent) but WILL
    # get every request rejected as stale/future-dated by the API.
    body["timestamp"] = int(time.time())
    body_str, sig = _sign(body)

    headers = {
        "Content-Type": "application/json",
        "X-AUTH-APIKEY": COINDCX_API_KEY,
        "X-AUTH-SIGNATURE": sig,
    }

    if dry_run:
        print(f"  [DRY RUN] POST {COINDCX_BASE}{path}")
        print(f"  [DRY RUN] body: {body_str}")
        print(f"  [DRY RUN] headers: X-AUTH-APIKEY={COINDCX_API_KEY[:6] or '(none)'}... "
              f"X-AUTH-SIGNATURE={sig[:12]}...")
        return {"dry_run": True, "would_send": body}

    r = requests.post(f"{COINDCX_BASE}{path}", data=body_str, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


# ── instrument lookup (public, no key — always real, never hardcoded) ────────

_instrument_cache: dict[str, dict] = {}
_active_instruments_cache: list[str] | None = None


def _to_coindcx_pair(db_pair: str) -> str:
    """'ETHUSDT' -> 'B-ETH_USDT'. Confirmed against real CoinDCX active
    instruments via test_public_endpoints.py (2026-08) — see that
    script's docstring for how to re-verify if this ever needs revisiting
    (e.g. a non-USDT-quoted pair, which this project doesn't currently
    trade but would break this naive suffix split)."""
    if not db_pair.endswith("USDT"):
        raise ValueError(f"Unexpected pair format (not USDT-quoted): {db_pair}")
    return f"B-{db_pair[:-4]}_USDT"


def _get_active_instruments() -> list[str]:
    global _active_instruments_cache
    if _active_instruments_cache is None:
        r = requests.get(
            COINDCX_BASE + ACTIVE_INSTRUMENTS_PATH,
            params={"margin_currency_short_name[]": "USDT"},
            timeout=10,
        )
        r.raise_for_status()
        _active_instruments_cache = r.json()
    return _active_instruments_cache


def _get_instrument(coindcx_pair: str) -> dict:
    """Real per-pair rules (fee, quantity step, min notional, max
    leverage) fetched live from CoinDCX's public data endpoint — never
    hardcoded, since test_public_endpoints.py already showed these vary
    per pair (e.g. SOL max leverage 5x vs LTC 25x) and drift from any
    single documented 'example' figure."""
    if coindcx_pair not in _instrument_cache:
        r = requests.get(
            COINDCX_BASE + INSTRUMENT_DETAIL_PATH,
            params={"pair": coindcx_pair, "margin_currency_short_name": "USDT"},
            timeout=10,
        )
        r.raise_for_status()
        _instrument_cache[coindcx_pair] = r.json()["instrument"]
    return _instrument_cache[coindcx_pair]


def _round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


# ── signal -> order mapping ───────────────────────────────────────────────────

def _position_size(entry: float, stop_loss: float, instrument: dict) -> float:
    """R-based sizing: risk RISK_PCT of ACCOUNT_CAPITAL_USDT, position
    size = risk_amount / stop_distance_in_price — in the underlying
    asset's units (confirmed by the real docs, see module docstring).
    Rounded DOWN to the pair's real quantity_increment (e.g. DOGE trades
    in whole units, ETH in 0.001 steps) and capped at MAX_POSITION_USDT
    notional regardless of what the risk math computes."""
    risk_amount = ACCOUNT_CAPITAL_USDT * RISK_PCT
    stop_dist = abs(entry - stop_loss)
    if stop_dist <= 0:
        return 0.0
    qty = risk_amount / stop_dist

    notional = qty * entry
    if notional > MAX_POSITION_USDT:
        qty = MAX_POSITION_USDT / entry

    step = float(instrument.get("quantity_increment") or 0)
    qty = _round_to_step(qty, step) if step else qty

    min_qty = float(instrument.get("min_quantity") or 0)
    if qty < min_qty:
        return 0.0  # too small to place at all — caller must skip
    return qty


def _effective_leverage(instrument: dict) -> int:
    """Never exceeds the pair's real max leverage, whichever side is
    lower — a hardcoded EXECUTE_LEVERAGE could otherwise exceed what a
    specific pair actually allows (they range 5x-25x+ per
    test_public_endpoints.py) and get the order rejected, or worse, get
    silently clamped by CoinDCX to a value this module didn't account
    for in its own risk math."""
    max_lev = min(
        float(instrument.get("max_leverage_long") or DEFAULT_LEVERAGE),
        float(instrument.get("max_leverage_short") or DEFAULT_LEVERAGE),
    )
    return int(min(DEFAULT_LEVERAGE, max_lev))


def build_order_payload(signal: dict) -> dict | None:
    """Returns None (with a printed reason) if the pair isn't tradeable
    or the computed size rounds to zero — callers must check for None
    rather than assume every signal produces a valid order."""
    coindcx_pair = _to_coindcx_pair(signal["pair"])

    if coindcx_pair not in _get_active_instruments():
        print(f"  [SKIP] {signal['pair']} ({coindcx_pair}) is not an active "
              f"CoinDCX futures instrument — cannot place a real order.")
        return None

    instrument = _get_instrument(coindcx_pair)
    entry = float(signal["entry"])
    stop_loss = float(signal["stop_loss"])
    take_profit = float(signal["take_profit"])

    qty = _position_size(entry, stop_loss, instrument)
    if qty <= 0:
        print(f"  [SKIP] {signal['pair']} — computed size rounds below the pair's "
              f"min_quantity ({instrument.get('min_quantity')}); MAX_POSITION_USDT "
              f"may be too small for this pair's price/step.")
        return None

    notional = qty * entry
    min_notional = float(instrument.get("min_notional") or 0)
    if notional < min_notional:
        print(f"  [SKIP] {signal['pair']} — order notional ${notional:.2f} is below "
              f"the pair's min_notional ${min_notional}.")
        return None

    side = "buy" if signal["direction"] == "long" else "sell"
    leverage = _effective_leverage(instrument)

    return {
        "order": {
            "side": side,
            "pair": coindcx_pair,
            "order_type": "market_order",
            # price/stop_price omitted — not used for a market order per
            # the real docs ("Keep this NULL for market orders").
            "total_quantity": qty,
            "leverage": leverage,
            "notification": "no_notification",
            "margin_currency_short_name": MARGIN_CURRENCY,
            "take_profit_price": round(take_profit, 6),
            "stop_loss_price": round(stop_loss, 6),
        }
    }


# ── executed-order tracking (this module's own bookkeeping table) ────────────

def ensure_schema(supabase: Client) -> None:
    try:
        supabase.table("executed_orders").select("id").limit(1).execute()
    except Exception as exc:
        raise RuntimeError(
            "executed_orders table not found — run "
            "backend/execute_signals/schema.sql in the Supabase SQL editor first."
        ) from exc


def already_executed(supabase: Client, signal_id: str) -> bool:
    resp = (
        supabase.table("executed_orders")
        .select("id")
        .eq("signal_id", signal_id)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def record_execution(supabase: Client, signal: dict, order_resp: dict, dry_run: bool) -> None:
    supabase.table("executed_orders").insert({
        "signal_id": signal["id"],
        "pair": signal["pair"],
        "direction": signal["direction"],
        "dry_run": dry_run,
        "order_response": order_resp,
        "tp_sl_response": None,  # TP/SL is set IN the create-order call now
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# ── main ───────────────────────────────────────────────────────────────────

def fetch_pending_donchian_signals(supabase: Client) -> list:
    resp = (
        supabase.table("trade_signals")
        .select("*")
        .eq("strategy", "donchian")
        .eq("result", "pending")
        .order("timestamp", desc=True)
        .execute()
    )
    return resp.data or []


def execute_signal(supabase: Client, signal: dict, dry_run: bool) -> None:
    print(f"\n  {signal['pair']:<10} {signal['direction'].upper():<5} "
          f"entry={signal['entry']} sl={signal['stop_loss']} tp={signal['take_profit']}")

    order_body = build_order_payload(signal)
    if order_body is None:
        return  # reason already printed by build_order_payload

    print(f"  Order payload: {order_body}")
    order_resp = _post(CREATE_ORDER_PATH, order_body, dry_run)
    record_execution(supabase, signal, order_resp, dry_run)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                     help="Disable dry-run and send REAL orders. Also requires "
                          "EXECUTE_LIVE=true in the environment — both must be set.")
    ap.add_argument("--signal-id", type=str, default=None,
                     help="Execute one specific signal by id instead of all pending donchian signals.")
    args = ap.parse_args()

    dry_run = not (args.live and os.environ.get("EXECUTE_LIVE", "").lower() == "true")

    if not dry_run and (not COINDCX_API_KEY or not COINDCX_API_SECRET):
        raise RuntimeError("Live mode requires COINDCX_API_KEY and COINDCX_API_SECRET.")

    print(f"[execute_signals] {'DRY RUN' if dry_run else '*** LIVE — REAL ORDERS ***'}")
    if not dry_run:
        print("[execute_signals] Live mode confirmed by both --live and EXECUTE_LIVE=true.")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    ensure_schema(supabase)

    if args.signal_id:
        resp = supabase.table("trade_signals").select("*").eq("id", args.signal_id).execute()
        signals = resp.data or []
    else:
        signals = fetch_pending_donchian_signals(supabase)

    print(f"[execute_signals] {len(signals)} pending donchian signal(s) found.")

    for signal in signals:
        if already_executed(supabase, signal["id"]):
            print(f"  [SKIP] {signal['pair']} — already executed (id={signal['id'][:8]}...)")
            continue
        try:
            execute_signal(supabase, signal, dry_run)
        except Exception as exc:
            print(f"  [ERR] {signal['pair']}: {exc}")

    print(f"\n[execute_signals] Done. {'(nothing sent — dry run)' if dry_run else ''}")


if __name__ == "__main__":
    main()
