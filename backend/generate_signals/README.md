# generate_signals

Automated trading signal generator for the top 15 crypto pairs + Gold (XAU) and Silver (XAG) perpetual futures.

Runs 3× per day via GitHub Actions. Produces at most **4 signals/day**.

---

## How the algorithm works

### Step 1 — Regime Gate (the most important step)

Before any indicators are checked, the algorithm asks: **is there actually a trend worth trading?**

Two conditions must both be true or no signal is generated:

1. **ADX(14) ≥ 20** — Average Directional Index measures trend *strength* (not direction). Below 20 = ranging/choppy market. Momentum strategies lose money in ranging markets, so we sit out entirely.
2. **EMA stack aligned** — For a long: `price > EMA50 > EMA200`. For a short: `price < EMA50 < EMA200`. This ensures all three trend layers agree on direction.

> This is what separates a systematic strategy from random indicator stacking. The ADX regime gate is the most proven single improvement in trend-following.

---

### Step 2 — Voting (all votes point WITH the trend)

Once a valid trend regime is confirmed, indicators vote **+1 (bullish) / −1 (bearish) / 0 (neutral)**.

Critically, all votes are regime-aware — they can only reinforce the confirmed direction, never fight it.

| # | Indicator | What it measures | How it votes |
|---|---|---|---|
| 1 | **EMA 200** | Macro trend (months) | +1 if price above, −1 below |
| 2 | **EMA 50** | Intermediate trend (weeks) | +1 if price above, −1 below |
| 3 | **EMA 20/50 cross** | Short-term momentum | +1 if EMA20 > EMA50 |
| 4 | **MACD** | Momentum direction + crossover | +1 if histogram positive (single vote — no double-count) |
| 5 | **OBV slope** | Volume confirms price move | +1 if OBV trending up |
| 6 | **Oscillators** | Oversold/overbought consensus | Regime-aware: oversold in uptrend = buy-the-dip (+1), NOT a counter short |
| 7 | **Bollinger %B** | Pullback depth | Regime-aware: dip below mid-band in uptrend = entry opportunity |
| 8 | **Funding rate** | Derivatives positioning | Negative = shorts paying (contrarian bullish) |
| 9 | **Long/Short ratio** | Crowd positioning | LSR < 0.8 = over-shorted (contrarian bullish) |
| 10 | **Market Context** | Combined sentiment | F&G + market-cap + news + macro collapsed into one vote; requires net agreement ≥ 2 to fire |
| 11 | **Volume spike** | Confirms conviction | Amplifies the net direction if volume is 1.5× average (always placed last) |

**Why indicators 6 & 7 are regime-aware:**
In the old version, RSI showing "overbought" during a strong uptrend would vote −1 (bearish), directly fighting the EMA trend votes. This caused the algorithm to "buy tops" — trend indicators pushing the score to +4, oscillators resisting. Now, overbought in an uptrend is simply neutral (0), and *oversold* in an uptrend is a buy opportunity (+1). The two philosophies no longer contradict.

**Why Market Context (news/sentiment) is collapsed to one vote:**
Google News keyword scoring individually gets the same weight as EMA200, which means a single news headline could flip a borderline signal. Now F&G + market-cap + news + macro must collectively agree (net ≥ +2 or ≤ −2) before adding one point. A single noisy headline can't move the score.

---

### Step 3 — Decision

```
LONG  if net score >= +4  AND  uptrend confirmed (EMA stack)
SHORT if net score <= -4  AND  downtrend confirmed (EMA stack)
Skip  otherwise
```

**Signal Strength** = `|score| / active_votes × 35 + 60` → mapped to 60–95%.

Signals below **72% strength** are discarded as low-conviction. The remaining candidates are ranked by strength and the top 4 are inserted (daily cap).

---

### Step 4 — Risk Sizing (1:1.5 RR floor, always)

Designed for **3–4% momentum swings on 1h candles**:

| Parameter | Value | Reasoning |
|---|---|---|
| Take Profit | Fixed **3.5%** from entry | Matches typical 1h momentum swing duration |
| Stop Loss | `min(2 × ATR, 2.3%)` | ATR-based breathing room, capped to prevent wide stops |
| RR floor | **1 : 1.5 minimum** | SL is tightened automatically if RR would fall below this |

The RR floor means a negative-expectancy trade (risk 2% to make 1%) is mathematically impossible to generate.

---

### Data sources (all free, no paid API keys)

| Source | Used for | Geo-blocked? |
|---|---|---|
| Binance Futures `fapi.binance.com` | 1h OHLCV candles (primary) | Yes — India & US |
| Bybit `api.bybit.com` | Candles (fallback 1) | Sometimes on Azure |
| **OKX `www.okx.com`** | Candles (fallback 2, always works) | No |
| Alternative.me | Fear & Greed Index | No |
| OKX | Funding rate + Long/Short ratio | No |
| CoinGecko | Global market cap 24h change | No |
| Google News RSS | Coin-specific headlines | No |
| CoinDesk RSS | Crypto market news | No |
| Reuters RSS + Google News | Macro events (Fed, rates, wars) | No |

The 3-provider candle fallback chain ensures signals generate reliably from GitHub Actions US runners where Binance and Bybit are geo-blocked.

---

### Pairs covered

**Crypto (top 15 by market cap, stablecoins excluded):**
BTC, ETH, BNB, SOL, XRP, ADA, DOGE, TRX, AVAX, TON, DOT, LINK, LTC, BCH, UNI

**Commodities:**
XAU (Gold), XAG (Silver) — both as USDT perpetuals on OKX/Bybit

> Note: Fear & Greed Index and Global Market Cap change are skipped for XAU/XAG since they measure crypto-specific sentiment, not commodity sentiment.

---

### Configuration knobs

```python
ADX_TREND_MIN     = 20    # lower = more signals in weak trends, raise to 25 for strict
MIN_BULL_SCORE    = 4     # votes needed to generate a signal
MIN_SIGNAL_STRENGTH = 72  # discard weak signals (60–95 scale)
MAX_SIGNALS       = 4     # daily cap
TARGET_TP_PCT     = 0.035 # 3.5% take profit
ATR_SL_MULT       = 2.0   # SL = 2× ATR
MAX_SL_PCT        = 0.023 # hard SL cap at 2.3%
MIN_RR            = 1.5   # reward:risk floor
```

---

### Running locally

```bash
cd backend/generate_signals
pip install -r requirements.txt
python handler.py
```

Requires a `.env` file — copy from `.env.example` and fill in your Supabase credentials.
