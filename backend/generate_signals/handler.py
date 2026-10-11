"""
generate_signals — creates trade signals for top crypto pairs by market cap.

Three robust algorithmic engines run side by side:
  1. Algo 1 (donchian.py) — 55-bar channel breakout, 4h bars, 1:3 R:R target.
  2. Algo 2 (algo2.py)    — 1h Macro Bull Momentum, 1:2 R:R target (+10% / -5%), LONG only.
  3. Algo 3 (algo3.py)    — 4h Bearish Macro Breakdown Short, 1:2 R:R target (+10% / -5%), SHORT only.

Replaces the old 1:1 mean reversion engine with 1:2 Algo 2 and Algo 3.
"""

from __future__ import annotations

import json
import os
import time
import requests
import numpy as np
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from google.oauth2 import service_account
import google.auth.transport.requests

from donchian import analyze_donchian
from algo2 import analyze_algo2
from algo3 import analyze_algo3

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── config ────────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

def _load_firebase_sa() -> str:
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if path and os.path.isfile(path):
        with open(path) as f:
            return f.read()
    return os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")

FIREBASE_SA_JSON = _load_firebase_sa()

BINANCE_FUTURES  = "https://fapi.binance.com/fapi/v1/klines"
BYBIT_KLINES     = "https://api.bybit.com/v5/market/kline"
OKX_KLINES       = "https://www.okx.com/api/v5/market/candles"
FEAR_GREED_URL   = "https://api.alternative.me/fng/?limit=1"

_HEADERS = {"User-Agent": "TradePilot/1.0 signal-bot"}


def _retry(fn, retries: int = 3, backoff: float = 1.5, label: str = ""):
    """
    Call fn() up to `retries` times with exponential backoff.
    """
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(retries):
        try:
            return fn()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code < 500:
                raise
            last_exc = exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        except Exception as exc:
            raise

        wait = backoff * (2 ** attempt)
        lbl  = f" [{label}]" if label else ""
        print(f"  [RETRY]{lbl} attempt {attempt + 1}/{retries} failed — retrying in {wait:.1f}s")
        time.sleep(wait)

    raise last_exc


# Top crypto by market cap — stablecoins excluded.
TOP_PAIRS = [
    "ETHUSDT",  "SOLUSDT",  "XRPUSDT",  "ADAUSDT",
    "DOGEUSDT", "TONUSDT",  "DOTUSDT",  "LTCUSDT",  "BCHUSDT",
    "UNIUSDT",
]

# ── Engine tags (written to the `strategy` column) ───────────────────────────
DONCHIAN_TAG = "donchian"  # Algo 1: 1:3 Breakout
ALGO2_TAG    = "algo2"     # Algo 2: 1:2 Macro Bull Momentum (Long)
ALGO3_TAG    = "algo3"     # Algo 3: 1:2 Bearish Macro Breakdown (Short)
LEGACY_TAG   = "legacy"

MAX_SIGNALS_PER_ENGINE = 3
MAX_SIGNALS            = MAX_SIGNALS_PER_ENGINE * 3  # 9 max/day across all 3 engines
CANDLE_LIMIT           = 300
SEP = "-" * 60


# ── technical indicators ──────────────────────────────────────────────────────

