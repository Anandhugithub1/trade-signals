# BTC / ETH Option Signals

A technical-analysis signal engine for **BTC and ETH options**, adapted from
this repo's earlier NIFTY 50 index-options engine (`../nifty option trading`)
for a 24/7 crypto market. It generates **BUY CALL / BUY PUT** signals from
technical indicators on the BTC/ETH perpetual-futures price, sizes every
trade to a fixed USD stop-loss, and holds until stop/target/timeout (no
session close to square off against — crypto trades around the clock).

Built with **free, no-API-key data sources**:

- **Binance / Bybit / OKX futures klines** → BTC/ETH perpetual OHLC history,
  same three-provider fallback chain already used by this repo's main crypto
  signal engine (`backend/generate_signals`) — Binance and Bybit are
  geo-blocked on some cloud/CI IPs, OKX is the reliable final leg. OKX's
  `history-candles` endpoint additionally supports cursor pagination, which
  is what makes 24-month backtests possible from a single free endpoint.
- **Deribit public options API** → live ATM strike, mark price and IV for
  the nearest expiry (unofficial use of a public, no-auth endpoint; best
  effort, degrades gracefully — see caveats).

> ⚠️ **Not financial advice.** This is an educational/research tool. Option
> P&L in the backtest is a *delta-based approximation* — it ignores time
> decay (theta) and volatility (vega). Real results will differ. Trade at
> your own risk.

---

## Strategy

A signal fires only when **trend and momentum agree**, gated by a
trend-strength filter (industry-standard ADX gate, same anti-chop logic as
the NIFTY version — the single biggest lesson carried over: never fire a
trend-following signal in a flat/choppy ADX regime):

| Direction | Conditions (all must hold) |
|-----------|----------------------------|
| **BUY CALL** (bullish) | Supertrend up · EMA9 > EMA21 · RSI crosses up through 50 · ADX ≥ 25 |
| **BUY PUT** (bearish)  | Supertrend down · EMA9 < EMA21 · RSI crosses down through 50 · ADX ≥ 25 |

**Risk model:**

- **Stop-loss is USD-based** — you set `--max-loss` (default $200) and the
  algo sizes the position so a stop-out loses approximately that amount.
- **Target is tighter than the stop** (2.5× ATR target vs 2.0× ATR stop) —
  this is the opposite shape from the NIFTY module's "wide target, tight
  stop" and was **not** copied over on assumption; it's what a 24-month
  parameter sweep on real BTC/ETH data actually found. See "Research basis"
  below for why.
- **24/7, no square-off** — a position is held until stop, target, or
  `--max-hold-bars` (default 72×1h = 3 days), never force-closed for an
  exchange close, because crypto doesn't have one.
- **Cooldown between same-direction signals** (default 4 bars) — crypto has
  no session boundary to reset chatter, so without this a strong trend can
  retrigger on every RSI wobble.

---

## Setup

```bash
cd "crypto option trading"
pip install -r requirements.txt
```

## Usage

**Backtest / simulate** — 24 months of real 1h data (Binance/Bybit/OKX,
free, no key):

```bash
python src/backtest.py --symbols BTCUSDT,ETHUSDT --interval 1h --max-loss 200 --months 24
```

**Live signal** (latest signal + live price + Deribit ATM premium):

```bash
python src/live_signal.py --symbol BTCUSDT --max-loss 200
```

---

## Backtest results — REAL 24 months, 1h bars, $200 stop

Data from Binance/Bybit/OKX futures klines (2024-08-29 → 2026-08-19).

| Metric | Combined (BTC+ETH) | BTC only | ETH only |
|--------|---------------------|----------|----------|
| Trades | 237 (~10/month) | 124 | 113 |
| Win rate | 51.9% | 51.6% | 52.2% |
| Profit factor | **1.32** | 1.30 | 1.34 |
| **Total P&L** | **+$7,133** | +$3,558 | +$3,575 |
| Avg P&L / trade | +$30 | +$29 | +$32 |
| Avg win / loss | +$242 / −$198 | +$243 / −$200 | +$241 / −$197 |
| **Max single loss** | **−$200** (stop respected) | −$200 | −$200 |

**Monthly (combined, read this before trading):**

