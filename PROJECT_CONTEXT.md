# TradePilot — Project Context

Last updated: 2026-07-02

## What this is

A crypto + commodity **futures trading signals** platform. A Python backend analyzes
15 top crypto pairs + Gold/Silver perpetuals, generates LONG/SHORT trade signals with
entry/SL/TP, and delivers them free via a Flutter mobile app and a Next.js admin dashboard.

**Business model:** Free MVP — no login required in the mobile app, no paywall.
The admin dashboard IS gated (email allowlist) since it's the operator's control panel.

---

## Repo layout

```
trade pilot/
├── app/                    Flutter mobile app (Android/iOS/Web)
├── backend/
│   ├── generate_signals/   Python — creates new signals (cron, every 4h)
│   └── check_signals/      Python — resolves SL/TP hits (cron, hourly)
├── dashboard/               Next.js 16 admin web dashboard
└── .github/workflows/       GitHub Actions cron definitions
```

Supabase (Postgres) is the shared database — all three surfaces read/write the
`trade_signals` and `market_sentiment` tables via the same anon/service keys.

---

## Backend — signal generation algorithm

File: `backend/generate_signals/handler.py`
Full algorithm writeup: `backend/generate_signals/README.md` (read this for the
complete indicator table — don't re-derive it, it's already documented in depth).

**Strategy in one line:** ADX-gated momentum trading on 1h candles, targeting
3.5% moves with a hard 1:1.5 reward:risk floor.

Key facts to remember:
- **Timeframe is 1h** (was 4h — changed because 3-4% targets need hourly resolution,
  4h candles alone often exceed 3% range and stop out the trade before it develops)
- **Regime gate first**: ADX(14) >= 20 AND EMA50/EMA200 stack aligned, or NO signal.
  This was the single biggest fix — the old version summed trend-following and
  mean-reversion votes that fought each other (buying tops because oscillators
  said "overbought" while trend said "buy" simultaneously)
- Oscillators (RSI/StochRSI/Williams%R) and Bollinger are **regime-aware**: an
  oversold reading in a confirmed uptrend is a pullback buy signal, never a
  counter-trend short
- **Entry price = live ticker price**, not the candle close (candle close can be
  up to 1h stale). `get_live_price()` fetches the real-time last-traded price.
- SL/TP: TP fixed 3.5%, SL = min(2×ATR, 2.3% cap), auto-tightened to guarantee
  RR >= 1:1.5. A negative-expectancy signal is mathematically impossible.
- **"Confidence" was renamed to "Signal Strength"** everywhere in the UI (Flutter +
  dashboard) because "confidence %" implied a calibrated win probability that
  didn't exist. The Supabase column is still literally named `confidence` —
  don't rename the DB column, only the UI label.
