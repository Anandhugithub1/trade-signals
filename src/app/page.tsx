'use client'
import { useEffect, useState } from 'react'
import { supabase, isConfigured } from '@/lib/supabase'
import type { TradeSignal } from '@/types/signal'

function computeStats(signals: TradeSignal[]) {
  const wins = signals.filter((s) => s.result === 'win').length
  const losses = signals.filter((s) => s.result === 'loss').length
  const pending = signals.filter((s) => s.result === 'pending').length
  const closed = wins + losses
  const winRate = closed ? (wins / closed) * 100 : 0
  const avgConf = signals.length
    ? signals.reduce((a, s) => a + s.confidence, 0) / signals.length
    : 0
  return { total: signals.length, wins, losses, pending, winRate, avgConf }
}

function pairStats(signals: TradeSignal[]) {
  const map: Record<string, { wins: number; losses: number; pending: number }> = {}
  signals.forEach((s) => {
    if (!map[s.pair]) map[s.pair] = { wins: 0, losses: 0, pending: 0 }
    if (s.result === 'win') map[s.pair].wins++
    else if (s.result === 'loss') map[s.pair].losses++
    else map[s.pair].pending++
  })
  return Object.entries(map)
    .map(([pair, v]) => ({ pair, ...v, total: v.wins + v.losses + v.pending }))
    .sort((a, b) => b.total - a.total)
}

