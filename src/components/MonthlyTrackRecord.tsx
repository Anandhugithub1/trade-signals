'use client'
import { useEffect, useState, memo } from 'react'
import { supabase, isConfigured } from '@/lib/supabase'

/**
 * Permanent month-by-month track record, read from `monthly_summary`.
 *
 * The signals tables have a 90-day TTL, so raw trades are deleted and any
 * history older than that is gone. This table is the durable record — one
 * tiny row per (month, market), written daily by backend/monthly_summary.
 */

export interface MonthlyRow {
  month: string           // 'YYYY-MM-01'
  market: 'crypto' | 'crypto_options' | 'stocks'
  trades: number
  wins: number
  losses: number
  expired: number
  win_rate: number | null
  pnl: number
  pnl_unit: 'pct' | 'usd'
  best: number | null
  worst: number | null
}

const MARKETS = {
  crypto:         { label: 'Crypto',  color: '#f59e0b' },
  crypto_options: { label: 'Options', color: '#818cf8' },
  stocks:         { label: 'Stocks',  color: '#22c55e' },
} as const

const monthLabel = (m: string) =>
  new Date(m + 'T00:00:00Z').toLocaleDateString('en-US',
    { month: 'short', year: 'numeric', timeZone: 'UTC' })

/** P&L is percent for crypto/stocks and USD for crypto options — never mix them. */
const fmtPnl = (v: number, unit: 'pct' | 'usd') => {
  const sign = v >= 0 ? '+' : '−'
  const n = Math.abs(v)
  return unit === 'usd'
    ? `${sign}$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
    : `${sign}${n.toFixed(1)}%`
}

const winColor = (v: number | null) =>
  v === null ? '#8b949e' : v >= 60 ? '#22c55e' : v >= 40 ? '#f59e0b' : '#ef4444'

const MonthlyTrackRecord = memo(function MonthlyTrackRecord() {
  const [rows, setRows] = useState<MonthlyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    if (!isConfigured) { setLoading(false); return }
    supabase
      .from('monthly_summary')
      .select('*')
      .order('month', { ascending: false })
      .then(({ data, error }) => {
        // The table may not exist yet (schema not applied) — say so plainly
        // rather than rendering an empty state that looks like "no trades".
        if (error) setMissing(true)
        else setRows((data ?? []) as MonthlyRow[])
        setLoading(false)
      })
  }, [])

  if (loading) {
    return <div className="animate-pulse bg-[#21262d] rounded-xl" style={{ height: 220 }} />
  }

  if (missing) {
    return (
      <p className="text-[13px] text-[#8b949e] py-8 text-center">
        <code className="text-[#c9d1d9]">monthly_summary</code> table not found —
        run <code className="text-[#c9d1d9]">backend/monthly_summary/schema.sql</code> in
        the Supabase SQL editor.
      </p>
    )
  }

  if (!rows.length) {
    return (
      <p className="text-[13px] text-[#8b949e] py-8 text-center">
        No completed months yet. Summaries appear once trades close.
      </p>
    )
  }

  // Group by month, newest first, so each row shows every market side by side.
  const months = [...new Set(rows.map(r => r.month))]
  const byMonth = months.map(m => ({
    month: m,
    markets: rows.filter(r => r.month === m),
  }))

  return (
    <div className="space-y-4">
      {byMonth.map(({ month, markets }) => (
        <div key={month}>
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-[13px] font-semibold text-white">
              {monthLabel(month)}
            </h3>
            <span className="text-[11px] text-[#8b949e]">
              {markets.reduce((s, m) => s + m.trades, 0)} trades
            </span>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            {(Object.keys(MARKETS) as Array<keyof typeof MARKETS>).map(key => {
              const r = markets.find(m => m.market === key)
              const meta = MARKETS[key]
              return (
                <div
                  key={key}
                  className="bg-[#0d1117] border border-[#21262d] rounded-xl px-3.5 py-3"
                >
                  <div className="flex items-center gap-1.5 mb-2">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: meta.color }}
                    />
                    <span className="text-[11px] font-medium text-[#8b949e]">
                      {meta.label}
                    </span>
                  </div>

                  {!r || r.trades === 0 ? (
                    <p className="text-[13px] text-[#484f58]">No trades</p>
                  ) : (
                    <>
                      <p
                        className="text-lg font-bold tracking-tight leading-none"
                        style={{ color: r.pnl >= 0 ? '#22c55e' : '#ef4444' }}
                      >
                        {fmtPnl(r.pnl, r.pnl_unit)}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5 text-[11px]">
                        <span style={{ color: winColor(r.win_rate) }}>
                          {r.win_rate === null ? '—' : `${r.win_rate}%`} win
                        </span>
                        <span className="text-[#484f58]">·</span>
                        <span className="text-[#8b949e]">
                          {r.wins}W / {r.losses}L
                          {r.expired > 0 && ` · ${r.expired} exp`}
                        </span>
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <p className="text-[11px] text-[#8b949e] pt-1">
        P&amp;L is the sum of per-trade returns (% for crypto and stocks,
        USD for crypto options) — not a compounded account return. Kept
        permanently; raw signals are deleted after 90 days.
      </p>
    </div>
  )
})

export default MonthlyTrackRecord
