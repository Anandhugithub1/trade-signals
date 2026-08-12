'use client'
import { useEffect, useMemo, useState, memo, useCallback } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis,
  AreaChart, Area, ReferenceLine,
  LineChart, Line, Legend,
} from 'recharts'
import { supabase, isConfigured } from '@/lib/supabase'
import { isAdmin } from '@/lib/admin'
import { createClient } from '@/lib/supabase'
import type { TradeSignal } from '@/types/signal'
import MonthlyTrackRecord from '@/components/MonthlyTrackRecord'

interface Sentiment {
  id: string; date: string
  bullish_pct: number; neutral_pct: number; bearish_pct: number
  fear_greed_value: number | null
  active_longs: number; active_shorts: number
}

const wr = (w: number, t: number) => t ? Math.round((w / t) * 100) : 0

// ── Tooltip ───────────────────────────────────────────────────────────────────
const Tip = memo(({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#0d1117] border border-[#30363d] rounded-xl px-4 py-3 shadow-2xl text-xs pointer-events-none">
      {label && <p className="text-[#8b949e] mb-2 font-medium">{label}</p>}
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color ?? p.fill }} />
          <span className="text-[#8b949e]">{p.name}</span>
          <span className="ml-auto font-bold text-white pl-4">
            {p.name === 'P&L'
              ? `${p.value >= 0 ? '+' : '−'}$${Math.abs(p.value)}`
              : p.name === 'donchian' || p.name === 'mean_reversion'
              ? `${p.value >= 0 ? '+' : ''}${p.value}R`
              : `${p.value}${['Win Rate','Precision','Bullish','Neutral','Bearish'].includes(p.name) ? '%' : ''}`}
          </span>
        </div>
      ))}
    </div>
  )
})
Tip.displayName = 'Tip'

// ── Shared ────────────────────────────────────────────────────────────────────
const Section = memo(({ title, sub, children, right }: {
  title: string; sub?: string; children: React.ReactNode; right?: React.ReactNode
}) => (
  <div className="bg-[#161b22] border border-[#30363d] rounded-2xl overflow-hidden">
    <div className="flex items-start justify-between px-5 sm:px-6 py-4 border-b border-[#21262d]">
      <div>
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        {sub && <p className="text-[11px] text-[#8b949e] mt-0.5 max-w-lg">{sub}</p>}
      </div>
      {right}
    </div>
    <div className="p-5 sm:p-6">{children}</div>
  </div>
))
Section.displayName = 'Section'

const Pill = ({ label, value, sub }: { label: string; value: string | number; sub?: string }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[11px] text-[#8b949e] font-medium">{label}</span>
    <span className="text-xl sm:text-2xl font-bold text-white tracking-tight leading-none">{value}</span>
    {sub && <span className="text-[11px] text-[#8b949e]">{sub}</span>}
  </div>
)

const Bar2 = ({ pct, color }: { pct: number; color: string }) => (
  <div className="h-1.5 bg-[#21262d] rounded-full overflow-hidden">
    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color, transition: 'width .4s ease' }} />
  </div>
)

const Badge = ({ v }: { v: number }) => {
  const [color, bg] = v >= 60 ? ['#22c55e','#22c55e15'] : v >= 40 ? ['#f59e0b','#f59e0b15'] : ['#ef4444','#ef444415']
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded-md" style={{ color, background: bg }}>
      {v > 0 ? `${v}%` : '—'}
    </span>
  )
}

const Skel = ({ h = 200 }: { h?: number }) => (
  <div className="animate-pulse bg-[#21262d] rounded-xl" style={{ height: h }} />
)