def _ema_array(data: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.empty_like(data)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = data[i] * k + out[i - 1] * (1 - k)
    return out


def calc_ema(close: np.ndarray, period: int) -> float:
    return float(_ema_array(close, period)[-1])


def calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    high  = high.astype(float)
    low   = low.astype(float)
    close = close.astype(float)

    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    up   = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    def _wilder(x: np.ndarray, n: int) -> np.ndarray:
        out = np.zeros(len(x))
        if len(x) < n:
            return out
        out[n - 1] = x[:n].sum()
        for i in range(n, len(x)):
            out[i] = out[i - 1] - out[i - 1] / n + x[i]
        return out

    tr_s  = _wilder(tr, period)
    pdm_s = _wilder(plus_dm, period)
    mdm_s = _wilder(minus_dm, period)

    plus_di  = 100 * np.divide(pdm_s, tr_s, out=np.zeros_like(tr_s), where=tr_s != 0)
    minus_di = 100 * np.divide(mdm_s, tr_s, out=np.zeros_like(tr_s), where=tr_s != 0)
    di_sum   = plus_di + minus_di
    dx       = 100 * np.abs(plus_di - minus_di) / np.where(di_sum == 0, 1, di_sum)
    return float(np.mean(dx[-period:]))


def _okx_symbol(pair: str) -> str:
    return pair[:-4] + "-USDT"


def fetch_candles(symbol: str, interval: str = "4h") -> list:
    binance_iv, bybit_iv, okx_iv = {
        "1h": ("1h", "60", "1H"),
        "4h": ("4h", "240", "4H"),
    }[interval]

    limit = 1000

    # 1. Binance Futures
    try:
        r = requests.get(
            BINANCE_FUTURES,
            params={"symbol": symbol, "interval": binance_iv, "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        print(f"  [WARN] Binance Futures {r.status_code} for {symbol} — trying Bybit")
    except Exception as e:
        print(f"  [WARN] Binance Futures error for {symbol} ({e}) — trying Bybit")

    # 2. Bybit Futures
    try:
        r = requests.get(
            BYBIT_KLINES,
            params={"category": "linear", "symbol": symbol,
                    "interval": bybit_iv, "limit": limit},
            headers=_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return list(reversed(r.json()["result"]["list"]))
        print(f"  [WARN] Bybit {r.status_code} for {symbol} — trying OKX")
    except Exception as e:
        print(f"  [WARN] Bybit error for {symbol} ({e}) — trying OKX")

    # 3. OKX
    r = requests.get(
        OKX_KLINES,
        params={"instId": _okx_symbol(symbol), "bar": okx_iv, "limit": limit},
        headers=_HEADERS, timeout=10,
    )
    r.raise_for_status()
    return list(reversed(r.json()["data"]))


def is_stale_feed(candles: list, lookback: int = 30) -> bool:
    if len(candles) < lookback:
        return False
    closes = {float(c[4]) for c in candles[-lookback:]}
    return len(closes) <= 1


def get_live_price(symbol: str) -> float | None:
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": symbol}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass

    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": symbol}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            items = r.json().get("result", {}).get("list", [])
            if items:
                return float(items[0]["lastPrice"])
    except Exception:
        pass

    try:
        r = requests.get(
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": _okx_symbol(symbol) + "-SWAP"}, headers=_HEADERS, timeout=6,
        )
        if r.status_code == 200 and r.json().get("data"):
            return float(r.json()["data"][0]["last"])
    except Exception:
        pass

    return None


# ── external sentiment ────────────────────────────────────────────────────────

def get_fear_greed() -> tuple[int, int, str]:
    try:
        r = requests.get(FEAR_GREED_URL, timeout=5)
        d = r.json()["data"][0]
        val   = int(d["value"])
        label = d["value_classification"]
        if val <= 25:
            return 1, val, f"Extreme Fear ({val}) — contrarian bullish"
        if val >= 75:
            return -1, val, f"Extreme Greed ({val}) — contrarian bearish"
        return 0, val, f"Neutral ({val} — {label})"
    except Exception as exc:
        return 0, -1, f"Fear/Greed unavailable ({exc})"


def _pair_trend_direction(candles: list) -> int:
    if len(candles) < 210:
        return 0
    close = np.array([float(c[4]) for c in candles])
    high  = np.array([float(c[2]) for c in candles])
    low   = np.array([float(c[3]) for c in candles])

    if calc_adx(high, low, close) < 20:
        return 0
    price  = close[-1]
    ema50  = calc_ema(close, 50)
    ema200 = calc_ema(close, 200)
    if price > ema50 > ema200:
        return 1
    if price < ema50 < ema200:
        return -1
    return 0


# ── push notifications ────────────────────────────────────────────────────────

def _get_fcm_access_token() -> tuple[str, str]:
    sa_info   = json.loads(FIREBASE_SA_JSON)
    project   = sa_info["project_id"]
    creds     = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token, project


def _send_push_notifications(supabase, inserted_signals: list) -> None:
    if not FIREBASE_SA_JSON or not inserted_signals:
        if not FIREBASE_SA_JSON:
            print("  [FCM]  FIREBASE_SERVICE_ACCOUNT_JSON not set — skipping push")
        return

    try:
        res = (
            supabase.table("notification_tokens")
            .select("device_token")
            .eq("is_enabled", True)
            .execute()
        )
        tokens = [r["device_token"] for r in (res.data or [])]
        if not tokens:
            print("  [FCM]  No enabled devices — skipping push")
            return

        bearer, project_id = _get_fcm_access_token()
        url     = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

        n      = len(inserted_signals)
        pairs  = ", ".join(s["pair"] for s in inserted_signals[:3])
        plural = "s" if n > 1 else ""
        title  = "New Trade Signal" + ("s" if n > 1 else "")
        body   = f"{n} new signal{plural}: {pairs}"

        ok = fail = 0
        for token in tokens:
            try:
                resp = requests.post(url, headers=headers, json={
                    "message": {
                        "token": token,
                        "notification": {"title": title, "body": body},
                        "data": {"type": "new_signal", "count": str(n)},
                        "android": {"priority": "high"},
                        "apns": {"payload": {"aps": {"sound": "default", "badge": n}}},
                    }
                }, timeout=8)
                if resp.status_code == 200:
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1

        print(f"  [FCM]  Sent to {len(tokens)} device(s) — {ok} ok / {fail} failed")

    except Exception as exc:
        print(f"  [FCM ERR]  {exc}")


# ── market sentiment ──────────────────────────────────────────────────────────

def _upsert_sentiment(supabase, analyses: list, fg_raw: int, fg_label: str) -> None:
    if not analyses:
        return

    bullish = sum(1 for a in analyses if a.get("score", 0) > 0)
    bearish = sum(1 for a in analyses if a.get("score", 0) < 0)
    neutral = len(analyses) - bullish - bearish
    total   = len(analyses)

    bullish_pct = round(bullish / total * 100)
    bearish_pct = round(bearish / total * 100)
    neutral_pct = max(0, 100 - bullish_pct - bearish_pct)

    dominant = "bullish" if bullish > bearish else "bearish" if bearish > bullish else "neutral"

    pending = (
        supabase.table("trade_signals")
        .select("direction")
        .eq("result", "pending")
        .execute()
    ).data or []
    active_longs  = sum(1 for s in pending if s.get("direction") == "long")
    active_shorts = sum(1 for s in pending if s.get("direction") == "short")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "date":             today,
        "bullish_pct":      bullish_pct,
        "neutral_pct":      neutral_pct,
        "bearish_pct":      bearish_pct,
        "fear_greed_value": fg_raw if fg_raw >= 0 else None,
        "fear_greed_label": fg_label,
        "active_longs":     active_longs,
        "active_shorts":    active_shorts,
        "dominant":         dominant,
    }

    supabase.table("market_sentiment").upsert(row, on_conflict="date").execute()

    print(f"\n  [SENTIMENT]  {today}  Bullish={bullish_pct}%  Neutral={neutral_pct}%  Bearish={bearish_pct}%  "
          f"Dominant={dominant}  F&G={fg_raw}  Longs={active_longs}  Shorts={active_shorts}")


# ── main handler ──────────────────────────────────────────────────────────────

def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    now_utc   = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[generate_signals] Started at {today_str}")

    # Daily cap check across all 3 engines
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_rows  = (
        supabase.table("trade_signals")
        .select("id, strategy")
        .gte("timestamp", today_start)
        .execute()
    ).data or []

    today_by_engine = {
        DONCHIAN_TAG: sum(1 for r in today_rows
                          if (r.get("strategy") or LEGACY_TAG) == DONCHIAN_TAG),
        ALGO2_TAG: sum(1 for r in today_rows
                       if (r.get("strategy") or LEGACY_TAG) == ALGO2_TAG),
        ALGO3_TAG: sum(1 for r in today_rows
                       if (r.get("strategy") or LEGACY_TAG) == ALGO3_TAG),
    }
    donchian_slots = max(0, MAX_SIGNALS_PER_ENGINE - today_by_engine[DONCHIAN_TAG])
    algo2_slots    = max(0, MAX_SIGNALS_PER_ENGINE - today_by_engine[ALGO2_TAG])
    algo3_slots    = max(0, MAX_SIGNALS_PER_ENGINE - today_by_engine[ALGO3_TAG])
    today_count    = len(today_rows)
    slots_left     = donchian_slots + algo2_slots + algo3_slots

    print(f"[generate_signals] Signals today: {today_count} / {MAX_SIGNALS}  "
          f"(Algo1-Donchian: {today_by_engine[DONCHIAN_TAG]}/{MAX_SIGNALS_PER_ENGINE}, "
          f"Algo2-BullMom: {today_by_engine[ALGO2_TAG]}/{MAX_SIGNALS_PER_ENGINE}, "
          f"Algo3-Short: {today_by_engine[ALGO3_TAG]}/{MAX_SIGNALS_PER_ENGINE})")

    if slots_left == 0:
        print(f"[generate_signals] All 3 engines at daily cap of "
              f"{MAX_SIGNALS_PER_ENGINE} — skipping run.\n")
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "today_count": today_count})}

    print(f"[generate_signals] Room for {donchian_slots} Algo1 + "
          f"{algo2_slots} Algo2 + {algo3_slots} Algo3 signal(s) this run.\n")

    fg_score, fg_raw, fg_reason = get_fear_greed()
    fg_label = fg_reason.split(" — ")[0] if " — " in fg_reason else fg_reason
    print(f"  Fear & Greed  : {fg_reason}\n")

    stats = {
        "analysed": 0, "inserted": 0,
        "no_signal": 0,
        "skipped_existing": 0, "errors": [],
        "today_count": today_count,
        "slots_left": slots_left,
    }

    # ── Pass 1: analyse all pairs, collect valid candidates ───────────────────
    breadth = []
    donchian_candidates = []
    algo2_candidates    = []
    algo3_candidates    = []

    for pair in TOP_PAIRS:
        try:
            existing = (
                supabase.table("trade_signals")
                .select("id, timestamp, strategy")
                .eq("pair", pair)
                .eq("result", "pending")
                .execute()
            ).data or []
            held_by = {r.get("strategy") or LEGACY_TAG for r in existing}

            d4 = None
            d1 = None

            # Fetch 4h candles if any engine has room for this pair
            if not (DONCHIAN_TAG in held_by and ALGO2_TAG in held_by and ALGO3_TAG in held_by):
                try:
                    d4 = fetch_candles(pair, interval="4h")
                    if is_stale_feed(d4):
                        print(f"  [STALE] {pair:<12} — price frozen, skipping pair")
                        stats["stale_feed"] = stats.get("stale_feed", 0) + 1
                        d4 = None
                except Exception as exc:
                    print(f"  [4H FETCH ERR] {pair}: {exc}")
                    d4 = None

            if d4 is None:
                stats["no_signal"] += 1
                continue

            stats["analysed"] += 1
            breadth.append({"pair": pair, "score": _pair_trend_direction(d4)})
            live_px = get_live_price(pair)

            # Fetch 1h candles if Algo 2 or Algo 3 need them
            if ALGO2_TAG not in held_by or ALGO3_TAG not in held_by:
                try:
                    d1 = fetch_candles(pair, interval="1h")
                except Exception as exc:
                    print(f"  [1H FETCH ERR] {pair}: {exc}")
                    d1 = None

            # Evaluate Algo 1 (Donchian 1:3 Breakout)
            if DONCHIAN_TAG in held_by:
                print(f"  [SKIP] {pair:<12} — Algo 1 (Donchian) position already open")
            else:
                try:
                    dsig = analyze_donchian(pair, d4, live_px)
                    if dsig:
                        donchian_candidates.append(dsig)
                        print(f"  [ALGO 1] {pair:<12} {dsig['direction'].upper():<5} "
                              f"entry={dsig['entry']:,.4f} "
                              f"({dsig['_rank']:.2f} ATR beyond channel)")
                except Exception as exc:
                    print(f"  [ALGO 1 ERR] {pair}: {exc}")

            # Evaluate Algo 2 (Macro Bull Momentum 1:2)
            if ALGO2_TAG in held_by:
                print(f"  [SKIP] {pair:<12} — Algo 2 (Bull Momentum) position already open")
            elif d1 is not None:
                try:
                    a2sig = analyze_algo2(pair, d1, d4, live_px)
                    if a2sig:
                        algo2_candidates.append(a2sig)
                        print(f"  [ALGO 2] {pair:<12} {a2sig['direction'].upper():<5} "
                              f"entry={a2sig['entry']:,.4f} rr=1:{a2sig['rr_ratio']:.2f}")
                except Exception as exc:
                    print(f"  [ALGO 2 ERR] {pair}: {exc}")

            # Evaluate Algo 3 (Macro Bearish Breakdown Short 1:2)
            if ALGO3_TAG in held_by:
                print(f"  [SKIP] {pair:<12} — Algo 3 (Short) position already open")
            else:
                try:
                    a3sig = analyze_algo3(pair, d4, d1, live_px)
                    if a3sig:
                        algo3_candidates.append(a3sig)
                        print(f"  [ALGO 3] {pair:<12} {a3sig['direction'].upper():<5} "
                              f"entry={a3sig['entry']:,.4f} rr=1:{a3sig['rr_ratio']:.2f}")
                except Exception as exc:
                    print(f"  [ALGO 3 ERR] {pair}: {exc}")

        except requests.HTTPError as exc:
            msg = f"{pair}: API HTTP {exc.response.status_code} (all providers failed)"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)
        except Exception as exc:
            msg = f"{pair}: {exc}"
            print(f"\n  [ERR] {msg}")
            stats["errors"].append(msg)

    # ── Pass 2: rank within each engine's own budget ──────────────────────────
    donchian_candidates.sort(key=lambda s: -s["_rank"])
    algo2_candidates.sort(key=lambda s: -s["_rank"])
    algo3_candidates.sort(key=lambda s: -s["_rank"])

    donchian_take = donchian_candidates[:donchian_slots]
    used_pairs = {s["pair"] for s in donchian_take}

    algo2_eligible = [s for s in algo2_candidates if s["pair"] not in used_pairs]
    algo2_take = algo2_eligible[:algo2_slots]
    used_pairs.update(s["pair"] for s in algo2_take)

    algo3_eligible = [s for s in algo3_candidates if s["pair"] not in used_pairs]
    algo3_take = algo3_eligible[:algo3_slots]

    to_insert = (
        [{"signal": s, "engine": DONCHIAN_TAG} for s in donchian_take]
        + [{"signal": s, "engine": ALGO2_TAG} for s in algo2_take]
        + [{"signal": s, "engine": ALGO3_TAG} for s in algo3_take]
    )

    print(f"\n  Engine mix: {len(donchian_take)}/{donchian_slots} Algo1 + "
          f"{len(algo2_take)}/{algo2_slots} Algo2 + "
          f"{len(algo3_take)}/{algo3_slots} Algo3  "
          f"[{len(donchian_candidates)} / {len(algo2_candidates)} / {len(algo3_candidates)} qualified]")

    # ── Pass 3: insert the winners ────────────────────────────────────────────
    if to_insert:
        print(f"\n{SEP}")
        print(f"  Inserting top {len(to_insert)} signal(s)  (max={MAX_SIGNALS}):\n")

    for analysis in to_insert:
        sig = dict(analysis["signal"])
        engine = analysis.get("engine", DONCHIAN_TAG)
        sig["strategy"] = engine
        sig.pop("_rank", None)
        try:
            supabase.table("trade_signals").insert(sig).execute()
            print(f"  [DB OK]  {sig['pair']:<12}  {sig['direction'].upper():<5}  "
                  f"[{engine}]  "
                  f"RR=1:{sig['rr_ratio']:.2f}  "
                  f"entry=${sig['entry']:,.4f}  id={sig['id'][:8]}...")
            stats["inserted"] += 1
            stats[f"inserted_{engine}"] = stats.get(f"inserted_{engine}", 0) + 1
        except Exception as exc:
            msg = f"{sig['pair']} insert failed: {exc}"
            print(f"  [DB ERR] {msg}")
            stats["errors"].append(msg)

    # ── Pass 4: push notifications ────────────────────────────────────────────
    inserted_sigs = [a["signal"] for a in to_insert if a["signal"]["pair"] not in
                     [e.split(" ")[0] for e in stats["errors"]]]
    _send_push_notifications(supabase, inserted_sigs[:stats["inserted"]])

    # ── Pass 5: upsert market sentiment ───────────────────────────────────────
    try:
        _upsert_sentiment(supabase, breadth, fg_raw, fg_label)
    except Exception as exc:
        print(f"\n  [SENTIMENT ERR] {exc}")

    print(f"\n{SEP}")
    print(f"[generate_signals] Done")
    print(f"  Inserted         : {stats['inserted']}  "
          f"(Algo1 {stats.get('inserted_' + DONCHIAN_TAG, 0)}, "
          f"Algo2 {stats.get('inserted_' + ALGO2_TAG, 0)}, "
          f"Algo3 {stats.get('inserted_' + ALGO3_TAG, 0)}; "
          f"cap {MAX_SIGNALS_PER_ENGINE}/engine, today total="
          f"{today_count + stats['inserted']})")
    print(f"  No signal        : {stats['no_signal']}")
    print(f"  Already pending  : {stats['skipped_existing']}")
    print(f"  Errors           : {len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"    - {e}")

    return {"statusCode": 200, "body": json.dumps(stats)}


if __name__ == "__main__":
    result = handler()
    print("\n" + json.dumps(json.loads(result["body"]), indent=2))
