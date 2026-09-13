# Zenviq

A free trading-signals platform: a Python backend generates signals across
several independent strategy engines, a Flutter mobile app shows them to
users, and a Next.js dashboard gives the operator visibility and analytics.
No login required in the app, no paywall.

## Repo layout

```
trade pilot/
├── app/                       Flutter mobile app (Android/iOS/Web)
├── backend/
│   ├── generate_signals/      Crypto perp futures — LONG/SHORT, top 15 pairs + gold/silver
│   ├── check_signals/         Resolves SL/TP on open crypto futures signals
│   ├── generate_stock_signals/  US stock swing signals (deprecated, kept on disk)
│   ├── check_stock_signals/     Resolves + refreshes stock signals (deprecated)
│   ├── execute_signals/       Dry-run CoinDCX execution for donchian signals
│   ├── monthly_summary/       Permanent monthly P&L rollup across all engines
│   └── trade_checker/         Standalone diagnostic script
├── crypto option trading/     BTC/ETH options — buy CALL/PUT, 24-month backtested
├── short new listings/        Short newly-listed Binance perps, 27-33 days post-listing
├── nifty option trading/      NIFTY 50 index options (deprecated, kept on disk)
├── dashboard/                 Next.js 16 admin dashboard (auth-gated)
└── .github/workflows/         GitHub Actions cron schedules for every engine
```

Supabase (Postgres) is the shared database — every surface reads/writes
through the same anon/service keys, with Row-Level Security enforcing
read-only public access and service-role-only writes.

## Where to look next

- **`PROJECT_CONTEXT.md`** — the full write-up: algorithms, schema,
  deployment notes, and a running list of things deliberately *not* to
  reintroduce (bugs already found and fixed once).
- **`DEPENDENCY_GRAPH.md`** — how data flows between the backend jobs,
  Supabase, Firebase, and the two client apps.
- Each engine folder under `backend/` and at the repo root has its own
  `README.md` with the strategy, backtest results, and honest caveats
  about what's actually been validated versus assumed.

## Status of each signal engine

| Engine | Status |
|---|---|
| Crypto futures (`backend/generate_signals`) | Live |
| Crypto options (`crypto option trading`) | Live |
| Short new listings (`short new listings`) | Live |
| US stock signals (`backend/generate_stock_signals`) | Deprecated — code kept, cron disabled |
| NIFTY options (`nifty option trading`) | Deprecated — code kept, cron disabled |

> ⚠️ Not financial advice. Every engine's own README documents what was
> actually backtested versus assumed — read the caveats before trusting
> any number.