- **Expiry window: 3-4 days** (was 2-7, tightened per user request — momentum
  trades shouldn't sit open for a week)
- Max **4 signals/day**, ranked by signal strength, daily-count-checked before
  each run so the workflow exits in ~3s once the cap is hit (saves Action minutes)
- **17 pairs**: top 15 crypto by market cap (BTC, ETH, BNB, SOL, XRP, ADA, DOGE,
  TRX, AVAX, TON, DOT, LINK, LTC, BCH, UNI) + XAUUSDT (Gold) + XAGUSDT (Silver)
- Fear & Greed and crypto market-cap-change are **skipped for XAU/XAG** — those
  indicators measure crypto sentiment, not commodity sentiment
- News/macro/F&G/mktcap sentiment is collapsed into ONE low-weight
  "Market Context" vote (needs net agreement >= 2) so a single noisy headline
  can't flip a technical setup — previously each had equal weight to EMA200

### Candle-fetch provider fallback chain (important — do not simplify)

Binance Futures and Bybit are **geo-blocked** on GitHub Actions runners (they run
from US/Azure IPs). The fallback chain exists for a real operational reason:

1. Binance Futures (`fapi.binance.com`) — blocked in US & India, tried first anyway
2. Bybit (`api.bybit.com`) — blocked on Azure cloud IPs specifically
3. **OKX** (`www.okx.com`) — always works from GitHub Actions, final fallback

Same chain used in both `generate_signals` and `check_signals`, and for the
`get_live_price()` ticker fetch. If you ever see "HTTP 451" or "HTTP 403" errors
in the Action logs, this is why — it's expected and the fallback should catch it.

### Push notifications

FCM v1 API (not the deprecated legacy HTTP API). Requires a Firebase **service
account JSON** (not a server key — Firebase removed server keys for new projects).

- Local dev: `FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json` in `.env`
  (this file is gitignored — never commit it, contains a private key)
- GitHub Actions: `FIREBASE_SERVICE_ACCOUNT_JSON` secret (full JSON as one string),
  written to a temp file by the workflow before the Python script runs
- `check_signals` sends a push when SL or TP is hit (win/loss), reading enabled
  device tokens from the `notification_tokens` Supabase table
- Flutter app registers its FCM token to that table on startup via
  `push_notification_service.dart`

---

## Backend — check_signals (hourly resolver)

File: `backend/check_signals/handler.py`

- Runs hourly, **skips 2am-6am IST** (UTC 19:30-23:30) — no need to check overnight
- Walks 1h candles from signal creation time, checks SL/TP breach in chronological
  order (SL checked before TP in the same candle — conservative assumption)
- Updates `latest_price` on the signal row every run, even while still pending —
  this powers the "live P&L" display in the Flutter app and dashboard
- 90-day TTL cleanup: deletes signals older than 90 days (also mirrored by a
  Supabase `pg_cron` job as a belt-and-suspenders backup)
- Exits immediately (~2s) if there are zero pending signals — saves Action minutes

---

## GitHub Actions schedule

| Workflow | Cron | Notes |
|---|---|---|
| `generate_signals` | every 4h (`0 */4 * * *`) | Matches candle timeframe; early-exits if daily cap already met |
| `check_signals` | hourly, `30 0-18 * * *` | Runs 6am-midnight IST, skips 1am-5am IST; offset :30 so it never overlaps generate_signals |

Repo is **private** — GitHub Free gives 2,000 min/month. Both workflows are
designed to exit in seconds when there's nothing to do, so actual usage is well
under budget even at these frequencies.

---

## Flutter app (`app/`)

- Package name: `com.trade.signals` (was `com.example.trade_pilot` — if you ever
  see build errors referencing the old package, check `MainActivity.kt` is at the
  right path: `android/app/src/main/kotlin/com/trade/signals/MainActivity.kt`)
- **No login/auth required** — `main.dart` routes straight to `MainShell()`.
  Auth screens (`login_screen.dart`, `register_screen.dart`) still exist in the
  codebase for future use but aren't in the active navigation flow.
- 3 screens: Home, Signals list, Profile — bottom nav
- Profile shows "Free Plan" / "Free Access · MVP" — there is no paid tier yet,
  don't add subscription UI unless explicitly asked
- Theme: `ThemeMode.system` — respects OS light/dark automatically via
  `AppColors` (light/dark variants) + `context.colors` extension pattern
- Supabase client reads signals directly (anon key + RLS policies — see below)
- `SupabaseService._guard()` wraps all calls, maps exceptions to typed
  `AppError` subclasses (`NetworkError`, `AuthError`, `ServerError`, `DataError`)
  for consistent error UI via `ErrorView`/`EmptyView` widgets

### Known constraint: emulator issues on this machine

The user's Android emulators (`Pixel_10_Pro`, `Pixel_6a`) have had repeated boot
failures — the `google_apis_playstore_ps16k` system image (16K page size) is
incompatible with this Windows/HAXM setup and hangs indefinitely at boot.
**Do not spend time debugging the emulator further** — the established working
path is to build a debug/release APK and either:
1. `flutter run -d <device-id>` with the physical Samsung S23 FE (`RZCX917PGGV`)
   connected via USB, or
2. Build APK and manually transfer/install via file copy if USB debugging drops

---

## Dashboard (`dashboard/`)

Next.js 16 (Turbopack), Tailwind, deployed... (currently local dev only, no
production deploy configured yet as of this writing).

- **Next.js 16 renamed `middleware.ts` → `proxy.ts`**, and the exported function
  must be named `proxy` not `middleware`. Both old and new file can't coexist —
  Next.js throws if it finds both. If you see "Both middleware file and proxy
  file are detected" — delete `middleware.ts`, keep only `proxy.ts`.
- Admin gate: `src/lib/admin.ts` checks `NEXT_PUBLIC_ADMIN_EMAILS` (comma-separated
  env var) against the logged-in Supabase Auth user's email. No match = 403 view.
  This is the ONLY access control on `/analytics` — the dashboard itself
  (`/`, `/signals`) requires Supabase Auth login via `proxy.ts`, but analytics
  additionally requires being in the admin allowlist.
- **`/analytics` page** — uses `recharts` (donut charts, bar charts, area chart).
  Includes an **interactive P&L simulator** (adjustable trade size/risk%/target%)
  and an **indicator precision chart** that reads `votes_json` per signal to show
  which indicators historically predicted wins vs losses.
- **Dashboard home (`/`)** has a fixed "$1,000/trade performance" card using the
  algorithm's actual 3.5%/2% TP/SL assumptions (not user-adjustable, unlike the
  analytics page simulator which lets you change all three inputs).
- Charts must guard against SSR hydration mismatches — recharts needs
  `ResponsiveContainer` to only render after `mounted` state is true (a
  `useEffect(() => setMounted(true), [])` pattern), otherwise charts render
  blank on first paint.

---

## Supabase schema (tables referenced across the codebase)

- `trade_signals` — the core table. Columns include: id, pair, direction,
  entry, stop_loss, take_profit, confidence (= signal strength), rr_ratio,
  timestamp, expires_at, result (pending/win/loss/expired), close_price,
  latest_price, votes_json (compact `{indicator: vote}` dict, no reason
  strings — kept small deliberately, ~120 bytes/signal not ~1KB)
- `market_sentiment` — daily rollup (bullish/neutral/bearish %, F&G value,
  active long/short counts) written once per `generate_signals` run
- `notification_tokens` — FCM device tokens, `is_enabled` boolean per device

RLS policies must allow: anon SELECT on `trade_signals` (Flutter app reads
without auth), anon INSERT/UPDATE on `notification_tokens` (app registers its
own token), authenticated-only INSERT/UPDATE/DELETE on `trade_signals` (dashboard
admin CRUD via `SignalForm.tsx`).

---

## Things NOT to reintroduce (already tried, rejected, or fixed)

- Don't add a paid subscription tier to the Flutter app — explicitly free MVP
- Don't sum trend-following and mean-reversion indicator votes flat — that was
  the core bug; always route new indicators through the regime-aware pattern
- Don't use candle close as signal entry price — use `get_live_price()`
- Don't set expiry beyond 4 days or below 3 — deliberately tightened range
- Don't re-add `middleware.ts` alongside `proxy.ts` in the dashboard
- Don't use Binance/Bybit as the only candle source — always keep the OKX
  fallback, GitHub Actions runners get geo-blocked otherwise
- Don't store `votes_json` with full reason strings — compact `{name: vote}`
  format only, storage cost was the reason for the original refactor
- Don't spend cycles debugging the local Android emulator — use physical device
  or APK install instead
