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

const C = { green: '#22c55e', red: '#ef4444', amber: '#f59e0b', blue: '#6366f1', gray: '#64748b', text: '#94a3b8' }

function wr(w: number, t: number) { return t ? Math.round((w / t) * 100) : 0 }

function DarkTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#0f0f13] border border-[#2a2a3a] rounded-lg px-3 py-2 text-xs shadow-xl">
      {label && <p className="text-[#94a3b8] mb-1 font-semibold">{label}</p>}
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color ?? p.fill }}>
          {p.name}: <span className="font-bold">{p.value}{String(p.name).includes('%') || p.name === 'Win Rate' || p.name === 'Precision' ? '%' : ''}</span>
        </p>
      ))}
    </div>
  )
}

// Placeholder shown while waiting for browser mount (avoids SSR mismatch)
function ChartSkeleton({ h = 240 }: { h?: number }) {
  return <div className="animate-pulse bg-[#2a2a3a] rounded-lg w-full" style={{ height: h }} />
}

export default function AnalyticsPage() {
  const [user, setUser]       = useState<{ email?: string } | null>(null)
  const [signals, setSignals] = useState<TradeSignal[]>([])
  const [sentiment, setSent]  = useState<MarketSentiment[]>([])
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
    ]).then(([sigRes, sentRes]) => {
      if (sigRes.error) setError(sigRes.error.message)
      else setSignals(sigRes.data ?? [])
      if (!sentRes.error) setSent(sentRes.data ?? [])
      setLoading(false)
    })
  }, [user])

  if (user === null || loading) return <LoadingState />

  if (!isAdmin(user?.email)) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="text-center max-w-sm">
          <h2 className="text-lg font-bold text-white mb-2">Admin Access Required</h2>
          <p className="text-[#64748b] text-sm">Set <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded">NEXT_PUBLIC_ADMIN_EMAILS</code> in your <code className="text-[#818cf8] bg-[#2a2a3a] px-1 rounded">.env.local</code>.</p>
        </div>
      </div>
    )
  }

  // ── derived ───────────────────────────────────────────────────────────────
  const closed   = signals.filter(s => s.result === 'win' || s.result === 'loss')
  const wins     = signals.filter(s => s.result === 'win').length
  const losses   = signals.filter(s => s.result === 'loss').length
  const pending  = signals.filter(s => s.result === 'pending').length
  const expired  = signals.filter(s => s.result === 'expired').length
  const longs    = signals.filter(s => s.direction === 'long').length
  const shorts   = signals.filter(s => s.direction === 'short').length
  const winRate  = wr(wins, closed.length)
  const avgConf  = signals.length ? Math.round(signals.reduce((a, s) => a + s.confidence, 0) / signals.length) : 0

  const resultPie = [
    { name: 'Win',     value: wins,    color: C.green },
    { name: 'Loss',    value: losses,  color: C.red },
    { name: 'Pending', value: pending, color: C.amber },
    { name: 'Expired', value: expired, color: C.gray },
  ].filter(d => d.value > 0)

  const dirPie = [
    { name: 'Long',  value: longs,  color: C.green },
    { name: 'Short', value: shorts, color: C.red },
  ].filter(d => d.value > 0)

  const pairMap: Record<string, { w: number; l: number; p: number }> = {}
  signals.forEach(s => {
    if (!pairMap[s.pair]) pairMap[s.pair] = { w: 0, l: 0, p: 0 }
    if (s.result === 'win')     pairMap[s.pair].w++
    else if (s.result === 'loss') pairMap[s.pair].l++
    else pairMap[s.pair].p++
  })
  const pairBar = Object.entries(pairMap)
    .map(([pair, d]) => ({ pair, winRate: wr(d.w, d.w + d.l), wins: d.w, total: d.w + d.l + d.p }))
    .filter(d => d.wins + (pairMap[d.pair]?.l ?? 0) > 0)
    .sort((a, b) => b.winRate - a.winRate).slice(0, 10)

  const confBar = [
    { band: '60-70%', min: 60, max: 70 },
    { band: '70-80%', min: 70, max: 80 },
    { band: '80-90%', min: 80, max: 90 },
    { band: '90%+',   min: 90, max: 101 },
  ].map(b => {
    const inB   = closed.filter(s => s.confidence >= b.min && s.confidence < b.max)
    const bWins = inB.filter(s => s.result === 'win').length
    return { band: b.band, winRate: wr(bWins, inB.length), count: inB.length }
  })

  const indMap: Record<string, { w: number; l: number }> = {}
  closed.forEach(s => {
    if (!s.votes_json) return
    Object.entries(s.votes_json as Record<string, number>).forEach(([name]) => {
      if (!indMap[name]) indMap[name] = { w: 0, l: 0 }
      if (s.result === 'win') indMap[name].w++
      else indMap[name].l++
    })
  })
  const indBar = Object.entries(indMap)
    .map(([name, d]) => ({ name, winRate: wr(d.w, d.w + d.l), fires: d.w + d.l }))
    .filter(d => d.fires >= 2)
    .sort((a, b) => b.winRate - a.winRate)

  const sentArea = sentiment.map(s => ({
    date: s.date.slice(5),
    Bullish: s.bullish_pct, Neutral: s.neutral_pct, Bearish: s.bearish_pct,
  }))

  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Analytics</h1>
        <p className="text-[#64748b] text-sm mt-1">{signals.length} signals · {closed.length} closed · <span className="text-[#6366f1] font-medium">Admin only</span></p>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm">{error}</div>}

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
        {[
          { label: 'Total',    v: signals.length,  c: ''      },
          { label: 'Win Rate', v: `${winRate}%`,   c: winRate >= 60 ? 'green' : winRate >= 40 ? 'amber' : 'red' },
          { label: 'Wins',     v: wins,            c: 'green' },
          { label: 'Losses',   v: losses,          c: 'red'   },
          { label: 'Pending',  v: pending,         c: 'amber' },
          { label: 'Avg Conf', v: `${avgConf}%`,   c: ''      },
          { label: 'Pairs',    v: pairBar.length,  c: ''      },
        ].map(({ label, v, c }) => (
          <div key={label} className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl p-4">
            <p className="text-[9px] text-[#475569] uppercase tracking-widest font-semibold">{label}</p>
            <p className={`text-xl font-bold mt-1.5 ${c === 'green' ? 'text-[#22c55e]' : c === 'red' ? 'text-[#ef4444]' : c === 'amber' ? 'text-amber-400' : 'text-white'}`}>{v}</p>
          </div>
        ))}
      </div>

      {/* Pie charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Result Distribution">
          {!mounted ? <ChartSkeleton /> : resultPie.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={resultPie} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value"
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`} labelLine={false}>
                  {resultPie.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: C.text }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Long vs Short Distribution">
          {!mounted ? <ChartSkeleton /> : dirPie.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={dirPie} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value"
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`} labelLine={false}>
                  {dirPie.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: C.text }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Bar charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Win Rate by Pair">
          {!mounted ? <ChartSkeleton h={280} /> : pairBar.length === 0 ? <Empty text="No closed signals yet." /> : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={pairBar} layout="vertical" margin={{ left: 8, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="pair" tick={{ fill: C.text, fontSize: 10 }} width={76} />
                <Tooltip content={<DarkTooltip />} />
                <Bar dataKey="winRate" name="Win Rate" radius={[0, 4, 4, 0]}>
                  {pairBar.map((d, i) => <Cell key={i} fill={d.winRate >= 60 ? C.green : d.winRate >= 40 ? C.amber : C.red} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Win Rate by Confidence Band">
          {!mounted ? <ChartSkeleton h={280} /> : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={confBar} margin={{ right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
                <XAxis dataKey="band" tick={{ fill: C.text, fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
                <Tooltip content={<DarkTooltip />} />
                <Bar dataKey="winRate" name="Win Rate" radius={[4, 4, 0, 0]}>
                  {confBar.map((d, i) => <Cell key={i} fill={d.winRate >= 60 ? C.green : d.winRate >= 40 ? C.amber : C.red} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Indicator precision — votes_json */}
      <Card title="Indicator Precision" subtitle="From votes_json — % of times each indicator fired on a winning signal. Needs closed signals to populate.">
        {!mounted ? <ChartSkeleton h={320} /> : indBar.length === 0 ? (
          <div className="py-6 text-center">
            <p className="text-[#475569] text-sm mb-1">No indicator data yet.</p>
            <p className="text-[#334155] text-xs">
              <code className="bg-[#2a2a3a] px-1.5 py-0.5 rounded">votes_json</code> is stored when signals generate. Once signals close (win/loss) this chart appears.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(260, indBar.length * 34)}>
            <BarChart data={indBar} layout="vertical" margin={{ left: 8, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <YAxis type="category" dataKey="name" tick={{ fill: C.text, fontSize: 11 }} width={92} />
              <Tooltip content={<DarkTooltip />} formatter={(v: any) => [`${v}%`, 'Precision']} />
              <Bar dataKey="winRate" name="Precision" radius={[0, 4, 4, 0]}>
                {indBar.map((d, i) => <Cell key={i} fill={d.winRate >= 65 ? C.green : d.winRate >= 45 ? C.amber : C.red} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Sentiment area chart */}
      <Card title="Market Sentiment Trend" subtitle="Daily Bullish / Neutral / Bearish % from generate_signals analysis">
        {!mounted ? <ChartSkeleton /> : sentArea.length === 0 ? <Empty text="No sentiment data yet. Run generate_signals to populate." /> : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={sentArea} margin={{ right: 10 }}>
              <defs>
                {[['bg', C.green], ['ng', C.amber], ['rg', C.red]].map(([id, color]) => (
                  <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={color} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3d" />
              <XAxis dataKey="date" tick={{ fill: C.text, fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <Tooltip content={<DarkTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: C.text }} />
              <Area type="monotone" dataKey="Bullish" stroke={C.green} fill="url(#bg)" strokeWidth={2} />
              <Area type="monotone" dataKey="Neutral" stroke={C.amber} fill="url(#ng)" strokeWidth={2} />
              <Area type="monotone" dataKey="Bearish" stroke={C.red}   fill="url(#rg)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Pair detail table */}
      <Card title="Pair Performance — Detail">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[#475569] border-b border-[#2a2a3a]">
                {['Pair', 'W', 'L', 'Open', 'WR%', 'Bar'].map(h => (
                  <th key={h} className={`pb-2 font-semibold ${h === 'Pair' ? 'text-left' : 'text-right'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(pairMap).map(([pair, d]) => {
                const rate = wr(d.w, d.w + d.l)
                return (
                  <tr key={pair} className="border-b border-[#2a2a3a]/40 hover:bg-[#1f1f2e]">
                    <td className="py-2.5 font-bold text-white">{pair}</td>
                    <td className="py-2.5 text-right text-[#22c55e]">{d.w}</td>
                    <td className="py-2.5 text-right text-[#ef4444]">{d.l}</td>
                    <td className="py-2.5 text-right text-amber-400">{d.p}</td>
                    <td className="py-2.5 text-right">
                      <span className={`font-bold ${rate >= 60 ? 'text-[#22c55e]' : rate >= 40 ? 'text-amber-400' : 'text-[#ef4444]'}`}>{d.w + d.l > 0 ? `${rate}%` : '—'}</span>
                    </td>
                    <td className="py-2.5 pl-4 w-28">
                      <div className="h-1.5 bg-[#2a2a3a] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${rate}%`, background: rate >= 60 ? C.green : rate >= 40 ? C.amber : C.red }} />
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
    <div className="p-8 space-y-6 animate-pulse">
      <div className="h-8 w-48 bg-[#2a2a3a] rounded" />
      <div className="grid grid-cols-7 gap-3">{[...Array(7)].map((_, i) => <div key={i} className="h-20 bg-[#2a2a3a] rounded-xl" />)}</div>
      {[...Array(5)].map((_, i) => <div key={i} className="h-64 bg-[#2a2a3a] rounded-xl" />)}
    </div>
  )
}
