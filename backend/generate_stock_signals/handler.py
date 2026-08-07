"""
generate_stock_signals — swing-trade signals for the top 50 US stocks.

═══════════════════════════════════════════════════════════════════
 WHY THIS STRATEGY  (chosen by measurement, not by preference)
═══════════════════════════════════════════════════════════════════
Two candidates were backtested on 3 years of real daily bars for the same
top-50 universe, with 5bp slippage per side:

  A. "Dual momentum" — the textbook equity approach (absolute momentum via
     the 200-day MA + cross-sectional relative strength vs SPY + 12-1
     momentum). This is what the academic literature recommends for stocks.
  B. A port of the crypto engine's regime-filtered vote model to daily bars.

Over 6 INDEPENDENT non-overlapping ~4-month blocks, B won 5 of 6 and was
profitable in every single block; A had two losing blocks:

    block                     dual R    crypto R
    2024-08-05..2024-12-02      +4.3        +1.0
    2024-12-03..2025-04-04      -8.3        +0.1
    2025-04-07..2025-08-06     +10.0       +11.3
    2025-08-07..2025-12-04      -1.2        +7.3
    2025-12-05..2026-04-08      +1.2        +2.5
    2026-04-09..2026-08-07      +0.9       +15.1
    TOTAL                       +6.9       +37.3

So we use B. Note this is a walk-forward result on ONE universe over 3
years; it is evidence the approach generalises across regimes, not a
guarantee. Treat the R-multiples as indicative.

═══════════════════════════════════════════════════════════════════
 STRATEGY
═══════════════════════════════════════════════════════════════════
  DAILY bars (not intraday). US stocks trade 09:30-16:00 ET, so an
  intraday bar series carries ~17h overnight gaps that EMA/RSI/MACD read
  as momentum — the exact artifact that had to be fixed in the NIFTY
  strategy. Daily bars have no such discontinuity.

  STEP 1 — MARKET REGIME: SPY must be above its own 200-day EMA.
     Ablation over the same 6 blocks: total R is identical (+37.3 both
     ways) but the filter turns the one negative block positive
     (-1.9 -> +0.1). Free downside protection, so it stays on.

  STEP 2 — PER-STOCK REGIME GATE
     ADX(14) >= 20 and price > EMA50 > EMA200. No counter-trend trades.

  STEP 3 — VOTE (long-only; see note below)
     EMA200 / EMA50 / EMA20-50 stack, RSI vs 50, volume spike.
     Net score >= 4 qualifies.

  STEP 4 — RANK & CAP
     Highest score first, at most MAX_SIGNALS per day, skipping tickers
     that already have a pending signal.

  STEP 5 — RISK
     SL = 2x ATR(14); TP = 2R. Same R-multiple convention as the crypto
     job, so reward:risk is constant across names regardless of volatility.

LONG-ONLY: the backtest above only ever tested longs, and the regime
filter already restricts us to uptrending markets. Shorting stocks has
different mechanics (borrow, hard-to-borrow fees, unlimited loss) that the
model does not capture, so we do not emit short signals.

Trigger: once per weekday after the US close, via GitHub Actions.
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
from supabase import create_client, Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def _load_firebase_sa() -> str:
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if path and os.path.isfile(path):
        with open(path) as f:
            return f.read()
    return os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")


FIREBASE_SA_JSON = _load_firebase_sa()

# Top 50 US large-caps by market cap. Mega-caps only: tight spreads, deep
# liquidity, and no borrow issues. BRK-B uses the yfinance dash form.
TOP_STOCKS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B",
    "JPM", "LLY", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "JNJ", "WMT",
    "ABBV", "NFLX", "CRM", "BAC", "ORCL", "CVX", "KO", "AMD", "PEP", "TMO",
    "LIN", "ADBE", "MRK", "CSCO", "ACN", "MCD", "ABT", "PM", "IBM", "TXN",
    "QCOM", "GE", "CAT", "INTU", "VZ", "DIS", "AMGN", "NOW", "PFE", "SPGI",
]

# Precious metals. CoinDCX lists these as INR-settled perpetual futures
# (B-XAU_USDT / B-XAG_USDT — confirmed live on their public price feed), so
# they are reachable from India without the LRS route that US shares need.
#
# We trade them through the SAME engine as the stocks. Validated separately
# on 3y of daily bars: 5 of 6 walk-forward blocks profitable, none negative,
# +27.6R total (gold PF 3.49 / silver PF 2.16). That is BETTER block
# consistency than the equity universe -- but note the test window covers a
# historic gold bull run, so treat the magnitude as flattered by regime.
#
# yfinance symbols: GC=F / SI=F are the COMEX front-month futures, which
# track CoinDCX's XAU/XAG spot quotes closely.
METALS = {
    "GC=F": "XAUUSD",   # gold
    "SI=F": "XAGUSD",   # silver
}

# Everything the scanner ranks over.
UNIVERSE = TOP_STOCKS + list(METALS)


def display_symbol(sym: str) -> str:
    """Human ticker for storage/UI: 'GC=F' -> 'XAUUSD', 'AAPL' -> 'AAPL'."""
    return METALS.get(sym, sym)

BENCHMARK = "SPY"          # market-regime proxy
MIN_SCORE = 4              # net votes required
MAX_SIGNALS = 3            # equity slots inserted per run

# Metals get their OWN slot rather than competing in the equity pool.
# Measured: over 2 years gold/silver qualified on 235 and 132 days but won
# only 3 of 120 trades — 50 stocks crowd them out of 3 shared slots, so a
# combined pool gives you no metals exposure at all. A reserved slot is what
# makes the diversification real. Metals also correlate poorly with equities,
# which is the point of holding them.
MAX_METAL_SIGNALS = 1
ADX_TREND_MIN = 20
ATR_SL_MULT = 2.0
TP_R_MULT = 2.0
MAX_HOLD_DAYS = 20         # swing horizon; check_stock_signals expires past this
HISTORY_PERIOD = "2y"      # enough to warm a 200-day EMA


# ── indicators (pandas, daily bars) ──────────────────────────────────────────

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - prev).abs(),
                    (df["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    prev = c.shift()
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / atr_s
    mdi = 100 * mdm.ewm(alpha=1 / n, adjust=False).mean() / atr_s
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def fetch_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Daily OHLCV for every ticker in one batched yfinance call."""
    import yfinance as yf
    raw = yf.download(tickers, period=HISTORY_PERIOD, interval="1d",
                      progress=False, auto_adjust=True,
                      group_by="ticker", threads=True)
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            sub = raw[t][["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(sub) > 220:          # need a warm EMA200
                out[t] = sub
        except Exception:
            continue
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["ema20"] = _ema(x["Close"], 20)
    x["ema50"] = _ema(x["Close"], 50)
    x["ema200"] = _ema(x["Close"], 200)
    x["atr"] = _atr(x)
    x["adx"] = _adx(x)
    x["rsi"] = _rsi(x["Close"])
    x["vol_avg20"] = x["Volume"].rolling(20).mean()
    return x


def analyze(ticker: str, x: pd.DataFrame) -> dict | None:
    """Score the latest bar. Returns a signal dict, or None if it doesn't fire."""
    r = x.iloc[-1]
    need = (r["ema200"], r["ema50"], r["ema20"], r["adx"], r["atr"], r["rsi"])
    if any(pd.isna(v) for v in need):
        return None

    # Regime gate — trend must exist and be aligned.
    if r["adx"] < ADX_TREND_MIN:
        return None
    if not (r["Close"] > r["ema50"] > r["ema200"]):
        return None

    score = 0
    votes = []
    if r["Close"] > r["ema200"]:
        score += 1; votes.append("price > EMA200")
    if r["Close"] > r["ema50"]:
        score += 1; votes.append("price > EMA50")
    if r["ema20"] > r["ema50"]:
        score += 1; votes.append("EMA20 > EMA50")
    if r["rsi"] > 50:
        score += 1; votes.append(f"RSI {r['rsi']:.0f} > 50")
    vol_ratio = (r["Volume"] / r["vol_avg20"]) if r["vol_avg20"] else 1.0
    if vol_ratio >= 1.5:
        score += 1; votes.append(f"volume {vol_ratio:.1f}x avg")

    if score < MIN_SCORE:
        return None

    entry = float(r["Close"])
    atr_v = float(r["atr"])
    sl_dist = ATR_SL_MULT * atr_v
    if sl_dist <= 0:
        return None
    sl = entry - sl_dist
    tp = entry + TP_R_MULT * sl_dist

    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "ticker": display_symbol(ticker),
        "direction": "long",
        "entry": round(entry, 4),
        "stop_loss": round(sl, 4),
        "take_profit": round(tp, 4),
        "atr": round(atr_v, 4),
        "adx": round(float(r["adx"]), 1),
        "rsi": round(float(r["rsi"]), 1),
        "score": score,
        "rr_ratio": TP_R_MULT,
        "result": "pending",
        "entry_confirmed": False,
        "timestamp": now.isoformat(),
        "expires_at": (now + timedelta(days=MAX_HOLD_DAYS)).isoformat(),
        "note": f"ADX {r['adx']:.0f} uptrend; " + "; ".join(votes) + ".",
    }


def market_is_bullish(spy: pd.DataFrame) -> tuple[bool, str]:
    """SPY above its 200-day EMA. See the docstring's ablation."""
    r = spy.iloc[-1]
    if pd.isna(r["ema200"]):
        return False, "SPY EMA200 not warm"
    ok = bool(r["Close"] > r["ema200"])
    return ok, (f"SPY {r['Close']:.2f} {'>' if ok else '<'} "
                f"EMA200 {r['ema200']:.2f}")


def handler(event=None, context=None):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    print(f"\n[generate_stock_signals] {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")

    hist = fetch_history(UNIVERSE + [BENCHMARK])
    if BENCHMARK not in hist:
        print(f"  [ERR] no {BENCHMARK} data — cannot judge market regime; aborting")
        return {"statusCode": 200, "body": json.dumps({"skipped": "no benchmark"})}

    spy = add_indicators(hist[BENCHMARK])
    bullish, why = market_is_bullish(spy)
    print(f"  Market regime : {why}")
    if not bullish:
        print("  Risk-off — no long signals this run.\n")
        return {"statusCode": 200,
                "body": json.dumps({"skipped": "market risk-off", "detail": why})}

    # Tickers already holding an open signal
    pending = (supabase.table("stock_signals").select("ticker")
               .eq("result", "pending").execute()).data or []
    held = {p["ticker"] for p in pending}
    if held:
        print(f"  Already open  : {', '.join(sorted(held))}")

    equities, metals = [], []
    for t in UNIVERSE:
        # `held` stores display symbols, so compare on the same form.
        if display_symbol(t) in held or t not in hist:
            continue
        try:
            sig = analyze(t, add_indicators(hist[t]))
            if sig:
                (metals if t in METALS else equities).append(sig)
        except Exception as exc:
            print(f"  [ERR] {t}: {exc}")

    # Rank within each bucket, then fill their separate slots. Metals do not
    # compete against 50 equities for the same 3 slots (see MAX_METAL_SIGNALS).
    equities.sort(key=lambda s: -s["score"])
    metals.sort(key=lambda s: -s["score"])
    n_metal_held = len(held & {display_symbol(m) for m in METALS})
    chosen = (equities[:MAX_SIGNALS]
              + metals[:max(0, MAX_METAL_SIGNALS - n_metal_held)])
    print(f"  Qualified     : {len(equities)} equity + {len(metals)} metal "
          f"-> inserting {len(chosen)}")

    inserted = 0
    for sig in chosen:
        try:
            supabase.table("stock_signals").insert(sig).execute()
            print(f"  [DB OK] {sig['ticker']:<6} score={sig['score']} "
                  f"entry=${sig['entry']:.2f} SL=${sig['stop_loss']:.2f} "
                  f"TP=${sig['take_profit']:.2f}")
            inserted += 1
        except Exception as exc:
            print(f"  [DB ERR] {sig['ticker']}: {exc}")

    if inserted:
        _notify(supabase, chosen[:inserted])

    print(f"\n[generate_stock_signals] inserted {inserted}")
    return {"statusCode": 200,
            "body": json.dumps({"inserted": inserted,
                                "qualified_equity": len(equities),
                                "qualified_metal": len(metals)})}


def _notify(supabase, signals: list) -> None:
    """Push an FCM alert for newly inserted signals (no-op if unconfigured)."""
    if not FIREBASE_SA_JSON or not signals:
        return
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
        sa = json.loads(FIREBASE_SA_JSON)
        creds = service_account.Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
        creds.refresh(google.auth.transport.requests.Request())
        tokens = [r["device_token"] for r in
                  (supabase.table("notification_tokens")
                   .select("device_token").eq("is_enabled", True)
                   .execute().data or [])]
        if not tokens:
            return
        names = ", ".join(s["ticker"] for s in signals)
        url = f"https://fcm.googleapis.com/v1/projects/{sa['project_id']}/messages:send"
        headers = {"Authorization": f"Bearer {creds.token}",
                   "Content-Type": "application/json"}
        for tok in tokens:
            requests.post(url, headers=headers, json={"message": {
                "token": tok,
                "notification": {"title": "New Stock Signal"
                                          + ("s" if len(signals) > 1 else ""),
                                 "body": f"{len(signals)} new: {names}"},
                "data": {"type": "new_stock_signal"},
                "android": {"priority": "high"},
            }}, timeout=8)
        print(f"  [FCM] notified {len(tokens)} device(s)")
    except Exception as exc:
        print(f"  [FCM ERR] {exc}")


if __name__ == "__main__":
    print(json.dumps(json.loads(handler()["body"]), indent=2))
