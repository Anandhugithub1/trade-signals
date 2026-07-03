"""
trade_checker — estimates the probability of hitting TP vs SL for pending signals.

STATUS: standalone / log-only. Not wired into any cron workflow or called by
        generate_signals / check_signals. Run manually to inspect probability
        estimates for currently pending signals.

═══════════════════════════════════════════════════════════════════
 METHOD — Monte Carlo probability-of-touch simulation
═══════════════════════════════════════════════════════════════════
For each pending signal:
  1. Pull recent 1h candles for the pair (same provider fallback chain as
     generate_signals / check_signals: Binance → Bybit → OKX).
  2. Estimate hourly volatility (stdev of log returns) from the last N candles.
  3. Simulate thousands of possible future price paths from the current live
     price forward to the signal's expiry, using Geometric Brownian Motion
     (zero-drift — we don't assume the algorithm's directional edge here,
     this measures pure statistical probability-of-touch, not signal quality).
  4. For each simulated path, walk hour-by-hour and record whichever of
     SL / TP is touched first (if either).
  5. Aggregate across all simulated paths:
       P(TP first) + P(SL first) + P(neither, expires pending) ≈ 100%

This is the same probability-of-touch approach used in options pricing
(barrier option touch probability) — it does NOT predict direction, only
"given random-walk price action at this volatility, how often does the
price path reach TP before SL, before expiry."

Zero-drift is a deliberate choice: it isolates the risk/reward GEOMETRY
(how far is TP vs SL, how much time is left, how volatile is the pair)
from the algorithm's directional call. A signal with a tight TP and wide
SL will show a high P(TP) here even before considering whether the trend
call itself is correct.

Trigger: NONE. Manual run only — `python handler.py`
"""

import os
import sys
import numpy as np
import requests
from datetime import datetime, timezone
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── config ────────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1/klines"
BYBIT_KLINES    = "https://api.bybit.com/v5/market/kline"
OKX_KLINES      = "https://www.okx.com/api/v5/market/candles"
_HEADERS        = {"User-Agent": "TradePilot/1.0 trade-checker"}

VOL_LOOKBACK_CANDLES = 100     # 1h candles used to estimate hourly volatility
N_SIMULATIONS        = 5000    # Monte Carlo paths per signal
MAX_HORIZON_HOURS     = 96     # hard cap on simulated horizon (4 days)
SEP = "-" * 60


# ── candle fetch (same fallback chain as generate_signals / check_signals) ────

def _okx_symbol(pair: str) -> str:
    return pair[:-4] + "-USDT"


