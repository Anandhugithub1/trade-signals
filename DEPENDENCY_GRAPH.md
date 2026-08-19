# Dependency Graph

How the pieces of Trade Pilot / Zenviq fit together — data flow between the
Flutter app, dashboard, backend jobs, Supabase, Firebase, and external market
data providers.

```mermaid
graph TD
    subgraph External["External data sources (free, no keys)"]
        Binance["Binance Futures"]
        Bybit["Bybit Futures"]
        OKX["OKX (candles, funding rate, L/S ratio)"]
        FG["Alternative.me Fear & Greed"]
        CG["CoinGecko (market cap)"]
        News["Google News / CoinDesk / Reuters RSS"]
    end

    subgraph Backend["backend/ — scheduled Python jobs (GitHub Actions)"]
        GenSignals["generate_signals\n(every 4h + pre-US-open)"]
        CheckSignals["check_signals\n(hourly 00:30-18:30 UTC)"]
        TradeChecker["trade_checker\n(manual/ad-hoc script)"]
    end

    subgraph Cloud["Cloud services"]
        Supabase[("Supabase\ntrade_signals, notification_tokens,\nmarket_sentiment tables")]
        Firebase["Firebase Cloud Messaging"]
    end

    subgraph Clients["Client apps"]
        FlutterApp["Flutter app (app/)\niOS / Android"]
        Dashboard["Next.js dashboard (dashboard/)"]
    end

    Binance -.fallback.-> Bybit -.fallback.-> OKX
    GenSignals -->|fetch candles| Binance
    GenSignals -->|funding rate, L/S ratio| OKX
    GenSignals --> FG
    GenSignals --> CG
    GenSignals --> News
    GenSignals -->|insert signal + note| Supabase
    GenSignals -->|new signal alert| Firebase

    CheckSignals -->|fetch candles/price| Binance
    CheckSignals -->|read pending, write win/loss| Supabase
    CheckSignals -->|result alert| Firebase

    TradeChecker -->|fetch price| Binance
    TradeChecker -->|read/update trade_signals| Supabase

    Firebase -->|push notification| FlutterApp

    FlutterApp -->|read signals, register device token| Supabase
    Dashboard -->|CRUD signals, view analytics| Supabase

    style Backend fill:#1a1a24,stroke:#6366f1,color:#fff
    style Cloud fill:#1a1a24,stroke:#22c55e,color:#fff
    style Clients fill:#1a1a24,stroke:#818cf8,color:#fff
    style External fill:#1a1a24,stroke:#475569,color:#fff
```

## Notes

- **generate_signals** is the core signal-generation engine (top 15 pairs,
  regime-filtered momentum strategy) — see
  [backend/generate_signals/handler.py](backend/generate_signals/handler.py).
- **check_signals** polls pending signals and marks them win/loss/expired
  once TP/SL/expiry is hit.
- **check_signals** (`crypto option trading/src`) is the BTC/ETH options
  equivalent: it closes out open option signals (win/loss/expired +
  `pnl_usd`, `closed_at`, `exit_reason`) and runs right after `run_signal.py`
  in the same workflow (`crypto_option_signals.yml`). Before it existed,
  option signals stayed `pending` forever, so the app's win-rate and P&L
  cards were computed over an empty set. This replaced the earlier NIFTY
  index-options engine (`nifty option trading/`, workflow disabled but kept
  on disk) as the app's Options tab.
- **trade_checker** is a standalone diagnostic script, not on a GitHub
  Actions schedule.
- Both `generate_signals` and `check_signals` push notifications through
  Firebase Cloud Messaging to devices registered in Supabase's
  `notification_tokens` table (written by the Flutter app).
- The dashboard and Flutter app never talk to each other or to the backend
  jobs directly — **Supabase is the single source of truth** all four
  surfaces read/write through.
