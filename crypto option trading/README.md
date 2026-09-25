# BTC / ETH Option Signals

> ## ⛔ RETIRED 2026-09-25 — no edge once time decay is priced in
>
> New signals are no longer generated on schedule; the resolver keeps
> running so positions opened before retirement still close out. Code and
> data are kept. The numbers further down this README came from a
> **delta-only** P&L model that ignores theta — that's the flaw.
>
> **Live record** (Aug 19 – Sep 25): 19 signals → 3 wins, 14 losses,
> 1 expired, 1 pending ≈ **−$2,050** at $200 risk/trade.
>
> **Re-test on fresh 24-month data, every trade re-priced with
> Black-Scholes** (ATM, ~96h expiry, IV = trailing 30-day realized vol):
>
> | Config | In-sample (to Feb 2026) | Out-of-sample (Feb–Sep 2026) |
> |---|---|---|
> | Current (stop 2.0×ATR, target 2.5×ATR) — delta model | PF 1.14, +10.8R | PF 1.13, +5.3R |
> | Current — **with theta** | PF 1.00, −0.4R | PF 0.94, −2.7R |
> | 1:3 (stop 1.0×, target 3.0×) — with theta | PF 0.96, −10.0R | PF 0.75, −35.5R |
> | 1:3 (stop 1.5×, target 4.5×) — with theta | PF 0.89, −23.9R | PF 0.87, −14.8R |
> | 1:3 (stop 2.0×, target 6.0×, ADX≥30) — with theta | PF 0.89, −8.6R | PF 0.94, −1.9R |
>
> (R = one $200 stop-out.) The current config's whole edge was ~+$14/trade
> in the delta model; theta on a ~4-day ATM option held ~17h costs more
> than that. **1:3 reward:risk made it worse, not better**: the tighter
> stop gets hit far more often (win rate 21–27%, at/below the 25%
> breakeven), and a tighter stop means a *bigger* position, so the
> premium outlay and theta bleed per trade go up (~$1,150 outlay vs
> ~$560). No 1:3 variant was positive in both halves of the data even
> before theta. Full sweep: 19 configs (ADX 20/25/30 × stop 1.0/1.5/2.0 ×
> hold 72h/168h).
>
> If this is ever revisited: the trend signal itself is roughly
> breakeven, not a real edge, so a different *instrument* (perp futures,
> no theta) wouldn't rescue it either — it needs a different signal.

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

### Live operational note — GitHub cron reliability vs. signal staleness

The first two weeks live (2026-08-19 → 09-04) surfaced a real gap between
the backtest and production: 4 signals fired and all 4 lost (a normal
outcome for a 52%-win-rate strategy — see above), but then **zero** new
signals fired for 9 straight days despite the strategy's own indicators
showing a real, tradeable RSI-50 cross on 2026-09-02.

Root cause: GitHub's scheduled cron does not actually run hourly under
load — observed gaps between real runs over ~200 runs: mean 115 min,
31% of gaps > 90 min, worst case ~13 hours. `run_signal.py`'s staleness
guard (`MAX_SIGNAL_AGE_MIN`, originally 90) was tighter than the cron's
real-world jitter, so a signal born at the top of an hour could already be
stale by the time the next (delayed) run checked for it, and got silently
discarded — with no signal at all in the meantime, since the lookback
window was also too shallow (4 bars) to still find it once discovered late.
Fixed by widening both `MAX_SIGNAL_AGE_MIN` (360 min) and the scan lookback
to match. See the comments in `src/run_signal.py` for the full trace.

### Which contract to buy — strike and expiry

The signal is generated on the underlying perp, but what you actually buy is
a specific Deribit contract. Two rules, both of which had to be fixed after
going live:

**Strike = ATM** (nearest listed strike to spot). Deliberate on two
independent grounds:
1. The backtest prices P&L with `option_delta = 0.5`, which *is* an ATM
   option. Buying ITM or OTM instead silently breaks the correspondence
   between the published expectancy above and what you actually trade.
2. It is where the liquidity is. A live 2026-09-04 BTC chain check showed
   open interest **25.0 at the ATM strike vs 0.0–1.4 at every neighbour** —
   a "cheaper" OTM strike often cannot be filled at a sane spread at all.

**Expiry = the first one that outlives the trade** (72h max hold + 12h
buffer, so ~84h+). *This was a real bug*: the original code took Deribit's
nearest expiry (`min(expiration_timestamp)`), which is routinely under 24h
out. The live 2026-08-26 BTCUSDT PUT was written against `BTC-27AUG26` — an
option expiring ~25h after a signal designed to be held up to 72h. It would
have expired worthless mid-trade regardless of whether the direction was
right. The buffer matters too: theta decay accelerates hardest in a
contract's final day, so expiring "just barely" after the close still bleeds
premium through the back half of the hold.

The app flags any signal whose contract still settles before the trade's own
square-off, rather than showing a contract that cannot work.

### Premium is quoted in coin, not dollars — and it is the real max loss

Deribit quotes BTC/ETH options in **units of the underlying**: a BTC put at
`0.0117` costs 0.0117 BTC (≈$950 at 81k spot), not $0.01. The backend
converts to USD before storing (`premium_usd`, `premium_cost_usd`).

Note the gap this exposes between the model and reality: sizing solves
`size = max_loss / (stop_distance × delta)` for a **$200** modelled loss,
but the premium outlay for that size is typically **~$410** — because when
you *buy* an option your true worst case is the entire premium, not the
modelled stop-out. `max_loss_usd` is what you lose if you exit at the stop
as intended; the premium is what you lose if it expires worthless. The app
shows both, deliberately.

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
