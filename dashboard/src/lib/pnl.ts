import type { TradeSignal } from '@/types/signal'

/**
 * Realized P&L, computed from what each trade ACTUALLY did (entry → close
 * price), never from an assumed TP/SL %. The two live engines have very
 * different profit:loss shapes — donchian targets 3R, mean_reversion ~1R —
 * and every signal sets its own stop distance, so any single fixed % (the
 * old "+3.5% win / −2% loss") is wrong for both. Same formula the backend's
 * monthly_summary uses for crypto.
 */

export const TRADE_SIZE = 1000 // illustrative position size, $ per trade

export const ENGINES = [
  { key: 'donchian', label: 'Donchian', color: '#22c55e' },
  { key: 'mean_reversion', label: 'Mean Reversion', color: '#6366f1' },
] as const

/**
 * Signed % move from entry to exit. null when there was no position
 * (limit entry never filled), the trade is still open, or it closed
 * without a recorded exit price.
 */
export function tradePnlPct(x: TradeSignal): number | null {
  if (x.result === 'pending') return null
  if (x.entry_confirmed === false) return null
  if (x.close_price == null || !x.entry) return null
  const move = ((x.close_price - x.entry) / x.entry) * 100
  return x.direction === 'short' ? -move : move
}

/** The trade's result in R: % move ÷ its own stop distance. */
export function tradeR(x: TradeSignal): number | null {
  const pct = tradePnlPct(x)
  if (pct == null) return null
  const riskPct = (Math.abs(x.entry - x.stop_loss) / x.entry) * 100
  return riskPct ? pct / riskPct : null
}

export interface PnlSummary {
  trades: number        // closed trades with a real P&L
  wins: number
  losses: number
  winRate: number       // %
  netPct: number        // sum of per-trade % moves
  netUsd: number        // at TRADE_SIZE per trade
  grossProfitUsd: number
  grossLossUsd: number
  totalR: number
  avgWinPct: number
  avgLossPct: number    // negative
  profitLossRatio: number | null   // avg win ÷ avg loss (realized)
  plannedRR: number | null         // avg planned reward:risk (1:x)
  pf: number | null                // gross profit ÷ gross loss
  pending: number
  unpriced: number      // closed/expired rows we can't price (no fill or no exit)
}

export function summarize(signals: TradeSignal[]): PnlSummary {
  const priced = signals
    .map(x => ({ x, pct: tradePnlPct(x), r: tradeR(x) }))
    .filter((t): t is { x: TradeSignal; pct: number; r: number | null } => t.pct != null)

  const winPcts = priced.filter(t => t.pct > 0).map(t => t.pct)
  const lossPcts = priced.filter(t => t.pct <= 0).map(t => t.pct)
  const sum = (a: number[]) => a.reduce((s, v) => s + v, 0)
  const avg = (a: number[]) => (a.length ? sum(a) / a.length : 0)

  const grossProfitPct = sum(winPcts)
  const grossLossPct = -sum(lossPcts)
  const rrs = signals.map(x => x.rr_ratio).filter((v): v is number => typeof v === 'number' && v > 0)

  return {
    trades: priced.length,
    wins: winPcts.length,
    losses: lossPcts.length,
    winRate: priced.length ? (winPcts.length / priced.length) * 100 : 0,
    netPct: grossProfitPct - grossLossPct,
    netUsd: ((grossProfitPct - grossLossPct) / 100) * TRADE_SIZE,
    grossProfitUsd: (grossProfitPct / 100) * TRADE_SIZE,
    grossLossUsd: (grossLossPct / 100) * TRADE_SIZE,
    totalR: sum(priced.map(t => t.r ?? 0)),
    avgWinPct: avg(winPcts),
    avgLossPct: avg(lossPcts),
    profitLossRatio: winPcts.length && lossPcts.length ? avg(winPcts) / Math.abs(avg(lossPcts)) : null,
    plannedRR: rrs.length ? avg(rrs) : null,
    pf: grossLossPct > 0 ? grossProfitPct / grossLossPct : (grossProfitPct > 0 ? Infinity : null),
    pending: signals.filter(x => x.result === 'pending').length,
    unpriced: signals.filter(x => x.result !== 'pending' && x.entry_confirmed !== false && tradePnlPct(x) == null).length,
  }
}

export const fmtUsd = (v: number) => `${v >= 0 ? '+' : '−'}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
export const fmtPct = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`
export const fmtR = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}R`
export const fmtRatio = (v: number | null) => (v == null ? '—' : `1 : ${v.toFixed(2)}`)
export const fmtPf = (v: number | null) => (v == null ? '—' : v === Infinity ? '∞' : v.toFixed(2))
