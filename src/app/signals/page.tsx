'use client'
import { useEffect, useState } from 'react'
import { supabase, isConfigured } from '@/lib/supabase'
import type { TradeSignal } from '@/types/signal'
import { friendlyError } from '@/components/Toast'

type DirFilter = 'all' | 'long' | 'short'
type ResFilter = 'all' | 'pending' | 'win' | 'loss' | 'expired'

export default function SignalsPage() {
  const [signals, setSignals] = useState<TradeSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dirFilter, setDirFilter] = useState<DirFilter>('all')
  const [resFilter, setResFilter] = useState<ResFilter>('all')
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!isConfigured) { setLoading(false); return }
    load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const { data, error } = await supabase
        .from('trade_signals')
        .select('*')
        .order('timestamp', { ascending: false })
      if (error) throw error
      setSignals(data ?? [])
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }

  const filtered = signals.filter((s) => {
    const matchSearch = search === '' || s.pair.toLowerCase().includes(search.toLowerCase())
    const matchDir = dirFilter === 'all' || s.direction === dirFilter
    const matchRes = resFilter === 'all' || s.result === resFilter
    return matchSearch && matchDir && matchRes
  })

  if (!isConfigured) {
    return (
      <div className="p-8">
        <div className="max-w-md bg-[#1a1a24] border border-[#2a2a3a] rounded-xl p-6 text-sm text-[#64748b]">
          Configure Supabase credentials in{' '}
          <code className="text-[#818cf8] bg-[#2a2a3a] px-1.5 py-0.5 rounded text-xs">.env.local</code>{' '}
          to manage signals.
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Signals</h1>
          <p className="text-[#64748b] text-sm mt-1">
            {loading ? 'Loading…' : `${signals.length} total · ${filtered.length} shown`}
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm mb-5 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400/60 hover:text-red-400 ml-4">✕</button>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-[#475569]" width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <circle cx="11" cy="11" r="8" /><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search pair…"
            className="bg-[#1a1a24] border border-[#2a2a3a] rounded-lg pl-8 pr-3 py-2 text-sm text-white placeholder-[#475569] focus:border-[#6366f1] focus:outline-none w-44 transition-colors"
          />
        </div>

        <div className="flex gap-1">
          {(['all', 'long', 'short'] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDirFilter(d)}
              className={`px-3 py-2 text-xs font-semibold rounded-lg capitalize transition-colors ${
                dirFilter === d
                  ? 'bg-[#6366f1]/20 text-[#818cf8] border border-[#6366f1]/30'
                  : 'bg-[#1a1a24] text-[#64748b] border border-[#2a2a3a] hover:text-white'
              }`}
            >
              {d === 'all' ? 'All dirs' : d}
            </button>
          ))}
        </div>

        <div className="flex gap-1">
          {(['all', 'pending', 'win', 'loss', 'expired'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setResFilter(r)}
              className={`px-3 py-2 text-xs font-semibold rounded-lg capitalize transition-colors ${
                resFilter === r
                  ? 'bg-[#6366f1]/20 text-[#818cf8] border border-[#6366f1]/30'
                  : 'bg-[#1a1a24] text-[#64748b] border border-[#2a2a3a] hover:text-white'
              }`}
            >
              {r === 'all' ? 'All results' : r}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2a3a]">
                {['Pair', 'Direction', 'Entry', 'Last Price', 'SL / TP', 'Strength', 'Date', 'Result', 'Note'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-semibold text-[#475569]"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-[#2a2a3a]/40">
                    {[...Array(9)].map((_, j) => (
                      <td key={j} className="px-4 py-3.5">
                        <div className="h-3.5 bg-[#2a2a3a] rounded animate-pulse" style={{ width: `${40 + j * 10}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-16 text-center">
                    <p className="text-[#475569] text-sm">
                      {signals.length === 0
                        ? 'No signals yet. They are generated automatically by the backend.'
                        : 'No signals match your filters.'}
                    </p>
                  </td>
                </tr>
              ) : (
                filtered.map((s) => (
                  <tr
                    key={s.id}
                    className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e] transition-colors"
                  >
                    <td className="px-4 py-3.5 font-bold text-white">{s.pair}</td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider border ${
                          s.direction === 'long'
                            ? 'bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/20'
                            : 'bg-[#ef4444]/10 text-[#ef4444] border-[#ef4444]/20'
                        }`}
                      >
                        {s.direction === 'long' ? '▲ Long' : '▼ Short'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs text-white">
                      ${s.entry.toLocaleString()}
                    </td>
                    <td className="px-4 py-3.5">
                      {s.latest_price != null ? (() => {
                        const lp   = s.latest_price!
                        const pnl  = s.result === 'pending'
                          ? ((s.direction === 'long' ? lp - s.entry : s.entry - lp) / s.entry) * 100
                          : null
                        const isUp = (pnl ?? 0) >= 0
                        const priceColor = pnl === null
                          ? 'text-[#64748b]'
                          : isUp ? 'text-[#22c55e]' : 'text-[#ef4444]'
                        return (
                          <div className="flex flex-col gap-0.5">
                            <span className={`font-mono text-xs font-bold ${priceColor}`}>
                              ${lp.toLocaleString()}
                            </span>
                            {pnl !== null && (
                              <span className={`text-[10px] font-semibold ${priceColor}`}>
                                {isUp ? '+' : ''}{pnl.toFixed(2)}%
                              </span>
                            )}
                          </div>
                        )
                      })() : (
                        <span className="text-[#334155] text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="font-mono text-xs leading-relaxed">
                        <span className="text-[#ef4444]">${s.stop_loss.toLocaleString()}</span>
                        <span className="text-[#475569] mx-1">/</span>
                        <span className="text-[#22c55e]">${s.take_profit.toLocaleString()}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1.5 bg-[#2a2a3a] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[#6366f1] rounded-full"
                            style={{ width: `${s.confidence}%` }}
                          />
                        </div>
                        <span className="text-xs text-[#94a3b8]">{s.confidence}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-[#64748b] text-xs whitespace-nowrap">
                      {new Date(s.timestamp).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: '2-digit',
                      })}
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded border ${
                          s.result === 'win'
                            ? 'bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/20'
                            : s.result === 'loss'
                              ? 'bg-[#ef4444]/10 text-[#ef4444] border-[#ef4444]/20'
                              : s.result === 'expired'
                                ? 'bg-[#64748b]/10 text-[#64748b] border-[#64748b]/20'
                                : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        }`}
                      >
                        {s.result}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 max-w-[220px]">
                      {s.note ? (
                        <p
                          title={s.note}
                          className="text-xs text-[#94a3b8] leading-snug line-clamp-2 cursor-help"
                        >
                          {s.note}
                        </p>
                      ) : (
                        <span className="text-[#334155] text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