export default function DashboardPage() {
  const [signals, setSignals] = useState<TradeSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isConfigured) {
      setLoading(false)
      return
    }
    async function load() {
      const { data, error } = await supabase
        .from('trade_signals')
        .select('*')
        .order('timestamp', { ascending: false })
      if (error) setError(error.message)
      else setSignals(data ?? [])
      setLoading(false)
    }
    load()
  }, [])

  if (!isConfigured) {
    return (
      <div className="p-8">
        <SetupBanner />
      </div>
    )
  }

  const stats = computeStats(signals)
  const pairs = pairStats(signals)
  const recent = signals.slice(0, 8)

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Dashboard</h1>
        <p className="text-[#64748b] text-sm mt-1">Trade signal analytics overview</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard label="Total Signals" value={stats.total} loading={loading} />
        <StatCard
          label="Win Rate"
          value={`${stats.winRate.toFixed(1)}%`}
          loading={loading}
          color={stats.winRate >= 60 ? 'green' : stats.winRate >= 40 ? 'amber' : 'red'}
        />
        <StatCard label="Wins" value={stats.wins} loading={loading} color="green" />
        <StatCard label="Losses" value={stats.losses} loading={loading} color="red" />
        <StatCard label="Pending" value={stats.pending} loading={loading} color="amber" />
        <StatCard label="Avg Confidence" value={`${stats.avgConf.toFixed(0)}%`} loading={loading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pair breakdown */}
        <div className="bg-[#1a1a24] rounded-xl border border-[#2a2a3a] p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Performance by Pair</h2>
          {loading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-8 bg-[#2a2a3a] rounded animate-pulse" />
              ))}
            </div>
          ) : pairs.length === 0 ? (
            <p className="text-[#475569] text-sm py-4">No data yet — add signals to see breakdown.</p>
          ) : (
            <div className="space-y-4">
              {pairs.map((p) => {
                const closed = p.wins + p.losses
                const wr = closed ? (p.wins / closed) * 100 : 0
                return (
                  <div key={p.pair}>
                    <div className="flex justify-between text-xs mb-1.5">
                      <span className="font-semibold text-white">{p.pair}</span>
                      <span className="text-[#64748b]">
                        <span className="text-[#22c55e]">{p.wins}W</span>
                        {' / '}
                        <span className="text-[#ef4444]">{p.losses}L</span>
                        {p.pending > 0 && (
                          <span className="text-amber-400"> / {p.pending} open</span>
                        )}
                      </span>
                    </div>
                    <div className="h-2 bg-[#2a2a3a] rounded-full overflow-hidden flex">
                      {closed > 0 ? (
                        <>
                          <div className="h-full bg-[#22c55e]" style={{ width: `${wr}%` }} />
                          <div className="h-full bg-[#ef4444]" style={{ width: `${100 - wr}%` }} />
                        </>
                      ) : (
                        <div className="h-full w-full bg-amber-500/30" />
                      )}
                    </div>
                    <p className="text-[10px] text-[#475569] mt-1">
                      {closed > 0
                        ? `${wr.toFixed(0)}% win rate · ${p.total} total`
                        : 'All pending'}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Recent signals */}
        <div className="bg-[#1a1a24] rounded-xl border border-[#2a2a3a] p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Recent Signals</h2>
          {loading ? (
            <div className="space-y-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-10 bg-[#2a2a3a] rounded animate-pulse" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <p className="text-[#475569] text-sm py-4">No signals yet.</p>
          ) : (
            <div className="divide-y divide-[#2a2a3a]">
              {recent.map((s) => (
                <div key={s.id} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                        s.direction === 'long'
                          ? 'bg-[#22c55e]/10 text-[#22c55e]'
                          : 'bg-[#ef4444]/10 text-[#ef4444]'
                      }`}
                    >
                      {s.direction}
                    </span>
                    <span className="text-sm font-semibold text-white">{s.pair}</span>
                    <span className="text-xs text-[#475569] font-mono">
                      ${s.entry.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] text-[#475569]">
                      {new Date(s.timestamp).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                    <ResultBadge result={s.result} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({
  label,
  value,
  loading,
  color,
}: {
  label: string
  value: string | number
  loading: boolean
  color?: 'green' | 'red' | 'amber'
}) {
  const colorClass =
    color === 'green'
      ? 'text-[#22c55e]'
      : color === 'red'
        ? 'text-[#ef4444]'
        : color === 'amber'
          ? 'text-amber-400'
          : 'text-white'
  return (
    <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl p-4">
      <p className="text-[10px] text-[#475569] uppercase tracking-widest font-semibold">{label}</p>
      {loading ? (
        <div className="h-7 w-14 bg-[#2a2a3a] rounded animate-pulse mt-2" />
      ) : (
        <p className={`text-2xl font-bold mt-1.5 ${colorClass}`}>{value}</p>
      )}
    </div>
  )
}

function ResultBadge({ result }: { result: string }) {
  const styles: Record<string, string> = {
    win: 'bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/20',
    loss: 'bg-[#ef4444]/10 text-[#ef4444] border-[#ef4444]/20',
    pending: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  }
  return (
    <span
      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${styles[result] ?? styles.pending}`}
    >
      {result}
    </span>
  )
}

function SetupBanner() {
  return (
    <div className="max-w-md mx-auto mt-20 bg-[#1a1a24] border border-[#2a2a3a] rounded-2xl p-8 text-center">
      <div className="w-12 h-12 bg-[#6366f1]/10 rounded-xl flex items-center justify-center mx-auto mb-4">
        <svg className="w-6 h-6 text-[#6366f1]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
          />
        </svg>
      </div>
      <h2 className="text-lg font-bold text-white mb-2">Supabase Not Configured</h2>
      <p className="text-[#64748b] text-sm mb-5">
        Add your Supabase credentials to{' '}
        <code className="text-[#818cf8] bg-[#2a2a3a] px-1.5 py-0.5 rounded text-xs">.env.local</code>{' '}
        to get started.
      </p>
      <div className="bg-[#0f0f13] rounded-lg p-4 text-left font-mono text-xs text-[#94a3b8] space-y-1.5">
        <p className="text-[#475569]"># .env.local</p>
        <p>NEXT_PUBLIC_SUPABASE_URL=<span className="text-amber-400">https://xxx.supabase.co</span></p>
        <p>NEXT_PUBLIC_SUPABASE_ANON_KEY=<span className="text-amber-400">eyJ...</span></p>
      </div>
    </div>
  )
}
