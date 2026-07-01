'use client'
import { useEffect, useMemo, useState, memo } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  AreaChart, Area,
} from 'recharts'
import { supabase, isConfigured } from '@/lib/supabase'
import { isAdmin } from '@/lib/admin'
import { createClient } from '@/lib/supabase'
import type { TradeSignal } from '@/types/signal'

// ── types ─────────────────────────────────────────────────────────────────────
interface Sentiment {
  id: string; date: string
  bullish_pct: number; neutral_pct: number; bearish_pct: number
  fear_greed_value: number | null
  active_longs: number; active_shorts: number
}

// ── constants ─────────────────────────────────────────────────────────────────
const C = { green: '#22c55e', red: '#ef4444', amber: '#f59e0b', blue: '#6366f1', gray: '#64748b', dim: '#1e2a3d', text: '#64748b' }
const wr = (w: number, t: number) => t ? Math.round((w / t) * 100) : 0

// ── custom tooltip (memoized) ─────────────────────────────────────────────────
const DarkTooltip = memo(({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#0d1117] border border-[#2a2a3a] rounded-lg px-3 py-2 text-xs shadow-2xl pointer-events-none">
      {label && <p className="text-[#64748b] mb-1.5 font-semibold uppercase tracking-wide text-[10px]">{label}</p>}
      {payload.map((p: any, i: number) => (
        <p key={i} className="font-medium" style={{ color: p.color ?? p.fill }}>
          {p.name}: <span className="font-bold">{p.value}{['Win Rate','Precision','Bullish','Neutral','Bearish'].includes(p.name) ? '%' : ''}</span>
        </p>
      ))}
    </div>
  )
})
DarkTooltip.displayName = 'DarkTooltip'

