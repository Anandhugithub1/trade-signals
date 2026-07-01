'use client'
import { useEffect, useState } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  AreaChart, Area,
} from 'recharts'
import { supabase, isConfigured } from '@/lib/supabase'
import { isAdmin } from '@/lib/admin'
import { createClient } from '@/lib/supabase'
import type { TradeSignal } from '@/types/signal'

interface MarketSentiment {
  id: string; date: string
  bullish_pct: number; neutral_pct: number; bearish_pct: number
  fear_greed_value: number | null; fear_greed_label: string | null
  active_longs: number; active_shorts: number; dominant: string
}

// ── colours ───────────────────────────────────────────────────────────────────
const C = {
  green:  '#22c55e',
  red:    '#ef4444',
  amber:  '#f59e0b',
  blue:   '#6366f1',
  gray:   '#64748b',
  muted:  '#334155',
  text:   '#94a3b8',
}

function winRate(w: number, t: number) { return t ? Math.round((w / t) * 100) : 0 }

// ── custom tooltip ────────────────────────────────────────────────────────────
function DarkTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-lg px-3 py-2 text-xs shadow-xl">
      {label && <p className="text-[#94a3b8] mb-1 font-semibold">{label}</p>}
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color ?? p.fill }}>
          {p.name}: <span className="font-bold">{p.value}{p.name?.includes('%') || p.name === 'Win Rate' ? '%' : ''}</span>
        </p>
      ))}
    </div>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const [user, setUser]           = useState<{ email?: string } | null>(null)
  const [signals, setSignals]     = useState<TradeSignal[]>([])
  const [sentiment, setSentiment] = useState<MarketSentiment[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => setUser(data.user))
  }, [])

  useEffect(() => {
    if (!isConfigured || user === null) return
    if (!isAdmin(user?.email)) { setLoading(false); return }
    async function load() {
      const [sigRes, sentRes] = await Promise.all([
        supabase.from('trade_signals').select('*').order('timestamp', { ascending: false }),
        supabase.from('market_sentiment').select('*').order('date', { ascending: true }).limit(14),
      ])
      if (sigRes.error) setError(sigRes.error.message)
      else setSignals(sigRes.data ?? [])
      if (!sentRes.error) setSentiment(sentRes.data ?? [])
      setLoading(false)
    }
    load()
  }, [user])

  if (user === null || loading) return <LoadingState />

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
          <p className="text-[#64748b] text-sm">Set <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded">NEXT_PUBLIC_ADMIN_EMAILS</code> in <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded">.env.local</code>.</p>
        </div>
      </div>
    )
  }

  // ── derived data ─────────────────────────────────────────────────────────────
  const closed   = signals.filter(s => s.result === 'win' || s.result === 'loss')
  const wins     = signals.filter(s => s.result === 'win').length
  const losses   = signals.filter(s => s.result === 'loss').length
  const pending  = signals.filter(s => s.result === 'pending').length
  const expired  = signals.filter(s => s.result === 'expired').length
  const longs    = signals.filter(s => s.direction === 'long')
  const shorts   = signals.filter(s => s.direction === 'short')
  const wr       = winRate(wins, closed.length)
  const avgConf  = signals.length ? Math.round(signals.reduce((a, s) => a + s.confidence, 0) / signals.length) : 0

  // Pie data
  const resultPie = [
    { name: 'Win',     value: wins,    color: C.green },
    { name: 'Loss',    value: losses,  color: C.red },
    { name: 'Pending', value: pending, color: C.amber },
    { name: 'Expired', value: expired, color: C.gray },
  ].filter(d => d.value > 0)

  const directionPie = [
    { name: 'Long',  value: longs.length,  color: C.green },
    { name: 'Short', value: shorts.length, color: C.red },
  ].filter(d => d.value > 0)

  // Pair bar data (win rate per pair)
  const pairMap: Record<string, { wins: number; total: number }> = {}
  closed.forEach(s => {
    if (!pairMap[s.pair]) pairMap[s.pair] = { wins: 0, total: 0 }
    pairMap[s.pair].total++
    if (s.result === 'win') pairMap[s.pair].wins++
  })
  const pairBar = Object.entries(pairMap)
    .map(([pair, d]) => ({ pair, winRate: winRate(d.wins, d.total), wins: d.wins, total: d.total }))
    .sort((a, b) => b.winRate - a.winRate)
    .slice(0, 10)

  // Confidence buckets bar
  const confBuckets = [
    { bucket: '60-70%', min: 60, max: 70 },
    { bucket: '70-80%', min: 70, max: 80 },
    { bucket: '80-90%', min: 80, max: 90 },
    { bucket: '90%+',   min: 90, max: 101 },
  ].map(b => {
    const inB    = closed.filter(s => s.confidence >= b.min && s.confidence < b.max)
    const bWins  = inB.filter(s => s.result === 'win').length
    return { ...b, count: inB.length, winRate: winRate(bWins, inB.length) }
  })

  // votes_json indicator bar
  const indMap: Record<string, { wins: number; losses: number }> = {}
  closed.forEach(s => {
    if (!s.votes_json) return
    Object.entries(s.votes_json as Record<string, number>).forEach(([name]) => {
      if (!indMap[name]) indMap[name] = { wins: 0, losses: 0 }
      if (s.result === 'win') indMap[name].wins++
      else indMap[name].losses++
    })
  })
  const indBar = Object.entries(indMap)
    .map(([name, d]) => ({
      name,
      winRate: winRate(d.wins, d.wins + d.losses),
      fires: d.wins + d.losses,
    }))
    .filter(d => d.fires >= 2)
    .sort((a, b) => b.winRate - a.winRate)

  // Sentiment area chart
  const sentimentArea = sentiment.map(s => ({
    date:    s.date.slice(5),   // "MM-DD"
    Bullish: s.bullish_pct,
    Neutral: s.neutral_pct,
    Bearish: s.bearish_pct,
    FG:      s.fear_greed_value ?? 0,
  }))

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Analytics</h1>
        <p className="text-[#64748b] text-sm mt-1">
          {signals.length} signals · {closed.length} closed · <span className="text-[#6366f1] font-medium">Admin only</span>
        </p>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm">{error}</div>}

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
        {[
          { label: 'Total',    value: signals.length,      color: '' },
          { label: 'Win Rate', value: `${wr}%`,            color: wr >= 60 ? 'green' : wr >= 40 ? 'amber' : 'red' },
          { label: 'Wins',     value: wins,                color: 'green' },
          { label: 'Losses',   value: losses,              color: 'red' },
          { label: 'Pending',  value: pending,             color: 'amber' },
          { label: 'Avg Conf', value: `${avgConf}%`,       color: '' },
          { label: 'Pairs',    value: pairBar.length,      color: '' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl p-4">
            <p className="text-[9px] text-[#475569] uppercase tracking-widest font-semibold">{label}</p>
            <p className={`text-xl font-bold mt-1.5 ${color === 'green' ? 'text-[#22c55e]' : color === 'red' ? 'text-[#ef4444]' : color === 'amber' ? 'text-amber-400' : 'text-white'}`}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {/* Pie charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Result Distribution">
          {resultPie.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={resultPie} cx="50%" cy="50%" innerRadius={60} outerRadius={90}
                  dataKey="value" label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  labelLine={false}>
                  {resultPie.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: C.text }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Direction Distribution">
          {directionPie.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={directionPie} cx="50%" cy="50%" innerRadius={60} outerRadius={90}
                  dataKey="value" label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  labelLine={false}>
                  {directionPie.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: C.text }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Bar charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Win Rate by Pair">
          {pairBar.length === 0 ? <Empty text="No closed signals yet." /> : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={pairBar} layout="vertical" margin={{ left: 10, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="pair" tick={{ fill: C.text, fontSize: 11 }} width={72} />
                <Tooltip content={<DarkTooltip />} />
                <Bar dataKey="winRate" name="Win Rate" radius={[0, 4, 4, 0]}>
                  {pairBar.map((d, i) => (
                    <Cell key={i} fill={d.winRate >= 60 ? C.green : d.winRate >= 40 ? C.amber : C.red} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Win Rate by Confidence Band">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={confBuckets} margin={{ right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
              <XAxis dataKey="bucket" tick={{ fill: C.text, fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <Tooltip content={<DarkTooltip />} />
              <Bar dataKey="winRate" name="Win Rate" radius={[4, 4, 0, 0]}>
                {confBuckets.map((d, i) => (
                  <Cell key={i} fill={d.winRate >= 60 ? C.green : d.winRate >= 40 ? C.amber : C.red} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Votes_json — Indicator Analysis */}
      <Card
        title="Indicator Precision — Which indicators predicted wins"
        subtitle="Powered by votes_json stored per signal. Each bar = % of times this indicator fired on a winning signal."
      >
        {indBar.length === 0 ? (
          <div className="py-6 text-center">
            <p className="text-[#475569] text-sm mb-1">No indicator data yet.</p>
            <p className="text-[#334155] text-xs">
              <code className="bg-[#2a2a3a] px-1.5 py-0.5 rounded">votes_json</code> is stored when signals are generated.
              Once signals close (win/loss), this chart populates automatically.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(240, indBar.length * 32)}>
            <BarChart data={indBar} layout="vertical" margin={{ left: 10, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <YAxis type="category" dataKey="name" tick={{ fill: C.text, fontSize: 11 }} width={88} />
              <Tooltip content={<DarkTooltip />} formatter={(v: any) => [`${v}%`, 'Precision']} />
              <Bar dataKey="winRate" name="Precision" radius={[0, 4, 4, 0]}>
                {indBar.map((d, i) => (
                  <Cell key={i} fill={d.winRate >= 65 ? C.green : d.winRate >= 45 ? C.amber : C.red} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Sentiment area chart */}
      <Card
        title="Market Sentiment — Last 14 days"
        subtitle="Bullish / Neutral / Bearish % from generate_signals daily analysis"
      >
        {sentimentArea.length === 0 ? (
          <Empty text="No sentiment data yet. Run generate_signals to populate." />
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={sentimentArea} margin={{ right: 10 }}>
              <defs>
                {[['bullGrad', C.green], ['neutralGrad', C.amber], ['bearGrad', C.red]].map(([id, color]) => (
                  <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={color} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
              <XAxis dataKey="date" tick={{ fill: C.text, fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <Tooltip content={<DarkTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: C.text }} />
              <Area type="monotone" dataKey="Bullish" stroke={C.green} fill="url(#bullGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="Neutral" stroke={C.amber} fill="url(#neutralGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="Bearish" stroke={C.red}   fill="url(#bearGrad)"   strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Pair table */}
      <Card title="Performance by Pair — Detail">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[#475569] border-b border-[#2a2a3a]">
                {['Pair', 'W', 'L', 'Open', 'WR%', 'Trend'].map(h => (
                  <th key={h} className={`pb-2 font-semibold ${h === 'Pair' ? 'text-left' : 'text-right'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(pairMap).map(([pair, d]) => {
                const t  = d.wins + d.total - d.wins  // total closed = d.total
                const wr = winRate(d.wins, d.total)
                const pend = signals.filter(s => s.pair === pair && s.result === 'pending').length
                return (
                  <tr key={pair} className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e]">
                    <td className="py-2.5 font-bold text-white">{pair}</td>
                    <td className="py-2.5 text-right text-[#22c55e]">{d.wins}</td>
                    <td className="py-2.5 text-right text-[#ef4444]">{d.total - d.wins}</td>
                    <td className="py-2.5 text-right text-amber-400">{pend}</td>
                    <td className="py-2.5 text-right">
                      <span className={`font-bold ${wr >= 60 ? 'text-[#22c55e]' : wr >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>{wr}%</span>
                    </td>
                    <td className="py-2.5 pl-4 w-28">
                      <div className="h-1.5 bg-[#2a2a3a] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${wr}%`, background: wr >= 60 ? C.green : wr >= 40 ? C.amber : C.red }} />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ── shared ─────────────────────────────────────────────────────────────────────
function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#1a1a24] rounded-xl border border-[#2a2a3a] p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        {subtitle && <p className="text-[11px] text-[#475569] mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

function Empty({ text = 'No data yet.' }: { text?: string }) {
  return <p className="text-[#475569] text-sm py-6 text-center">{text}</p>
}

function LoadingState() {
  return (
    <div className="p-8 space-y-6">
      <div className="h-8 w-48 bg-[#2a2a3a] rounded animate-pulse" />
      <div className="grid grid-cols-7 gap-3">
        {[...Array(7)].map((_, i) => <div key={i} className="h-20 bg-[#2a2a3a] rounded-xl animate-pulse" />)}
      </div>
      {[...Array(4)].map((_, i) => <div key={i} className="h-72 bg-[#2a2a3a] rounded-xl animate-pulse" />)}
    </div>
  )
}