def fetch_candles(symbol: str, limit: int = VOL_LOOKBACK_CANDLES) -> list:
    """1h OHLCV candles, oldest-first. Binance -> Bybit -> OKX fallback."""
    try:
        r = requests.get(
            BINANCE_FUTURES,
            params={"symbol": symbol, "interval": "1h", "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass

    try:
        r = requests.get(
            BYBIT_KLINES,
            params={"category": "linear", "symbol": symbol,
                    "interval": "60", "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return list(reversed(r.json()["result"]["list"]))
    except Exception:
        pass

    r = requests.get(
        OKX_KLINES,
        params={"instId": _okx_symbol(symbol), "bar": "1H", "limit": limit},
        headers=_HEADERS, timeout=10,
    )
    r.raise_for_status()
    return list(reversed(r.json()["data"]))


def get_live_price(symbol: str) -> float | None:
    """Real-time last-traded price. Same 3-provider fallback."""
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/price",
                         params={"symbol": symbol}, headers=_HEADERS, timeout=6)
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass

    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers",
                         params={"category": "linear", "symbol": symbol},
                         headers=_HEADERS, timeout=6)
        if r.status_code == 200:
            items = r.json().get("result", {}).get("list", [])
            if items:
                return float(items[0]["lastPrice"])
    except Exception:
        pass

    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker",
                         params={"instId": _okx_symbol(symbol) + "-SWAP"},
                         headers=_HEADERS, timeout=6)
        if r.status_code == 200 and r.json().get("data"):
            return float(r.json()["data"][0]["last"])
    except Exception:
        pass

    return None


# ── volatility estimation ────────────────────────────────────────────────────

def estimate_hourly_volatility(candles: list) -> float:
    """
    Returns the stdev of hourly log returns — the per-hour volatility (sigma)
    used to drive the Monte Carlo simulation.
    """
    closes = np.array([float(c[4]) for c in candles])
    if len(closes) < 2:
        return 0.0
    log_returns = np.diff(np.log(closes))
    return float(np.std(log_returns))


# ── Monte Carlo probability-of-touch ─────────────────────────────────────────

def simulate_touch_probability(
    entry: float,
    current_price: float,
    stop_loss: float,
    take_profit: float,
    direction: str,
    hourly_sigma: float,
    hours_remaining: int,
    n_sims: int = N_SIMULATIONS,
) -> dict:
    """
    Zero-drift Geometric Brownian Motion simulation.

    Simulates `n_sims` independent hourly price paths starting from
    `current_price`, running for `hours_remaining` hours. Each path uses:
        price[t+1] = price[t] * exp(sigma * Z)     Z ~ N(0, 1)

    For each path, walks hour by hour and records whichever of SL/TP is
    touched first. Paths that touch neither by the horizon are counted
    as "neither" (still pending at expiry).

    Returns probabilities as percentages, summing to ~100%.
    """
    if hours_remaining <= 0 or hourly_sigma <= 0:
        return {"p_tp": 0.0, "p_sl": 0.0, "p_neither": 100.0, "n_sims": 0}

    hours_remaining = min(hours_remaining, MAX_HORIZON_HOURS)

    rng = np.random.default_rng()
    # shape: (n_sims, hours_remaining) — one log-return draw per hour per path
    log_returns = rng.normal(loc=0.0, scale=hourly_sigma, size=(n_sims, hours_remaining))
    # cumulative log price path per simulation
    log_paths = np.cumsum(log_returns, axis=1)
    price_paths = current_price * np.exp(log_paths)

    hit_tp = np.zeros(n_sims, dtype=bool)
    hit_sl = np.zeros(n_sims, dtype=bool)

    if direction == "long":
        tp_touch = price_paths >= take_profit
        sl_touch = price_paths <= stop_loss
    else:  # short
        tp_touch = price_paths <= take_profit
        sl_touch = price_paths >= stop_loss

    for i in range(n_sims):
        tp_idx = np.argmax(tp_touch[i]) if tp_touch[i].any() else -1
        sl_idx = np.argmax(sl_touch[i]) if sl_touch[i].any() else -1

        if tp_idx == -1 and sl_idx == -1:
            continue  # neither touched — still pending at horizon
        elif sl_idx == -1:
            hit_tp[i] = True
        elif tp_idx == -1:
            hit_sl[i] = True
        elif tp_idx <= sl_idx:
            hit_tp[i] = True
        else:
            hit_sl[i] = True

    p_tp = float(np.mean(hit_tp)) * 100
    p_sl = float(np.mean(hit_sl)) * 100
    p_neither = 100.0 - p_tp - p_sl

    return {
        "p_tp": round(p_tp, 1),
        "p_sl": round(p_sl, 1),
        "p_neither": round(max(0.0, p_neither), 1),
        "n_sims": n_sims,
    }


# ── logging ───────────────────────────────────────────────────────────────────

def log_signal_probability(signal: dict, result: dict, sigma: float, hours_left: float) -> None:
    pair      = signal["pair"]
    direction = signal["direction"].upper()
    entry     = float(signal["entry"])
    sl        = float(signal["stop_loss"])
    tp        = float(signal["take_profit"])

    print(SEP)
    print(f"  {pair:<12} {direction:<6}  entry=${entry:,.4f}")
    print(f"  SL = ${sl:,.4f}   TP = ${tp:,.4f}")
    print(f"  Hourly volatility (sigma) = {sigma*100:.3f}%   Hours remaining = {hours_left:.1f}h")
    print()
    print(f"  P(TP hit first)      : {result['p_tp']:>5.1f}%")
    print(f"  P(SL hit first)      : {result['p_sl']:>5.1f}%")
    print(f"  P(neither / expires) : {result['p_neither']:>5.1f}%")
    print(f"  ({result['n_sims']:,} simulated paths)")

    if result["p_tp"] + result["p_sl"] > 0:
        implied_wr = result["p_tp"] / (result["p_tp"] + result["p_sl"]) * 100
        print(f"  Implied win rate (TP vs SL only) : {implied_wr:.1f}%")


# ── main ──────────────────────────────────────────────────────────────────────

def check_all_pending() -> list[dict]:
    """
    Fetches all pending signals from Supabase, estimates TP/SL touch
    probability for each, logs results. Returns the list of result dicts
    (not persisted anywhere — caller decides what to do with them).
    """
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    print(f"\n[trade_checker] Started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"[trade_checker] LOG-ONLY — not persisted, not wired into any cron\n")

    response = supabase.table("trade_signals").select("*").eq("result", "pending").execute()
    signals = response.data or []
    print(f"[trade_checker] {len(signals)} pending signal(s) found")

    results = []

    for signal in signals:
        pair = signal["pair"]
        try:
            candles = fetch_candles(pair)
            sigma = estimate_hourly_volatility(candles)

            live = get_live_price(pair)
            current_price = live if live is not None else float(candles[-1][4])

            expires_at = signal.get("expires_at")
            if expires_at:
                expiry_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                hours_left = max(0.0, (expiry_dt - datetime.now(timezone.utc)).total_seconds() / 3600)
            else:
                hours_left = 72.0  # fallback horizon if expires_at missing

            result = simulate_touch_probability(
                entry=float(signal["entry"]),
                current_price=current_price,
                stop_loss=float(signal["stop_loss"]),
                take_profit=float(signal["take_profit"]),
                direction=signal["direction"],
                hourly_sigma=sigma,
                hours_remaining=int(round(hours_left)),
            )

            log_signal_probability(signal, result, sigma, hours_left)
            results.append({"pair": pair, "id": signal["id"], **result})

        except Exception as exc:
            print(f"\n  [ERR] {pair}: {exc}")

    print(f"\n{SEP}")
    print(f"[trade_checker] Done — {len(results)} signal(s) analysed, 0 written to DB (log-only)")
    return results


if __name__ == "__main__":
    check_all_pending()