// ── shared components ─────────────────────────────────────────────────────────
const Card = memo(({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) => (
  <div className="bg-[#1a1a24] rounded-xl border border-[#2a2a3a] p-4 sm:p-5">
    <div className="mb-4">
      <h2 className="text-sm font-semibold text-white">{title}</h2>
      {subtitle && <p className="text-[11px] text-[#475569] mt-0.5 leading-relaxed">{subtitle}</p>}
    </div>
    {children}
  </div>
))
Card.displayName = 'Card'

const Empty = ({ text = 'No data yet.' }: { text?: string }) => (
  <p className="text-[#475569] text-sm py-8 text-center">{text}</p>
)

const Skeleton = ({ h = 240 }: { h?: number }) => (
  <div className="animate-pulse bg-[#2a2a3a] rounded-lg w-full" style={{ height: h }} />
)

const KpiCard = memo(({ label, value, color }: { label: string; value: string | number; color?: string }) => {
  const cls = color === 'green' ? 'text-[#22c55e]' : color === 'red' ? 'text-[#ef4444]' : color === 'amber' ? 'text-amber-400' : 'text-white'
  return (
    <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl p-3 sm:p-4">
      <p className="text-[9px] text-[#475569] uppercase tracking-widest font-semibold truncate">{label}</p>
      <p className={`text-lg sm:text-xl font-bold mt-1.5 ${cls}`}>{value}</p>
    </div>
  )
})
KpiCard.displayName = 'KpiCard'

// ── main page ─────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const [user, setUser]       = useState<{ email?: string } | null>(null)
  const [signals, setSignals] = useState<TradeSignal[]>([])
  const [sentiment, setSent]  = useState<Sentiment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => { setMounted(true) }, [])
  useEffect(() => { createClient().auth.getUser().then(({ data }) => setUser(data.user)) }, [])
  useEffect(() => {
    if (!isConfigured || user === null) return
    if (!isAdmin(user?.email)) { setLoading(false); return }
    Promise.all([
      supabase.from('trade_signals').select('*').order('timestamp', { ascending: false }),
      supabase.from('market_sentiment').select('*').order('date', { ascending: true }).limit(14),
    ]).then(([s, m]) => {
      if (s.error) setError(s.error.message)
      else setSignals(s.data ?? [])
      if (!m.error) setSent(m.data ?? [])
      setLoading(false)
    })
  }, [user])

  // ── all derived data memoized ───────────────────────────────────────────────
  const stats = useMemo(() => {
    const closed  = signals.filter(s => s.result === 'win' || s.result === 'loss')
    const wins    = signals.filter(s => s.result === 'win').length
    const losses  = signals.filter(s => s.result === 'loss').length
    const pending = signals.filter(s => s.result === 'pending').length
    const expired = signals.filter(s => s.result === 'expired').length
    const longs   = signals.filter(s => s.direction === 'long').length
    const shorts  = signals.filter(s => s.direction === 'short').length
    const avgConf = signals.length ? Math.round(signals.reduce((a, s) => a + s.confidence, 0) / signals.length) : 0
    return { closed, wins, losses, pending, expired, longs, shorts, avgConf, winRate: wr(wins, closed.length) }
  }, [signals])

  const resultPie = useMemo(() => [
    { name: 'Win',     value: stats.wins,    color: C.green },
    { name: 'Loss',    value: stats.losses,  color: C.red   },
    { name: 'Pending', value: stats.pending, color: C.amber },
    { name: 'Expired', value: stats.expired, color: C.gray  },
  ].filter(d => d.value > 0), [stats])

  const dirPie = useMemo(() => [
    { name: 'Long',  value: stats.longs,  color: C.green },
    { name: 'Short', value: stats.shorts, color: C.red   },
  ].filter(d => d.value > 0), [stats])

  const pairBar = useMemo(() => {
    const map: Record<string, { w: number; l: number }> = {}
    stats.closed.forEach(s => {
      if (!map[s.pair]) map[s.pair] = { w: 0, l: 0 }
      if (s.result === 'win') map[s.pair].w++
      else map[s.pair].l++
    })
    return Object.entries(map)
      .map(([pair, d]) => ({ pair, winRate: wr(d.w, d.w + d.l), wins: d.w, total: d.w + d.l }))
      .sort((a, b) => b.winRate - a.winRate)
      .slice(0, 10)
  }, [stats.closed])

  const confBar = useMemo(() => [
    { band: '60-70%', min: 60, max: 70 },
    { band: '70-80%', min: 70, max: 80 },
    { band: '80-90%', min: 80, max: 90 },
    { band: '90%+',   min: 90, max: 101 },
  ].map(b => {
    const inB   = stats.closed.filter(s => s.confidence >= b.min && s.confidence < b.max)
    const bWins = inB.filter(s => s.result === 'win').length
    return { band: b.band, winRate: wr(bWins, inB.length), count: inB.length }
  }), [stats.closed])

  const indBar = useMemo(() => {
    const map: Record<string, { w: number; l: number }> = {}
    stats.closed.forEach(s => {
      if (!s.votes_json) return
      Object.entries(s.votes_json as Record<string, number>).forEach(([name]) => {
        if (!map[name]) map[name] = { w: 0, l: 0 }
        if (s.result === 'win') map[name].w++
        else map[name].l++
      })
    })
    return Object.entries(map)
      .map(([name, d]) => ({ name, winRate: wr(d.w, d.w + d.l), fires: d.w + d.l }))
      .filter(d => d.fires >= 2)
      .sort((a, b) => b.winRate - a.winRate)
  }, [stats.closed])

  const sentArea = useMemo(() => sentiment.map(s => ({
    date: s.date.slice(5),
    Bullish: s.bullish_pct, Neutral: s.neutral_pct, Bearish: s.bearish_pct,
  })), [sentiment])

  const pairTable = useMemo(() => {
    const map: Record<string, { w: number; l: number; p: number }> = {}
    signals.forEach(s => {
      if (!map[s.pair]) map[s.pair] = { w: 0, l: 0, p: 0 }
      if (s.result === 'win')      map[s.pair].w++
      else if (s.result === 'loss') map[s.pair].l++
      else                          map[s.pair].p++
    })
    return Object.entries(map)
      .map(([pair, d]) => ({ pair, ...d, rate: wr(d.w, d.w + d.l) }))
      .sort((a, b) => (b.w + b.l) - (a.w + a.l))
  }, [signals])

  // ── guard states ─────────────────────────────────────────────────────────────
  if (user === null || loading) return <FullPageSkeleton />
  if (!isAdmin(user?.email)) return <AccessDenied />

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Analytics</h1>
          <p className="text-[#64748b] text-sm mt-0.5">
            {signals.length} total · {stats.closed.length} closed · <span className="text-[#6366f1] font-medium">Admin</span>
          </p>
        </div>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm">{error}</div>}

      {/* KPI cards — 2 cols mobile, 4 tablet, 7 desktop */}
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-2 sm:gap-3">
        <KpiCard label="Total"    value={signals.length}      />
        <KpiCard label="Win Rate" value={`${stats.winRate}%`} color={stats.winRate >= 60 ? 'green' : stats.winRate >= 40 ? 'amber' : 'red'} />
        <KpiCard label="Wins"     value={stats.wins}          color="green" />
        <KpiCard label="Losses"   value={stats.losses}        color="red"   />
        <KpiCard label="Pending"  value={stats.pending}       color="amber" />
        <KpiCard label="Avg Conf" value={`${stats.avgConf}%`} />
        <KpiCard label="Pairs"    value={pairTable.length}    />
      </div>

      {/* Pie charts — stack on mobile */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        <Card title="Result Distribution">
          {!mounted ? <Skeleton /> : resultPie.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={resultPie} cx="50%" cy="50%" innerRadius={52} outerRadius={80}
                  dataKey="value" label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  labelLine={false} fontSize={11}>
                  {resultPie.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: C.text }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Long vs Short">
          {!mounted ? <Skeleton /> : dirPie.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={dirPie} cx="50%" cy="50%" innerRadius={52} outerRadius={80}
                  dataKey="value" label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  labelLine={false} fontSize={11}>
                  {dirPie.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: C.text }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Bar charts — stack on mobile */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        <Card title="Win Rate by Pair">
          {!mounted ? <Skeleton h={260} /> : pairBar.length === 0 ? <Empty text="No closed signals yet." /> : (
            <ResponsiveContainer width="100%" height={Math.max(200, pairBar.length * 28)}>
              <BarChart data={pairBar} layout="vertical" margin={{ left: 0, right: 20, top: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.dim} horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: C.text, fontSize: 10 }} tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="pair" tick={{ fill: C.text, fontSize: 10 }} width={80} />
                <Tooltip content={<DarkTooltip />} />
                <Bar dataKey="winRate" name="Win Rate" radius={[0, 4, 4, 0]} maxBarSize={20}>
                  {pairBar.map((d, i) => <Cell key={i} fill={d.winRate >= 60 ? C.green : d.winRate >= 40 ? C.amber : C.red} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Win Rate by Confidence Band">
          {!mounted ? <Skeleton h={260} /> : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={confBar} margin={{ right: 8, top: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.dim} vertical={false} />
                <XAxis dataKey="band" tick={{ fill: C.text, fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 10 }} tickFormatter={v => `${v}%`} width={36} />
                <Tooltip content={<DarkTooltip />} />
                <Bar dataKey="winRate" name="Win Rate" radius={[4, 4, 0, 0]} maxBarSize={48}>
                  {confBar.map((d, i) => <Cell key={i} fill={d.winRate >= 60 ? C.green : d.winRate >= 40 ? C.amber : C.red} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Indicator precision — votes_json */}
      <Card title="Indicator Precision"
        subtitle="Which indicators most reliably predicted wins. Needs closed signals with votes_json to populate.">
        {!mounted ? <Skeleton h={300} /> : indBar.length === 0 ? (
          <div className="py-8 text-center space-y-1">
            <p className="text-[#475569] text-sm">No indicator data yet.</p>
            <p className="text-[#334155] text-xs">
              <code className="bg-[#2a2a3a] px-1.5 py-0.5 rounded text-[#818cf8]">votes_json</code> stores which indicators voted per signal.
              Once signals close (win/loss), this chart shows which indicators are most accurate.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(240, indBar.length * 32)}>
            <BarChart data={indBar} layout="vertical" margin={{ left: 0, right: 32, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.dim} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: C.text, fontSize: 10 }} tickFormatter={v => `${v}%`} />
              <YAxis type="category" dataKey="name" tick={{ fill: C.text, fontSize: 10 }} width={90} />
              <Tooltip content={<DarkTooltip />} formatter={(v: any) => [`${v}%`, 'Precision']} />
              <Bar dataKey="winRate" name="Precision" radius={[0, 4, 4, 0]} maxBarSize={20}>
                {indBar.map((d, i) => <Cell key={i} fill={d.winRate >= 65 ? C.green : d.winRate >= 45 ? C.amber : C.red} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Sentiment area chart */}
      <Card title="Market Sentiment — Last 14 days"
        subtitle="Daily Bullish / Neutral / Bearish % generated by the signal algorithm">
        {!mounted ? <Skeleton /> : sentArea.length === 0 ? <Empty text="Run generate_signals to populate sentiment data." /> : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={sentArea} margin={{ right: 8, top: 4 }}>
              <defs>
                {[['bg', C.green], ['ng', C.amber], ['rg', C.red]].map(([id, color]) => (
                  <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={color} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={color} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.dim} vertical={false} />
              <XAxis dataKey="date" tick={{ fill: C.text, fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 10 }} tickFormatter={v => `${v}%`} width={36} />
              <Tooltip content={<DarkTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: C.text }} />
              <Area type="monotone" dataKey="Bullish" stroke={C.green} fill="url(#bg)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="Neutral" stroke={C.amber} fill="url(#ng)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="Bearish" stroke={C.red}   fill="url(#rg)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Pair table — scrollable on mobile */}
      <Card title="Pair Performance Detail">
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs min-w-[400px]">
            <thead>
              <tr className="text-[#475569] border-b border-[#2a2a3a]">
                {['Pair','W','L','Open','WR%',''].map((h, i) => (
                  <th key={i} className={`pb-2 font-semibold ${i === 0 ? 'text-left' : 'text-right'} ${i === 5 ? 'w-24 sm:w-32' : ''}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pairTable.map(({ pair, w, l, p, rate }) => (
                <tr key={pair} className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e] transition-colors">
                  <td className="py-2.5 font-bold text-white">{pair}</td>
                  <td className="py-2.5 text-right text-[#22c55e]">{w}</td>
                  <td className="py-2.5 text-right text-[#ef4444]">{l}</td>
                  <td className="py-2.5 text-right text-amber-400">{p}</td>
                  <td className="py-2.5 text-right">
                    <span className={`font-bold ${rate >= 60 ? 'text-[#22c55e]' : rate >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>
                      {w + l > 0 ? `${rate}%` : '—'}
                    </span>
                  </td>
                  <td className="py-2.5 pl-3">
                    <div className="h-1.5 bg-[#2a2a3a] rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${rate}%`, background: rate >= 60 ? C.green : rate >= 40 ? C.amber : C.red }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ── access denied ─────────────────────────────────────────────────────────────
function AccessDenied() {
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
          Set <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded text-xs">NEXT_PUBLIC_ADMIN_EMAILS</code> in{' '}
          <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded text-xs">.env.local</code>.
        </p>
      </div>
    </div>
  )
}

// ── full page skeleton ─────────────────────────────────────────────────────────
function FullPageSkeleton() {
  return (
    <div className="p-4 sm:p-8 space-y-6 animate-pulse">
      <div className="h-7 w-40 bg-[#2a2a3a] rounded" />
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-2 sm:gap-3">
        {[...Array(7)].map((_, i) => <div key={i} className="h-16 sm:h-20 bg-[#2a2a3a] rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        {[...Array(2)].map((_, i) => <div key={i} className="h-64 bg-[#2a2a3a] rounded-xl" />)}
      </div>
      {[260, 260, 300, 220].map((h, i) => <div key={i} className="bg-[#2a2a3a] rounded-xl" style={{ height: h }} />)}
    </div>
  )
}
