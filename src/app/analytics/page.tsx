'use client'
import { useEffect, useState } from 'react'
import { supabase, isConfigured } from '@/lib/supabase'
import { isAdmin } from '@/lib/admin'
import { createClient } from '@/lib/supabase'
import type { TradeSignal, SignalVote } from '@/types/signal'

// ── types ─────────────────────────────────────────────────────────────────────
interface MarketSentiment {
  id: string
  date: string
  bullish_pct: number
  neutral_pct: number
  bearish_pct: number
  fear_greed_value: number | null
  fear_greed_label: string | null
  active_longs: number
  active_shorts: number
  dominant: string
}

// ── helpers ───────────────────────────────────────────────────────────────────
function rrBucket(rr: number | null): string {
  if (!rr) return 'N/A'
  if (rr < 1.5) return '1:1 – 1.5'
  if (rr < 2.0) return '1:1.5 – 2'
  if (rr < 3.0) return '1:2 – 3'
  return '1:3+'
}
function confBucket(c: number): string {
  if (c < 70) return '60-70%'
  if (c < 80) return '70-80%'
  if (c < 90) return '80-90%'
  return '90%+'
}
function winRate(wins: number, total: number) {
  return total ? Math.round((wins / total) * 100) : 0
}

// ── main page ─────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const [user, setUser]           = useState<{ email?: string } | null>(null)
  const [signals, setSignals]     = useState<TradeSignal[]>([])
  const [sentiment, setSentiment] = useState<MarketSentiment[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)

  useEffect(() => {
    const client = createClient()
    client.auth.getUser().then(({ data }) => setUser(data.user))
  }, [])

  useEffect(() => {
    if (!isConfigured || user === null) return
    if (!isAdmin(user?.email)) { setLoading(false); return }

    async function load() {
      const [sigRes, sentRes] = await Promise.all([
        supabase.from('trade_signals').select('*').order('timestamp', { ascending: false }),
        supabase.from('market_sentiment').select('*').order('date', { ascending: false }).limit(14),
      ])
      if (sigRes.error)  setError(sigRes.error.message)
      else               setSignals(sigRes.data ?? [])
      if (!sentRes.error) setSentiment(sentRes.data ?? [])
      setLoading(false)
    }
    load()
  }, [user])

  // Waiting for user to load
  if (user === null) return <LoadingState />

  // Access denied
  if (!isAdmin(user?.email)) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="text-center max-w-sm">
          <div className="w-14 h-14 bg-red-500/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-white mb-2">Admin Access Required</h2>
          <p className="text-[#64748b] text-sm">
            Analytics is restricted to admin accounts. Set{' '}
            <code className="text-[#818cf8] bg-[#2a2a3a] px-1.5 py-0.5 rounded text-xs">NEXT_PUBLIC_ADMIN_EMAILS</code>{' '}
            in your <code className="text-[#818cf8] bg-[#2a2a3a] px-1.5 py-0.5 rounded text-xs">.env.local</code>.
          </p>
        </div>
      </div>
    )
  }

  if (loading) return <LoadingState />

  const closed   = signals.filter((s) => s.result === 'win' || s.result === 'loss')
  const wins     = closed.filter((s) => s.result === 'win')
  const losses   = closed.filter((s) => s.result === 'loss')
  const pending  = signals.filter((s) => s.result === 'pending')
  const longs    = signals.filter((s) => s.direction === 'long')
  const shorts   = signals.filter((s) => s.direction === 'short')
  const longWins = longs.filter((s) => s.result === 'win')
  const shortWins = shorts.filter((s) => s.result === 'win')
  const avgConf  = signals.length ? Math.round(signals.reduce((a, s) => a + s.confidence, 0) / signals.length) : 0
  const avgRR    = closed.length
    ? (closed.reduce((a, s) => a + (s.rr_ratio ?? 0), 0) / closed.length).toFixed(2)
    : ('—' as string)
  const wr       = winRate(wins.length, closed.length)

  // Confidence buckets
  const confBuckets = ['60-70%', '70-80%', '80-90%', '90%+']
  const confData = confBuckets.map((b) => {
    const inBucket = closed.filter((s) => confBucket(s.confidence) === b)
    const bWins = inBucket.filter((s) => s.result === 'win')
    return { label: b, total: inBucket.length, wins: bWins.length, wr: winRate(bWins.length, inBucket.length) }
  })

  // RR buckets
  const rrBuckets = ['1:1 – 1.5', '1:1.5 – 2', '1:2 – 3', '1:3+']
  const rrData = rrBuckets.map((b) => {
    const inBucket = closed.filter((s) => rrBucket(s.rr_ratio ?? null) === b)
    const bWins = inBucket.filter((s) => s.result === 'win')
    return { label: b, total: inBucket.length, wins: bWins.length, wr: winRate(bWins.length, inBucket.length) }
  })

  // Indicator hit rate (from votes_json)
  const indicatorMap: Record<string, { winFires: number; lossFires: number; total: number }> = {}
  closed.forEach((s) => {
    if (!s.votes_json) return
    s.votes_json.forEach((v: SignalVote) => {
      if (v.vote === 0) return
      if (!indicatorMap[v.name]) indicatorMap[v.name] = { winFires: 0, lossFires: 0, total: 0 }
      indicatorMap[v.name].total++
      if (s.result === 'win') indicatorMap[v.name].winFires++
      else indicatorMap[v.name].lossFires++
    })
  })
  const indicators = Object.entries(indicatorMap)
    .map(([name, d]) => ({ name, ...d, wr: winRate(d.winFires, d.total) }))
    .sort((a, b) => b.total - a.total)

  // Pair stats
  const pairMap: Record<string, { wins: number; losses: number; pending: number }> = {}
  signals.forEach((s) => {
    if (!pairMap[s.pair]) pairMap[s.pair] = { wins: 0, losses: 0, pending: 0 }
    if (s.result === 'win')     pairMap[s.pair].wins++
    else if (s.result === 'loss') pairMap[s.pair].losses++
    else                          pairMap[s.pair].pending++
  })
  const pairs = Object.entries(pairMap)
    .map(([pair, d]) => ({ pair, ...d, total: d.wins + d.losses + d.pending, closed: d.wins + d.losses }))
    .sort((a, b) => b.total - a.total)

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Analytics</h1>
          <p className="text-[#64748b] text-sm mt-1">
            Deep signal intelligence — {signals.length} signals analysed
            <span className="ml-2 text-[#6366f1] font-medium">Admin only</span>
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Overview cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
        {[
          { label: 'Total',      value: signals.length,         color: '' },
          { label: 'Win Rate',   value: `${wr}%`,               color: wr >= 60 ? 'green' : wr >= 40 ? 'amber' : 'red' },
          { label: 'Wins',       value: wins.length,            color: 'green' },
          { label: 'Losses',     value: losses.length,          color: 'red' },
          { label: 'Pending',    value: pending.length,         color: 'amber' },
          { label: 'Avg Conf',   value: `${avgConf}%`,          color: '' },
          { label: 'Avg RR',     value: `1:${avgRR}`,           color: '' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl p-4">
            <p className="text-[9px] text-[#475569] uppercase tracking-widest font-semibold">{label}</p>
            <p className={`text-xl font-bold mt-1.5 ${
              color === 'green' ? 'text-[#22c55e]' : color === 'red' ? 'text-[#ef4444]' : color === 'amber' ? 'text-amber-400' : 'text-white'
            }`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Direction analysis + Pair table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Direction breakdown */}
        <Card title="Direction Analysis">
          <div className="space-y-5">
            {[
              { label: 'LONG',  color: '#22c55e', bg: '#22c55e15', count: longs.length,  winsCount: longWins.length,  closedCount: longs.filter(s => s.result !== 'pending').length },
              { label: 'SHORT', color: '#ef4444', bg: '#ef444415', count: shorts.length, winsCount: shortWins.length, closedCount: shorts.filter(s => s.result !== 'pending').length },
            ].map(({ label, color, bg, count, winsCount, closedCount }) => {
              const pct = winRate(winsCount, closedCount)
              return (
                <div key={label}>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="font-bold px-2 py-0.5 rounded text-xs" style={{ color, background: bg }}>{label}</span>
                    <span className="text-[#94a3b8]">{count} signals · {winsCount}W / {closedCount - winsCount}L · <span style={{ color }}>{pct}% WR</span></span>
                  </div>
                  <div className="h-2 bg-[#2a2a3a] rounded-full overflow-hidden flex">
                    <div className="h-full" style={{ width: `${pct}%`, background: color }} />
                    <div className="h-full bg-[#ef4444]/40" style={{ width: `${100 - pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </Card>

        {/* Pair performance table */}
        <Card title="Performance by Pair">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#475569] border-b border-[#2a2a3a]">
                  <th className="text-left pb-2 font-semibold">Pair</th>
                  <th className="text-right pb-2 font-semibold">W</th>
                  <th className="text-right pb-2 font-semibold">L</th>
                  <th className="text-right pb-2 font-semibold">Open</th>
                  <th className="text-right pb-2 font-semibold">WR%</th>
                </tr>
              </thead>
              <tbody>
                {pairs.map((p) => (
                  <tr key={p.pair} className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e]">
                    <td className="py-2 font-bold text-white">{p.pair}</td>
                    <td className="py-2 text-right text-[#22c55e]">{p.wins}</td>
                    <td className="py-2 text-right text-[#ef4444]">{p.losses}</td>
                    <td className="py-2 text-right text-amber-400">{p.pending}</td>
                    <td className="py-2 text-right">
                      {p.closed > 0 ? (
                        <span className={`font-bold ${winRate(p.wins, p.closed) >= 60 ? 'text-[#22c55e]' : winRate(p.wins, p.closed) >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>
                          {winRate(p.wins, p.closed)}%
                        </span>
                      ) : (
                        <span className="text-[#475569]">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Confidence + RR buckets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Win Rate by Confidence Score">
          <div className="space-y-4">
            {confData.map((b) => (
              <div key={b.label}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-[#94a3b8] font-semibold">{b.label}</span>
                  <span className="text-[#64748b]">{b.wins}W / {b.total - b.wins}L
                    {b.total > 0 && <span className={`ml-2 font-bold ${b.wr >= 60 ? 'text-[#22c55e]' : b.wr >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>{b.wr}%</span>}
                  </span>
                </div>
                <div className="h-2 bg-[#2a2a3a] rounded-full overflow-hidden">
                  {b.total > 0
                    ? <div className="h-full rounded-full" style={{ width: `${b.wr}%`, background: b.wr >= 60 ? '#22c55e' : b.wr >= 40 ? '#f59e0b' : '#ef4444' }} />
                    : <div className="h-full w-full bg-[#2a2a3a]" />
                  }
                </div>
                {b.total === 0 && <p className="text-[10px] text-[#334155] mt-0.5">No closed signals in this range yet</p>}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Win Rate by Risk:Reward Ratio">
          <div className="space-y-4">
            {rrData.map((b) => (
              <div key={b.label}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-[#94a3b8] font-semibold">{b.label}</span>
                  <span className="text-[#64748b]">{b.wins}W / {b.total - b.wins}L
                    {b.total > 0 && <span className={`ml-2 font-bold ${b.wr >= 60 ? 'text-[#22c55e]' : b.wr >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>{b.wr}%</span>}
                  </span>
                </div>
                <div className="h-2 bg-[#2a2a3a] rounded-full overflow-hidden">
                  {b.total > 0
                    ? <div className="h-full rounded-full" style={{ width: `${b.wr}%`, background: b.wr >= 60 ? '#22c55e' : b.wr >= 40 ? '#f59e0b' : '#ef4444' }} />
                    : <div className="h-full w-full bg-[#2a2a3a]" />
                  }
                </div>
                {b.total === 0 && <p className="text-[10px] text-[#334155] mt-0.5">No closed signals in this range yet</p>}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Indicator hit rate */}
      <Card title="Indicator Analysis — Which signals fired on winners vs losers">
        {indicators.length === 0 ? (
          <p className="text-[#475569] text-sm py-2">
            No indicator data yet. signals need <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded text-xs">votes_json</code> column populated by the generator.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#475569] border-b border-[#2a2a3a]">
                  <th className="text-left pb-2 font-semibold w-36">Indicator</th>
                  <th className="text-right pb-2 font-semibold">Total fires</th>
                  <th className="text-right pb-2 font-semibold">On winners</th>
                  <th className="text-right pb-2 font-semibold">On losers</th>
                  <th className="text-right pb-2 font-semibold">Precision</th>
                  <th className="pb-2 pl-4">Reliability</th>
                </tr>
              </thead>
              <tbody>
                {indicators.map((ind) => (
                  <tr key={ind.name} className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e]">
                    <td className="py-2.5 font-bold text-white">{ind.name}</td>
                    <td className="py-2.5 text-right text-[#94a3b8]">{ind.total}</td>
                    <td className="py-2.5 text-right text-[#22c55e]">{ind.winFires}</td>
                    <td className="py-2.5 text-right text-[#ef4444]">{ind.lossFires}</td>
                    <td className="py-2.5 text-right">
                      <span className={`font-bold ${ind.wr >= 60 ? 'text-[#22c55e]' : ind.wr >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>
                        {ind.wr}%
                      </span>
                    </td>
                    <td className="py-2.5 pl-4 w-40">
                      <div className="h-1.5 bg-[#2a2a3a] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{
                          width: `${ind.wr}%`,
                          background: ind.wr >= 60 ? '#22c55e' : ind.wr >= 40 ? '#f59e0b' : '#ef4444',
                        }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Sentiment history */}
      <Card title="Market Sentiment History — Last 14 days">
        {sentiment.length === 0 ? (
          <p className="text-[#475569] text-sm py-2">No sentiment data yet. Run generate_signals to populate.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#475569] border-b border-[#2a2a3a]">
                  <th className="text-left pb-2 font-semibold">Date</th>
                  <th className="text-right pb-2 font-semibold">Bullish</th>
                  <th className="text-right pb-2 font-semibold">Neutral</th>
                  <th className="text-right pb-2 font-semibold">Bearish</th>
                  <th className="text-right pb-2 font-semibold">F&G</th>
                  <th className="text-right pb-2 font-semibold">Longs</th>
                  <th className="text-right pb-2 font-semibold">Shorts</th>
                  <th className="pb-2 pl-4">Breakdown</th>
                </tr>
              </thead>
              <tbody>
                {sentiment.map((s) => (
                  <tr key={s.id} className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e]">
                    <td className="py-2.5 font-semibold text-white">{s.date}</td>
                    <td className="py-2.5 text-right text-[#22c55e]">{s.bullish_pct}%</td>
                    <td className="py-2.5 text-right text-amber-400">{s.neutral_pct}%</td>
                    <td className="py-2.5 text-right text-[#ef4444]">{s.bearish_pct}%</td>
                    <td className="py-2.5 text-right text-[#94a3b8]">{s.fear_greed_value ?? '—'}</td>
                    <td className="py-2.5 text-right text-[#22c55e]">{s.active_longs}</td>
                    <td className="py-2.5 text-right text-[#ef4444]">{s.active_shorts}</td>
                    <td className="py-2.5 pl-4 w-32">
                      <div className="h-2 rounded-full overflow-hidden flex">
                        <div className="h-full bg-[#22c55e]" style={{ width: `${s.bullish_pct}%` }} />
                        <div className="h-full bg-amber-500/60" style={{ width: `${s.neutral_pct}%` }} />
                        <div className="h-full bg-[#ef4444]" style={{ width: `${s.bearish_pct}%` }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

// ── shared components ─────────────────────────────────────────────────────────
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#1a1a24] rounded-xl border border-[#2a2a3a] p-5">
      <h2 className="text-sm font-semibold text-white mb-4">{title}</h2>
      {children}
    </div>
  )
}

function LoadingState() {
  return (
    <div className="p-8 space-y-6">
      <div className="h-8 w-48 bg-[#2a2a3a] rounded animate-pulse" />
      <div className="grid grid-cols-4 gap-3">
        {[...Array(7)].map((_, i) => (
          <div key={i} className="h-20 bg-[#2a2a3a] rounded-xl animate-pulse" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-64 bg-[#2a2a3a] rounded-xl animate-pulse" />
        ))}
      </div>
    </div>
  )
}
