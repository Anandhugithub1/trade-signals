'use client'
import { useEffect, useState } from 'react'
import { supabase, isConfigured } from '@/lib/supabase'
import type { TradeSignal } from '@/types/signal'
import SignalForm from '@/components/SignalForm'
import { useToast, friendlyError } from '@/components/Toast'

type DirFilter = 'all' | 'long' | 'short'
type ResFilter = 'all' | 'pending' | 'win' | 'loss' | 'expired'

export default function SignalsPage() {
  const [signals, setSignals] = useState<TradeSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<TradeSignal | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [dirFilter, setDirFilter] = useState<DirFilter>('all')
  const [resFilter, setResFilter] = useState<ResFilter>('all')
  const [search, setSearch] = useState('')
  const { error: toastError, success: toastSuccess } = useToast()

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

  async function handleSave(data: Omit<TradeSignal, 'id'> & { id?: string }) {
    try {
      if (data.id) {
        const { error } = await supabase.from('trade_signals').update(data).eq('id', data.id)
        if (error) throw error
        toastSuccess('Signal updated successfully.')
      } else {
        const { error } = await supabase
          .from('trade_signals')
          .insert({ ...data, id: crypto.randomUUID() })
        if (error) throw error
        toastSuccess('Signal created successfully.')
      }
      setFormOpen(false)
      setEditTarget(null)
      await load()
    } catch (err) {
      throw new Error(friendlyError(err))
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this signal? This cannot be undone.')) return
    setDeleting(id)
    try {
      const { error } = await supabase.from('trade_signals').delete().eq('id', id)
      if (error) throw error
      setSignals((prev) => prev.filter((s) => s.id !== id))
      toastSuccess('Signal deleted.')
    } catch (err) {
      toastError(friendlyError(err))
    } finally {
      setDeleting(null)
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
        <button
          onClick={() => { setEditTarget(null); setFormOpen(true) }}
          className="flex items-center gap-2 bg-[#6366f1] hover:bg-[#4f46e5] text-white text-sm font-bold px-4 py-2.5 rounded-lg transition-colors"
        >
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
          </svg>
          New Signal
        </button>
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
                {['Pair', 'Direction', 'Entry', 'Last Price', 'SL / TP', 'Confidence', 'Date', 'Result', 'Actions'].map(
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
                        ? 'No signals yet. Click "New Signal" to create your first one.'
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
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => { setEditTarget(s); setFormOpen(true) }}
                          title="Edit"
                          className="text-[#475569] hover:text-[#818cf8] transition-colors"
                        >
                          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDelete(s.id)}
                          disabled={deleting === s.id}
                          title="Delete"
                          className="text-[#475569] hover:text-[#ef4444] transition-colors disabled:opacity-40"
                        >
                          {deleting === s.id ? (
                            <svg className="animate-spin" width="14" height="14" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {formOpen && (
        <SignalForm
          signal={editTarget}
          onClose={() => { setFormOpen(false); setEditTarget(null) }}
          onSave={handleSave}
        />
      )}
    </div>
  )
}
