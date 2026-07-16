# NIFTY 50 Option Signals

A technical-analysis signal engine for **NIFTY 50 index options**. It generates
intraday **BUY CE / BUY PE** signals from indicators on the NIFTY spot index,
sizes every trade to a fixed rupee stop-loss, and squares off the same day.

Built with **free, no-API-key data sources**:

- **yfinance** → NIFTY 50 index OHLC history (`^NSEI`) for backtesting & spot.
- **NSE public option-chain JSON** → live ATM strike, premium and PCR
  (unofficial, best-effort — see caveats below).

> ⚠️ **Not financial advice.** This is an educational/research tool. Option P&L
> in the backtest is a *delta-based approximation* — it ignores time decay
> (theta) and volatility (vega). Real results will differ. Trade at your own risk.

---

## Strategy

A signal fires only when **trend and momentum agree**:

| Direction | Conditions (all must hold) |
|-----------|----------------------------|
| **BUY CE** (bullish) | Supertrend up · EMA9 > EMA21 · RSI crosses up through 52 |
| **BUY PE** (bearish) | Supertrend down · EMA9 < EMA21 · RSI crosses down through 52 |

**Risk model (this is the important part):**

- **Stop-loss is rupee-based** — you set `--max-loss` (default ₹1,250) and the
  algo exits the moment the option's approximate loss reaches that amount.
  On NIFTY (lot = 75, ATM delta ≈ 0.5) a ₹1,250 stop ≈ 33 index points.
- **Target is wide** (8×ATR) — the edge comes from an asymmetric payoff:
  many small capped losses, fewer large winners.
- **Intraday only** — any open trade is squared off at the end of its own
  trading day. Nothing is carried overnight.

---

## Setup

```bash
cd "nifty option trading"
pip install -r requirements.txt
```

## Usage

**Backtest / simulate** — real 9 months of 15-min data (Upstox, free, no token):

```bash
python src/backtest.py --source upstox --months 9 --interval 15m --max-loss 1250
```

Or the quick 60-day version off yfinance (no Upstox needed):

```bash
python src/backtest.py --source yfinance --period 60d --interval 15m --max-loss 1250
```

Add `--no-reversal-exit` to test the fixed-ATR-target exit instead.

**Parameter sweep** (find profitable settings under your constraints):

```bash
python src/optimize.py
```

**Live signal** (latest signal + real ATM premium from NSE):

```bash
python src/live_signal.py --max-loss 1250
```

---

## Backtest results — REAL 9 months, 15-min bars, ₹1,250 stop

Data from the **Upstox** historical API (yfinance can't give 15m data past
60 days). Reversal exit, no trailing, intraday-only.

| Metric | Value |
|--------|-------|
| Period | Oct 2025 → Jul 2026 (9 months) |
| Trades | 112 (~12/month) |
| Win rate | 31.2% |
| Profit factor | 1.55 |
| **Total P&L** | **≈ +₹44,700** |
| Avg P&L / trade | +₹399 |
| Avg win / loss | +₹3,589 / −₹1,051 |
| **Max single loss** | **−₹1,250** (stop respected) |
| **Realistic monthly** | **≈ ₹5,000 / month per lot** |

**Month-by-month (read this before trading):**

| Month | Trades | P&L | Cumulative |
|-------|-------|------|-----------|
| Oct 25 | 6 | −₹2,402 | −₹2,402 |
| Nov 25 | 5 | +₹8,422 | +₹6,020 |
| **Dec 25** | 11 | **−₹13,368** | −₹7,348 |
| Jan 26 | 11 | −₹734 | −₹8,082 |
| Feb 26 | 19 | +₹7,540 | −₹542 |
| Mar 26 | 13 | +₹18,518 | +₹17,975 |
| Apr 26 | 12 | +₹7,601 | +₹25,576 |
| May 26 | 13 | +₹11,656 | +₹37,232 |
| Jun 26 | 17 | +₹7,245 | +₹44,477 |
| Jul 26 | 5 | +₹202 | +₹44,679 |

> ⚠️ **This strategy was UNDERWATER for its first 5 months** (bottomed at
> −₹8,082 after a −₹13k December) before turning profitable. Win rate is only
> **31%** — you lose ~7 of 10 trades and rely on a few big winners. You must be
> able to sit through long losing streaks. Subtract ~₹50/trade brokerage
> (~₹5,600 total) for a realistic net of ≈ ₹39k. Past performance is not
> indicative of future results.

**Trailing stop is OFF by default on purpose:** enabling it turned this same
+₹44.7k result into a −₹9.4k *loss* — it caps the big winners the edge depends on.

---

## Files

```
nifty option trading/
├── requirements.txt
├── README.md
└── src/
    ├── indicators.py    # EMA, RSI, ATR, MACD, Supertrend (pure pandas)
    ├── data_feed.py     # yfinance history + NSE option-chain fetch
    ├── upstox_feed.py   # Upstox v3 historical loader (free 15m, ~1yr+)
    ├── strategy.py      # signal rules + parameters
    ├── backtest.py      # simulation: rupee stop, reversal/trail, intraday exit
    ├── optimize.py      # parameter sweep
    ├── run_signal.py    # CI entry point (used by GitHub Actions)
    └── live_signal.py   # latest actionable signal with live premium
```

---

## Caveats & honest limitations

1. **Option P&L is approximated** via delta (0.5). Winners are understated
   (gamma helps), losers slightly understated (theta bleeds). Directionally
   sound, not tick-accurate.
2. **NSE endpoints are unofficial** and can be blocked/rate-limited. The code
   degrades gracefully (returns `None`) but live premium may be unavailable.
3. **No slippage/brokerage** modelled. Round-trip cost on 1 NIFTY lot is
   ~₹40–60; subtract that per trade for a realistic net.
4. **yfinance intraday history** is capped (~60 days for 15m bars), so the
   backtest window is short. Longer validation needs a paid/historical source.
5. Lot size is hard-coded to **75** in `backtest.py` — update if the exchange
   revises the NIFTY contract.
```