| Month | Trades | P&L | Cumulative |
|-------|-------|------|-----------|
| 2024-08 | 1 | +$250 | +$250 |
| 2024-09 | 12 | +$1,650 | +$1,900 |
| 2024-10 | 17 | +$1,550 | +$3,450 |
| 2024-11 | 7 | +$850 | +$4,300 |
| 2024-12 | 15 | −$541 | +$3,759 |
| 2025-01 | 8 | −$28 | +$3,730 |
| 2025-02 | 9 | −$0 | +$3,730 |
| 2025-03 | 7 | −$500 | +$3,230 |
| 2025-04 | 8 | −$1,150 | +$2,080 |
| 2025-05 | 13 | +$1,000 | +$3,080 |
| 2025-06 | 12 | +$300 | +$3,380 |
| 2025-07 | 9 | $0 | +$3,380 |
| 2025-08 | 8 | −$700 | +$2,680 |
| 2025-09 | 9 | +$450 | +$3,130 |
| 2025-10 | 9 | +$900 | +$4,030 |
| 2025-11 | 10 | +$700 | +$4,730 |
| 2025-12 | 7 | +$248 | +$4,978 |
| 2026-01 | 9 | −$663 | +$4,315 |
| 2026-02 | 9 | +$450 | +$4,765 |
| 2026-03 | 8 | +$1,100 | +$5,865 |
| 2026-04 | 8 | −$250 | +$5,615 |
| 2026-05 | 17 | +$667 | +$6,283 |
| 2026-06 | 9 | $0 | +$6,283 |
| 2026-07 | 10 | +$250 | +$6,533 |
| 2026-08 | 6 | +$600 | +$7,133 |

> ⚠️ Win rate is 52% — close to a coin-flip; the edge comes from wins
> averaging slightly larger than losses ($242 vs $198), not from a high hit
> rate. There were two real multi-month drawdowns (Dec'24–Apr'25, and
> Jan'26) — you must be able to sit through losing streaks. No slippage or
> exchange fees are modelled. Past performance is not indicative of future
> results.

### Research basis — why these parameters, not the NIFTY defaults

The NIFTY module's winning shape was "tight rupee stop + wide ATR target,
let winners run" (8× ATR target vs 1.5× ATR stop). Copying that directly to
crypto **lost money**: a first pass using the NIFTY-style wide target
(6× ATR) and ADX≥20 produced PF 0.85 and −$8,976 over 24 months. A
parameter sweep across ADX threshold, RSI midline, Supertrend multiplier,
and target/stop ratio — validated by requiring the winning config to be
profitable on BTC and ETH *independently*, not just in combined aggregate —
converged on the opposite shape for crypto:

- **RSI midline 50, not 52** — the NIFTY module's slightly-elevated 52
  threshold (deliberately requiring "stronger than flat" momentum) reduced
  crypto signal quality; 50 was uniformly better across the sweep.
- **ADX ≥ 25, stricter than NIFTY's 15–20** — crypto's 24/7 market chops
  more often than NIFTY's session-bounded trading day, so a stricter
  trend-strength gate matters more here.
- **Target (2.5× ATR) tighter than stop (2.0× ATR)** — the reverse of
  NIFTY's asymmetric "many small losses, few large winners" shape. Wide
  crypto targets (tested up to 6× ATR) got reversed by 24/7 volatility
  before they could be reached far more often than they were hit.

This is the kind of asset-specific result that justifies re-running a sweep
rather than porting a strategy's parameters by analogy — same lesson the
NIFTY README already documented for its own instrument, just re-learned
here for a different one.

---

## Files

```
crypto option trading/
├── requirements.txt
├── README.md
└── src/
    ├── indicators.py    # EMA, RSI, ATR, MACD, Supertrend (pure pandas)
    ├── data_feed.py     # Binance/Bybit/OKX perp history + Deribit option context
    ├── strategy.py      # signal rules + parameters (tuned via 24mo sweep)
    ├── backtest.py       # simulation: USD stop, ATR target, 24/7 timeout exit
    └── live_signal.py   # latest actionable signal with live Deribit premium
```

---

## Caveats & honest limitations

1. **Option P&L is approximated** via delta (0.5). Winners are understated
   (gamma helps), losers slightly understated (theta bleeds). Directionally
   sound, not tick-accurate — there is no free source of historical
   Deribit option premiums to replay instead.
2. **Deribit's public API is used unofficially** for the live ATM context;
   it can be rate-limited. The code degrades gracefully (returns `None`)
   but live premium may be unavailable.
3. **No slippage/exchange fees** modelled. Subtract taker fees + spread for
   a realistic net (Deribit options fees are typically ~0.03% of underlying,
   capped at a % of premium).
4. **24-month window is still one historical path.** BTC/ETH went through a
   specific mix of trending and choppy regimes in this window; the
   parameter sweep was validated for cross-asset (BTC vs ETH) consistency
   but not against a live-forward period, so treat it as informative, not
   guaranteed to repeat.
5. Position sizing assumes you can buy fractional underlying-equivalent
   option size; real listed strikes/lot conventions on Deribit may round
   this — check the actual instrument's minimum size before trading.