const NoData = ({ msg = 'No data yet.' }: { msg?: string }) => (
  <div className="flex flex-col items-center justify-center py-12 gap-2">
    <svg className="w-10 h-10 text-[#30363d]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
    <p className="text-[#8b949e] text-sm text-center">{msg}</p>
  </div>
)

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Analytics() {
  const [user, setUser]       = useState<{ email?: string } | null>(null)
  const [signals, setSignals] = useState<TradeSignal[]>([])
  const [sent, setSent]       = useState<Sentiment[]>([])
  const [loading, setLoading] = useState(true)
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
      setSignals(s.data ?? [])
      setSent(m.data ?? [])
      setLoading(false)
    })
  }, [user])

  // ── memoized derivations ──────────────────────────────────────────────────
  const s = useMemo(() => {
    const closed  = signals.filter(x => x.result === 'win' || x.result === 'loss')
    const wins    = signals.filter(x => x.result === 'win').length
    const losses  = signals.filter(x => x.result === 'loss').length
    const pending = signals.filter(x => x.result === 'pending').length
    const expired = signals.filter(x => x.result === 'expired').length
    const longs   = signals.filter(x => x.direction === 'long').length
    const shorts  = signals.filter(x => x.direction === 'short').length
    const conf    = signals.length ? Math.round(signals.reduce((a, x) => a + x.confidence, 0) / signals.length) : 0
    return { closed, wins, losses, pending, expired, longs, shorts, conf, winRate: wr(wins, closed.length) }
  }, [signals])

  const donutData = useMemo(() => [
    { name: 'Win',     v: s.wins,    c: '#22c55e' },
    { name: 'Loss',    v: s.losses,  c: '#ef4444' },
    { name: 'Pending', v: s.pending, c: '#f59e0b' },
    { name: 'Expired', v: s.expired, c: '#475569' },
  ].filter(d => d.v > 0), [s])

  const pairRows = useMemo(() => {
    const map: Record<string, { w: number; l: number; p: number }> = {}
    signals.forEach(x => {
      if (!map[x.pair]) map[x.pair] = { w: 0, l: 0, p: 0 }
      if (x.result === 'win')       map[x.pair].w++
      else if (x.result === 'loss') map[x.pair].l++
      else                          map[x.pair].p++
    })
    return Object.entries(map)
      .map(([pair, d]) => ({ pair, ...d, rate: wr(d.w, d.w + d.l) }))
      .sort((a, b) => b.rate - a.rate)
  }, [signals])

  const pairBar = useMemo(() => pairRows
    .filter(p => p.w + p.l > 0).slice(0, 8)
    .map(p => ({ pair: p.pair.replace('USDT',''), winRate: p.rate })),
  [pairRows])

  const confBar = useMemo(() => [
    { band: '60–70', min: 60, max: 70 },
    { band: '70–80', min: 70, max: 80 },
    { band: '80–90', min: 80, max: 90 },
    { band: '90+',   min: 90, max: 101 },
  ].map(b => {
    const inB   = s.closed.filter(x => x.confidence >= b.min && x.confidence < b.max)
    const bWins = inB.filter(x => x.result === 'win').length
    return { band: b.band, winRate: wr(bWins, inB.length), count: inB.length }
  }), [s.closed])

  const indBar = useMemo(() => {
    const map: Record<string, { w: number; l: number }> = {}
    s.closed.forEach(x => {
      if (!x.votes_json) return
      Object.entries(x.votes_json as Record<string, number>).forEach(([name]) => {
        if (!map[name]) map[name] = { w: 0, l: 0 }
        if (x.result === 'win') map[name].w++; else map[name].l++
      })
    })
    return Object.entries(map)
      .map(([name, d]) => ({ name, winRate: wr(d.w, d.w + d.l), fires: d.w + d.l }))
      .filter(d => d.fires >= 2).sort((a, b) => b.winRate - a.winRate)
  }, [s.closed])

  const sentArea = useMemo(() => sent.map(x => ({
    date: x.date.slice(5),
    Bullish: x.bullish_pct, Neutral: x.neutral_pct, Bearish: x.bearish_pct,
  })), [sent])

  // Equity curve — cumulative P&L at $1,000/trade using the algorithm's
  // actual TP/SL percentages (3.5% win = +$35, 2% loss = -$20)
  const equity = useMemo(() => {
    const closed = signals
      .filter(x => x.result === 'win' || x.result === 'loss')
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    let cum = 0
    return closed.map((x, i) => {
      cum += x.result === 'win' ? 35 : -20
      return {
        n: i + 1,
        date: new Date(x.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        'P&L': Math.round(cum * 100) / 100,
        pair: x.pair,
      }
    })
  }, [signals])
  const finalPnl = equity.length ? equity[equity.length - 1]['P&L'] : 0
  const eqColor  = finalPnl >= 0 ? '#22c55e' : '#ef4444'

  // ── Engine comparison ──────────────────────────────────────────────────────
  // Realized R-multiple per trade, computed from actual entry/stop/target —
  // NOT the equity curve's fixed $35/-$20 (that assumes one flat TP/SL % for
  // every trade, which donchian's 3R target and mean_reversion's ~1:1 target
  // both violate). risk = |entry - stop_loss|; a win realizes the full
  // planned reward (take_profit distance), a loss realizes -1R by
  // definition of the stop.
  const realizedR = (x: TradeSignal): number | null => {
    const risk = Math.abs(x.entry - x.stop_loss)
    if (!risk) return null
    if (x.result === 'win')  return Math.abs(x.take_profit - x.entry) / risk
    if (x.result === 'loss') return -1
    return null
  }

  const ENGINES = [
    { key: 'donchian',       label: 'Donchian',       color: '#22c55e' },
    { key: 'mean_reversion', label: 'Mean Reversion', color: '#6366f1' },
  ] as const

  const engineStats = useMemo(() => ENGINES.map(eng => {
    const rows   = signals.filter(x => x.strategy === eng.key)
    const closed = rows.filter(x => x.result === 'win' || x.result === 'loss')
    const wins   = closed.filter(x => x.result === 'win').length
    const losses = closed.length - wins
    const rs      = closed.map(realizedR).filter((r): r is number => r !== null)
    const totalR   = rs.reduce((a, r) => a + r, 0)
    const grossWin  = rs.filter(r => r > 0).reduce((a, r) => a + r, 0)
    const grossLoss = Math.abs(rs.filter(r => r < 0).reduce((a, r) => a + r, 0))
    const pf = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0)
    return {
      ...eng, rows: rows.length, closed: closed.length, wins, losses,
      winRate: wr(wins, closed.length), totalR, pf,
      pending: rows.filter(x => x.result === 'pending').length,
    }
  }), [signals])

  // Per-engine cumulative R curve, merged onto a shared trade index so both
  // lines render on one chart even though the engines fire at different
  // times/frequencies (mean_reversion fires far less often than donchian).
  const engineEquity = useMemo(() => {
    const series = ENGINES.map(eng => {
      const closed = signals
        .filter(x => x.strategy === eng.key && (x.result === 'win' || x.result === 'loss'))
        .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
      let cum = 0
      return closed.map(x => {
        const r = realizedR(x)
        cum += r ?? 0
        return { date: new Date(x.timestamp).getTime(), key: eng.key, cum: Math.round(cum * 100) / 100 }
      })
    })
    const merged = series.flat().sort((a, b) => a.date - b.date)
    if (merged.length === 0) return []
    const last: Record<string, number> = {}
    return merged.map(pt => {
      last[pt.key] = pt.cum
      return {
        date: new Date(pt.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        donchian: last['donchian'] ?? null,
        mean_reversion: last['mean_reversion'] ?? null,
      }
    })
  }, [signals])

  // ── guards ────────────────────────────────────────────────────────────────
  if (user === null || loading) return <PageSkeleton />
  if (!isAdmin(user?.email))   return <Blocked />

  const WR   = s.winRate
  const wrC  = WR >= 60 ? '#22c55e' : WR >= 40 ? '#f59e0b' : '#ef4444'

  return (
    <div className="min-h-screen bg-[#0d1117] p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto space-y-6">

        {/* ── Hero ── */}
        <div className="bg-gradient-to-br from-[#161b22] to-[#0d1117] border border-[#30363d] rounded-2xl p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
            {/* left */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-[#22c55e] animate-pulse" />
                <span className="text-xs text-[#8b949e] font-medium uppercase tracking-widest">Live Analytics</span>
                <span className="text-xs text-[#6366f1] bg-[#6366f1]/10 px-2 py-0.5 rounded-full font-semibold">Admin</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight mb-1">Signal Performance</h1>
              <p className="text-[#8b949e] text-sm">{signals.length} signals · {s.closed.length} closed · 90-day window</p>
            </div>
            {/* right — big win rate */}
            <div className="flex-shrink-0 text-center sm:text-right">
              <div className="text-6xl sm:text-7xl font-black tracking-tighter" style={{ color: wrC }}>{WR}%</div>
              <div className="text-[#8b949e] text-sm mt-1 font-medium">Win Rate</div>
              <div className="text-xs text-[#8b949e] mt-0.5">{s.wins}W · {s.losses}L · {s.pending} open</div>
            </div>
          </div>

          {/* KPI strip */}
          <div className="mt-6 pt-6 border-t border-[#21262d] grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4 sm:gap-6">
            {[
              { label: 'Total Signals',  value: signals.length },
              { label: 'Wins',           value: s.wins,    color: '#22c55e' },
              { label: 'Losses',         value: s.losses,  color: '#ef4444' },
              { label: 'Pending',        value: s.pending, color: '#f59e0b' },
              { label: 'Avg Strength', value: `${s.conf}%` },
              { label: 'Longs',          value: s.longs,   color: '#22c55e' },
              { label: 'Shorts',         value: s.shorts,  color: '#ef4444' },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <p className="text-[10px] text-[#8b949e] font-medium uppercase tracking-wide mb-1">{label}</p>
                <p className="text-xl font-bold" style={{ color: color ?? '#fff' }}>{value}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Monthly track record ── */}
        {/* Sits above the charts because it is the only view that survives
            the 90-day TTL — everything below is limited to that window. */}
        <Section
          title="Monthly Track Record"
          sub="Permanent month-by-month record across all three markets. Raw signals are deleted after 90 days; these rollups are kept forever."
        >
          <MonthlyTrackRecord />
        </Section>

        {/* ── Equity curve ── */}
        <Section
          title="Equity Curve — $1,000 per trade"
          sub="Cumulative P&L across closed signals in chronological order, using the algorithm's 3.5% TP / 2% SL."
          right={equity.length > 0 ? (
            <span className="text-lg font-black flex-shrink-0" style={{ color: eqColor }}>
              {finalPnl >= 0 ? '+' : '−'}${Math.abs(finalPnl).toFixed(0)}
            </span>
          ) : undefined}
        >
          {!mounted ? <Skel /> : equity.length < 2 ? (
            <NoData msg="Needs at least 2 closed signals to draw the curve." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={equity} margin={{ right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={eqColor} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={eqColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v => `$${v}`} width={44} axisLine={false} tickLine={false} />
                <ReferenceLine y={0} stroke="#30363d" strokeDasharray="4 4" />
                <Tooltip content={<Tip />} />
                <Area type="monotone" dataKey="P&L" stroke={eqColor} fill="url(#eqGrad)" strokeWidth={2.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Section>

        {/* ── Engine comparison ── */}
        <Section
          title="Engine Comparison"
          sub="donchian (trend breakout) vs mean_reversion (range-fade) — win rate, profit factor, and realized R-multiple per trade, computed from actual entry/stop/target/close, not a fixed % assumption."
        >
          {!mounted ? <Skel h={280} /> : (
            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {engineStats.map(e => {
                  const wrC = e.winRate >= 50 ? '#22c55e' : e.winRate >= 35 ? '#f59e0b' : '#ef4444'
                  const pfC = e.pf >= 1.2 ? '#22c55e' : e.pf >= 1 ? '#f59e0b' : '#ef4444'
                  return (
                    <div key={e.key} className="bg-[#21262d] rounded-xl p-4 border border-[#30363d]">
                      <div className="flex items-center justify-between mb-3">
                        <span className="flex items-center gap-2 text-sm font-bold text-[#c9d1d9]">
                          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: e.color }} />
                          {e.label}
                        </span>
                        <span className="text-xs bg-[#30363d] text-[#8b949e] px-2 py-0.5 rounded-md">
                          {e.rows} signal{e.rows === 1 ? '' : 's'}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <Pill label="Win Rate" value={e.closed > 0 ? `${e.winRate}%` : '—'} sub={`${e.wins}W / ${e.losses}L`} />
                        <Pill label="Profit Factor" value={e.pf === Infinity ? '∞' : e.closed > 0 ? e.pf.toFixed(2) : '—'} />
                        <Pill label="Total R" value={`${e.totalR >= 0 ? '+' : ''}${e.totalR.toFixed(1)}R`} />
                      </div>
                      <div className="mt-3 h-1.5 bg-[#0d1117] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${e.winRate}%`, background: wrC, transition: 'width .4s ease' }} />
                      </div>
                      <p className="text-[10px] text-[#8b949e] mt-1.5">
                        PF <span style={{ color: pfC }} className="font-semibold">{e.pf === Infinity ? '∞' : e.pf.toFixed(2)}</span>
                        {' · '}{e.pending} open
                      </p>
                    </div>
                  )
                })}
              </div>

              {engineEquity.length < 2 ? (
                <NoData msg="Needs at least 2 closed signals across both engines to draw the curve." />
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={engineEquity} margin={{ right: 8, top: 8 }}>
                    <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
                    <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v => `${v}R`} width={40} axisLine={false} tickLine={false} />
                    <ReferenceLine y={0} stroke="#30363d" strokeDasharray="4 4" />
                    <Tooltip content={<Tip />} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e' }} formatter={(v: string) => v === 'donchian' ? 'Donchian' : 'Mean Reversion'} />
                    <Line type="monotone" dataKey="donchian" stroke="#22c55e" strokeWidth={2.5} dot={false} connectNulls />
                    <Line type="monotone" dataKey="mean_reversion" stroke="#6366f1" strokeWidth={2.5} dot={false} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <p className="text-[10px] text-[#8b949e] text-center -mt-2">
                Cumulative realized R per engine, in trade-resolution order. R = actual reward:risk realized
                (win = target distance / stop distance, loss = −1R) — not a fixed dollar assumption.
              </p>
            </div>
          )}
        </Section>

        {/* ── Donuts row ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
          {/* Result donut */}
          <Section title="Result Breakdown">
            {!mounted ? <Skel /> : donutData.length === 0 ? <NoData /> : (
              <div className="flex items-center gap-6">
                <div className="flex-shrink-0 relative" style={{ width: 140, height: 140 }}>
                  <ResponsiveContainer width={140} height={140}>
                    <PieChart>
                      <Pie data={donutData} cx="50%" cy="50%" innerRadius={46} outerRadius={65}
                        dataKey="v" startAngle={90} endAngle={-270} strokeWidth={0}>
                        {donutData.map((d, i) => <Cell key={i} fill={d.c} />)}
                      </Pie>
                      <Tooltip content={<Tip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  {/* center text */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-2xl font-black" style={{ color: wrC }}>{WR}%</span>
                    <span className="text-[10px] text-[#8b949e]">Win Rate</span>
                  </div>
                </div>
                <div className="flex flex-col gap-3 flex-1">
                  {donutData.map(d => (
                    <div key={d.name}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="flex items-center gap-1.5 text-[#c9d1d9] font-medium">
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: d.c }} />
                          {d.name}
                        </span>
                        <span className="font-bold" style={{ color: d.c }}>{d.v}</span>
                      </div>
                      <Bar2 pct={signals.length ? (d.v / signals.length) * 100 : 0} color={d.c} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Section>

          {/* Direction split */}
          <Section title="Direction Split">
            {!mounted ? <Skel /> : (
              <div className="flex flex-col gap-5">
                {[
                  { label: 'Long', value: s.longs,  color: '#22c55e', wins: s.closed.filter(x=>x.direction==='long'&&x.result==='win').length, closed: s.closed.filter(x=>x.direction==='long').length },
                  { label: 'Short', value: s.shorts, color: '#ef4444', wins: s.closed.filter(x=>x.direction==='short'&&x.result==='win').length, closed: s.closed.filter(x=>x.direction==='short').length },
                ].map(d => {
                  const pct   = signals.length ? (d.value / signals.length) * 100 : 0
                  const dWr   = wr(d.wins, d.closed)
                  const dWrC  = dWr >= 60 ? '#22c55e' : dWr >= 40 ? '#f59e0b' : '#ef4444'
                  return (
                    <div key={d.label} className="bg-[#21262d] rounded-xl p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-[#c9d1d9]">{d.label}</span>
                          <span className="text-xs bg-[#30363d] text-[#8b949e] px-2 py-0.5 rounded-md">{d.value} signals</span>
                        </div>
                        <div className="text-right">
                          <span className="text-lg font-black" style={{ color: dWrC }}>{dWr}%</span>
                          <span className="text-[11px] text-[#8b949e] ml-1">WR</span>
                        </div>
                      </div>
                      <div className="h-2 bg-[#30363d] rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: d.color }} />
                      </div>
                      <p className="text-[11px] text-[#8b949e] mt-1.5">{d.wins}W / {d.closed - d.wins}L from {d.closed} closed</p>
                    </div>
                  )
                })}
              </div>
            )}
          </Section>
        </div>

        {/* ── Pair performance ── */}
        <Section title="Performance by Pair" sub="Win rate for each perpetual pair. Green ≥ 60%, amber 40–60%, red < 40%.">
          {!mounted ? <Skel h={280} /> : pairBar.length === 0 ? <NoData msg="No closed signals yet." /> : (
            <ResponsiveContainer width="100%" height={Math.max(200, pairBar.length * 36)}>
              <BarChart data={pairBar} layout="vertical" margin={{ left: 0, right: 44, top: 2, bottom: 2 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v => `${v}%`} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="pair" tick={{ fill: '#c9d1d9', fontSize: 11, fontWeight: 600 }} width={70} axisLine={false} tickLine={false} />
                <Tooltip content={<Tip />} cursor={{ fill: '#ffffff06' }} />
                <Bar dataKey="winRate" name="Win Rate" radius={[0, 6, 6, 0]} maxBarSize={22}
                  label={{ position: 'right', fill: '#8b949e', fontSize: 10, formatter: (v: any) => `${v}%` }}>
                  {pairBar.map((d, i) => <Cell key={i} fill={d.winRate >= 60 ? '#22c55e' : d.winRate >= 40 ? '#f59e0b' : '#ef4444'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Section>

        {/* ── Signal strength + Indicator side by side ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
          <Section title="Win Rate by Signal Strength">
            {!mounted ? <Skel h={220} /> : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={confBar} margin={{ right: 8, top: 4, bottom: 0 }} barCategoryGap="30%">
                  <XAxis dataKey="band" tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v => `${v}%`} width={32} axisLine={false} tickLine={false} />
                  <Tooltip content={<Tip />} cursor={{ fill: '#ffffff06' }} />
                  <Bar dataKey="winRate" name="Win Rate" radius={[6, 6, 0, 0]}
                    label={{ position: 'top', fill: '#8b949e', fontSize: 10, formatter: (v: any) => Number(v) > 0 ? `${v}%` : '' }}>
                    {confBar.map((d, i) => <Cell key={i} fill={d.winRate >= 60 ? '#22c55e' : d.winRate >= 40 ? '#f59e0b' : '#ef4444'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Section>

          <Section title="Indicator Precision" sub="From votes_json — fires on closed signals only">
            {!mounted ? <Skel h={220} /> : indBar.length === 0 ? (
              <NoData msg="Needs closed signals with votes_json to populate." />
            ) : (
              <div className="space-y-2.5 overflow-y-auto max-h-[220px] pr-1 custom-scroll">
                {indBar.map(d => {
                  const c = d.winRate >= 65 ? '#22c55e' : d.winRate >= 45 ? '#f59e0b' : '#ef4444'
                  return (
                    <div key={d.name} className="flex items-center gap-3">
                      <span className="text-[11px] text-[#8b949e] w-24 flex-shrink-0 font-medium truncate">{d.name}</span>
                      <div className="flex-1 h-2 bg-[#21262d] rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${d.winRate}%`, background: c }} />
                      </div>
                      <span className="text-[11px] font-bold w-8 text-right flex-shrink-0" style={{ color: c }}>{d.winRate}%</span>
                      <span className="text-[10px] text-[#8b949e] w-8 text-right flex-shrink-0">{d.fires}×</span>
                    </div>
                  )
                })}
              </div>
            )}
          </Section>
        </div>

        {/* ── Sentiment chart ── */}
        <Section title="Market Sentiment Trend" sub="Daily Bullish / Neutral / Bearish % from signal analysis">
          {!mounted ? <Skel /> : sentArea.length === 0 ? <NoData msg="Run generate_signals to populate." /> : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={sentArea} margin={{ right: 8, top: 4 }}>
                <defs>
                  {[['bg','#22c55e'],['ng','#f59e0b'],['rg','#ef4444']].map(([id,c]) => (
                    <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={c} stopOpacity={0.2} />
                      <stop offset="95%" stopColor={c} stopOpacity={0}   />
                    </linearGradient>
                  ))}
                </defs>
                <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0,100]} tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v=>`${v}%`} width={32} axisLine={false} tickLine={false} />
                <Tooltip content={<Tip />} />
                <Area type="monotone" dataKey="Bullish" stroke="#22c55e" fill="url(#bg)" strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="Neutral" stroke="#f59e0b" fill="url(#ng)" strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="Bearish" stroke="#ef4444" fill="url(#rg)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
          {sentArea.length > 0 && (
            <div className="flex gap-4 mt-3 flex-wrap">
              {[['#22c55e','Bullish'],['#f59e0b','Neutral'],['#ef4444','Bearish']].map(([c,l]) => (
                <span key={l} className="flex items-center gap-1.5 text-[11px] text-[#8b949e]">
                  <span className="w-3 h-0.5 rounded-full" style={{ background: c }} />{l}
                </span>
              ))}
            </div>
          )}
        </Section>

        {/* ── P&L Simulator ── */}
        <PnLSimulator wins={s.wins} losses={s.losses} />

        {/* ── Pair detail table ── */}
        <Section title="Pair Detail Table">
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-xs min-w-[460px]">
              <thead>
                <tr className="text-[#8b949e] border-b border-[#21262d]">
                  {['Pair','Wins','Losses','Open','Win Rate',''].map((h, i) => (
                    <th key={i} className={`pb-3 font-semibold ${i===0?'text-left':'text-right'} ${i===5?'w-28':''}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262d]/60">
                {pairRows.map(({ pair, w, l, p, rate }) => (
                  <tr key={pair} className="group hover:bg-[#161b22] transition-colors">
                    <td className="py-3 font-bold text-[#c9d1d9]">{pair}</td>
                    <td className="py-3 text-right text-[#22c55e] font-semibold">{w}</td>
                    <td className="py-3 text-right text-[#ef4444] font-semibold">{l}</td>
                    <td className="py-3 text-right text-[#f59e0b] font-semibold">{p}</td>
                    <td className="py-3 text-right"><Badge v={w+l > 0 ? rate : 0} /></td>
                    <td className="py-3 pl-4">
                      <div className="h-1.5 bg-[#21262d] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${rate}%`, background: rate>=60?'#22c55e':rate>=40?'#f59e0b':'#ef4444' }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

      </div>
    </div>
  )
}

// ── P&L Simulator ─────────────────────────────────────────────────────────────
function PnLSimulator({ wins, losses }: { wins: number; losses: number }) {
  const [tradeSize, setTradeSize] = useState(100)
  const [riskPct,   setRiskPct]   = useState(2)
  const [targetPct, setTargetPct] = useState(3)

  const calc = useMemo(() => {
    const totalTrades   = wins + losses
    const winAmount     = (tradeSize * targetPct) / 100
    const lossAmount    = (tradeSize * riskPct)   / 100
    const grossProfit   = wins   * winAmount
    const grossLoss     = losses * lossAmount
    const net           = grossProfit - grossLoss
    const totalDeployed = totalTrades * tradeSize
    const roi           = totalDeployed > 0 ? (net / totalDeployed) * 100 : 0
    return { winAmount, lossAmount, grossProfit, grossLoss, net, totalDeployed, roi, totalTrades }
  }, [wins, losses, tradeSize, riskPct, targetPct])

  const isProfit = calc.net >= 0
  const netColor = isProfit ? '#22c55e' : '#ef4444'

  const Input = useCallback(({ label, value, onChange, symbol = '$', step = 1 }: {
    label: string; value: number; onChange: (v: number) => void; symbol?: string; step?: number
  }) => (
    <div>
      <p className="text-[10px] text-[#8b949e] uppercase tracking-wide font-medium mb-1.5">{label}</p>
      <div className="flex items-center gap-1.5 bg-[#21262d] border border-[#30363d] rounded-lg px-3 py-2 focus-within:border-[#6366f1] transition-colors">
        <span className="text-[#8b949e] text-xs font-semibold">{symbol}</span>
        <input
          type="number" value={value} step={step} min={0}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="bg-transparent text-white text-sm font-bold w-full outline-none"
        />
      </div>
    </div>
  ), [])

  return (
    <div className="bg-[#161b22] border border-[#30363d] rounded-2xl overflow-hidden">
      <div className="px-5 sm:px-6 py-4 border-b border-[#21262d]">
        <h2 className="text-sm font-semibold text-white">P&L Simulator</h2>
        <p className="text-[11px] text-[#8b949e] mt-0.5">
          Simulate real dollar outcome from your {wins + losses} closed signals.
        </p>
      </div>

      <div className="p-5 sm:p-6 space-y-6">
        {/* Inputs */}
        <div className="grid grid-cols-3 gap-3 sm:gap-4">
          <Input label="Trade Size" value={tradeSize} onChange={setTradeSize} />
          <Input label="Risk % (SL)" value={riskPct} onChange={setRiskPct} symbol="%" step={0.5} />
          <Input label="Target % (TP)" value={targetPct} onChange={setTargetPct} symbol="%" step={0.5} />
        </div>

        {calc.totalTrades === 0 ? (
          <p className="text-[#475569] text-sm text-center py-4">No closed signals yet.</p>
        ) : (
          <>
            {/* Net P&L — big number */}
            <div className="bg-[#0d1117] border border-[#30363d] rounded-xl p-5 text-center">
              <p className="text-[11px] text-[#8b949e] uppercase tracking-widest font-medium mb-2">Net P&L</p>
              <p className="text-5xl font-black tracking-tight" style={{ color: netColor }}>
                {isProfit ? '+' : '−'}${Math.abs(calc.net).toFixed(2)}
              </p>
              <p className="text-[#8b949e] text-xs mt-2">
                from {calc.totalTrades} closed trades · ${tradeSize} each · ROI{' '}
                <span className="font-bold" style={{ color: netColor }}>
                  {isProfit ? '+' : ''}{calc.roi.toFixed(2)}%
                </span>
              </p>
            </div>

            {/* Breakdown grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Gross Profit',   value: `+$${calc.grossProfit.toFixed(2)}`, color: '#22c55e', sub: `${wins} wins × $${calc.winAmount.toFixed(2)}` },
                { label: 'Gross Loss',     value: `-$${calc.grossLoss.toFixed(2)}`,   color: '#ef4444', sub: `${losses} losses × $${calc.lossAmount.toFixed(2)}` },
                { label: 'Capital Used',   value: `$${calc.totalDeployed.toFixed(0)}`, color: '#f59e0b', sub: `${calc.totalTrades} trades × $${tradeSize}` },
                { label: 'Return on Cap',  value: `${isProfit ? '+' : ''}${calc.roi.toFixed(2)}%`, color: netColor, sub: 'net / capital deployed' },
              ].map(({ label, value, color, sub }) => (
                <div key={label} className="bg-[#21262d] rounded-xl p-4">
                  <p className="text-[9px] text-[#8b949e] uppercase tracking-widest font-semibold">{label}</p>
                  <p className="text-lg font-black mt-1" style={{ color }}>{value}</p>
                  <p className="text-[10px] text-[#8b949e] mt-1">{sub}</p>
                </div>
              ))}
            </div>

            {/* Visual P&L bar */}
            <div>
              <div className="flex justify-between text-[11px] text-[#8b949e] mb-1.5">
                <span>Profit  ${calc.grossProfit.toFixed(2)}</span>
                <span>Loss  ${calc.grossLoss.toFixed(2)}</span>
              </div>
              <div className="h-3 bg-[#21262d] rounded-full overflow-hidden flex">
                {calc.grossProfit + calc.grossLoss > 0 && (
                  <>
                    <div className="h-full bg-[#22c55e] rounded-l-full transition-all duration-500"
                      style={{ width: `${(calc.grossProfit / (calc.grossProfit + calc.grossLoss)) * 100}%` }} />
                    <div className="h-full bg-[#ef4444] rounded-r-full transition-all duration-500"
                      style={{ width: `${(calc.grossLoss / (calc.grossProfit + calc.grossLoss)) * 100}%` }} />
                  </>
                )}
              </div>
              <p className="text-[10px] text-[#8b949e] mt-2 text-center">
                Assumptions: each win earns <span className="text-[#22c55e] font-bold">${calc.winAmount.toFixed(2)}</span> · each loss costs <span className="text-[#ef4444] font-bold">${calc.lossAmount.toFixed(2)}</span>
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}


// ── access denied ─────────────────────────────────────────────────────────────
function Blocked() {
  return (
    <div className="min-h-screen bg-[#0d1117] flex items-center justify-center p-8">
      <div className="text-center max-w-sm">
        <div className="w-16 h-16 bg-[#1a1a24] border border-[#30363d] rounded-2xl flex items-center justify-center mx-auto mb-5">
          <svg className="w-8 h-8 text-[#ef4444]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Admin Access Required</h2>
        <p className="text-[#8b949e] text-sm leading-relaxed">
          Set <code className="text-[#a78bfa] bg-[#1a1a24] px-1.5 py-0.5 rounded text-xs">NEXT_PUBLIC_ADMIN_EMAILS</code> in{' '}
          <code className="text-[#a78bfa] bg-[#1a1a24] px-1.5 py-0.5 rounded text-xs">.env.local</code> to your email address.
        </p>
      </div>
    </div>
  )
}

// ── loading skeleton ──────────────────────────────────────────────────────────
function PageSkeleton() {
  return (
    <div className="min-h-screen bg-[#0d1117] p-4 sm:p-8 space-y-6 animate-pulse">
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-48" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-56" />
        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-56" />
      </div>
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-64" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-52" />
        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-52" />
      </div>
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl h-48" />
    </div>
  )
}
