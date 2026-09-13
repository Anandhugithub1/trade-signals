# Short New Listings

A signal engine that shorts newly-listed Binance USDT perpetual futures,
27-33 days after listing, with a defined stop-loss and an early
profit-lock exit. Replaces US Stock Signals as the app's 4th tab.

> ⚠️ **Not financial advice, and the underlying "new listings underperform"
> thesis is not confirmed.** This is a plain, short-only directional bet
> with real, uncapped downside (a short's loss is not bounded the way a
> long's is). Read "Research basis" below in full before risking real
> capital — it documents both what was validated and what was NOT.

---

## Strategy

**ENTRY**: short at the live price, once a listing is 27-33 days old (a
window, not an exact day, so GitHub's cron jitter can't cause a listing to
be skipped entirely — see `strategy.py`).

**EXIT**, whichever comes first:
| Trigger | Result |
|---|---|
| Price rises 30% above entry (adverse) | **STOP** — loss |
| Price falls 50% below entry (favourable) | **LOCK** — profit taken early |
| 30 days pass, neither triggered | **TIME** — close at whatever price it is |

This is the exact rule that was backtested — nothing else. Deliberately
**not** implemented: FDV/circulating-supply filters, token-unlock
calendars, "wait for a technical breakdown" confirmation. Those were part
of the original idea this engine grew out of, but none of them were
backtested, and they also need data Binance's API doesn't provide (FDV,
unlock dates) — pulling that from CoinGecko/CMC per-coin would add real
fragility for an unproven benefit. Add them later, but backtest first.

---

## Research basis — read this before trusting the numbers

### 1. Per-trade stats are real and stable

163 Binance listings (Aug 2025–Sep 2026), entry at day 30, 30% stop:

| Metric | Value |
|---|---|
| Win rate | 61.3% |
| Avg win | +30.2% |
| Avg loss | −27.6% |
| Avg P&L / trade | +$786 on a $10,000 position |

These numbers were stable across re-runs days apart (60.9-61.3% win rate,
~+$760-790/trade both times).

### 2. The "new listing" framing may not be a real edge — unconfirmed

A **control group** — shorting old, established coins (ETH, BNB, ADA, XRP,
LTC, LINK, DOT, SOL, AVAX, TRX) on the *same calendar dates* as the
new-listing entries — showed **statistically indistinguishable** results:
66.5% win rate, +7.58%/trade average, vs. the new-listing group's 64.4%
and +5.94%/trade (at a 30% stop). That means the apparent edge in the raw
30-day-hold version is probably explained by "the altcoin market fell
broadly during this ~13-month window", not something specific to newly
listed coins. **This control comparison has not been re-run against the
profit-lock version of the rule** (the one actually shipped here) — that
is the single most valuable next test before trusting this further.

### 3. Naive "$10k, one trade at a time, 100% risk" is dangerously unstable

Running the exact same rule on live data just 5 days apart gave:

| Run | Signals | Compounded $10k, one trade at a time |
|---|---|---|
| Run 1 | 163 | **+160.6%** ($26,057) |
| Run 2 (5 days later) | 151 | **−65.7%** ($3,433) |

The per-trade averages barely moved between these runs. The compounded
result flipped from strongly positive to badly negative purely because,
with only 15-17 non-overlapping trades fitting in ~13 months and 100% of
the account staked on each one, **the result is dominated by which few
trades you catch and in what order** — not by the underlying edge. Never
run this (or anything) risking your full account balance per trade.

### 4. Fixed-fractional sizing is far more stable — use this instead

Risking a fixed % of *current* equity per trade (so a full stop-loss only
costs that %, and multiple positions can run concurrently instead of
needing the account free for one trade at a time):

| Risk / trade | Result over ~13mo | Rough max drawdown |
|---|---|---|
| 2% | +108% | 4% |
| 5% | +450% | 10% |
| 10% | +1,906% | 20% |
| 20% | +8,153% | 61% |

Growth accelerates fast with higher risk, but so does drawdown — 10-20%
per trade is classic over-leveraging territory and is **not**
recommended. 2-5% is the sane range if you trade this at all.

**Caveat on all four of these sizing numbers**: they assume unlimited
margin/exchange capacity to run several concurrent small positions on
illiquid microcap alts, with no execution slippage. Real fills on thin new
listings will be worse than backtest-perfect daily-close/high/low prices.

### 5. A single real position can see 20-85x moves before crashing

While checking for what looked like data errors, two real, continuous
(non-glitched) price histories confirmed the tail risk this strategy is
built to fade: `RAVEUSDT` ran from $0.33 to $28 over about a month before
crashing; `LABUSDT` ran from $0.13 to $7.77 similarly. Both are legitimate
sustained melt-ups, not bad prints. This is exactly why the 30% stop
matters — without a real stop, a 6-month hold showed **36.6% of positions**
would hit a near-liquidation move (90%+ adverse) at some point.

**Bottom line**: treat the live signals from this engine as a
disciplined, defined-risk way to express a bearish view on hyped new
listings — not as a confirmed, validated edge. The control-group gap in
point 2 is the load-bearing unknown.

---

## Setup

```bash
cd "short new listings"
pip install -r requirements.txt
```

## Usage

**Backtest**:
```bash
python src/backtest.py --stop-pct 0.30 --lock-pct 0.50
```

**Live signal scan** (used by CI):
```bash
python src/run_signal.py
```

---

## Push notifications — old app installs never get these

New-signal and win/loss-resolution pushes exist (`src/push_notify.py`,
same FCM v1 pattern as the other engines), but are gated to devices
running app build **2 or later** — the first build that has the Shorts
tab at all. The app was never version-bumped before this feature shipped
(every APK built before it reports `1.0.0+1` forever, since an already-
installed binary's code cannot retroactively learn to send a new field),
so `notification_tokens.build_number` is the only thing separating "has
this feature" from "would just get a confusing push about a tab they
don't have." See `schema/migration_notification_build_gating.sql` and
`app/lib/services/push_notification_service.dart` for the full mechanism.

Requires the same `FIREBASE_SERVICE_ACCOUNT_JSON` secret (or a local
`FIREBASE_SERVICE_ACCOUNT_PATH`) the other engines use — set once,
already shared.

---

## Files

```
short new listings/
├── requirements.txt
├── README.md
├── schema/
│   ├── new_listing_shorts.sql
│   └── migration_notification_build_gating.sql
├── tests/
│   ├── test_strategy.py
│   ├── test_data_feed.py
│   └── test_push_notify.py
└── src/
    ├── data_feed.py       # Binance (+www.binance.com fallback) listings/klines
    ├── strategy.py        # entry window + stop/lock rule
    ├── backtest.py        # validation harness (this file's numbers)
    ├── run_signal.py      # CI entry point — scans + writes new signals
    ├── check_signals.py   # CI entry point — resolves open signals
    ├── push_notify.py     # build-gated FCM push (new signal + win/loss)
    └── supabase_writer.py
```

## Caveats & honest limitations

1. **No control-group re-check on the profit-lock rule** — see point 2
   above. This is the single biggest open question.
2. **Compounding is fragile with few trades** — see point 3. Use
   fixed-fractional position sizing, not full-account-per-trade.
3. **Survivorship bias**: only currently-listed (non-delisted) coins are
   included. Coins that crashed hardest and got delisted are missing —
   this would, if anything, understate the short-side edge, not overstate
   it, but it means the true trade count/frequency may be higher than
   what's testable here.
4. **No funding rate, fees, or slippage modelled.** Shorting a hyped coin
   with heavy long positioning typically means *receiving* funding
   (longs pay shorts when funding is positive), a real but unquantified
   tailwind not included in any number above.
5. **Non-independent trials**: many of the 150-160 listings cluster in
   the same calendar weeks, so the effective sample size for judging
   "is this a repeatable edge" is smaller than the trade count suggests.
