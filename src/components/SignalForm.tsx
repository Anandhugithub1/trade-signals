'use client'
import { useState } from 'react'
import type { TradeSignal, SignalDirection, SignalResult } from '@/types/signal'

/**
 * Convert a UTC ISO string to a "YYYY-MM-DDTHH:MM" value in local time.
 * datetime-local inputs have no timezone — they store and read local time.
 * Passing UTC directly causes a shift equal to the user's UTC offset on save.
 */
function toLocalDatetimeInput(isoStr: string): string {
  const d = new Date(isoStr)
  const localMs = d.getTime() - d.getTimezoneOffset() * 60_000
  return new Date(localMs).toISOString().slice(0, 16)
}

interface Props {
  signal?: TradeSignal | null
  onClose: () => void
  onSave: (data: Omit<TradeSignal, 'id'> & { id?: string }) => Promise<void>
}

const COMMON_PAIRS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT', 'DOGEUSDT']

export default function SignalForm({ signal, onClose, onSave }: Props) {
  const [form, setForm] = useState({
    pair: signal?.pair ?? '',
    direction: (signal?.direction ?? 'long') as SignalDirection,
    entry: signal?.entry?.toString() ?? '',
    stop_loss: signal?.stop_loss?.toString() ?? '',
    take_profit: signal?.take_profit?.toString() ?? '',
    confidence: signal?.confidence?.toString() ?? '75',
    timestamp: toLocalDatetimeInput(signal?.timestamp ?? new Date().toISOString()),
    result: (signal?.result ?? 'pending') as SignalResult,
    close_price: signal?.close_price?.toString() ?? '',
    note: signal?.note ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!form.pair.trim() || !form.entry || !form.stop_loss || !form.take_profit) {
      setError('Pair, Entry, Stop Loss and Take Profit are required.')
      return
    }
    setSaving(true)
    try {
      await onSave({
        id: signal?.id,
        pair: form.pair.toUpperCase().trim(),
        direction: form.direction,
        entry: parseFloat(form.entry),
        stop_loss: parseFloat(form.stop_loss),
        take_profit: parseFloat(form.take_profit),
        confidence: parseInt(form.confidence),
        timestamp: new Date(form.timestamp).toISOString(),
        result: form.result,
        close_price: form.close_price ? parseFloat(form.close_price) : null,
        note: form.note.trim() ? form.note.trim().slice(0, 500) : null,
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-2xl w-full max-w-lg shadow-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a3a] sticky top-0 bg-[#1a1a24] z-10">
          <h2 className="text-base font-bold text-white">
            {signal ? 'Edit Signal' : 'New Signal'}
          </h2>
          <button
            onClick={onClose}
            className="text-[#475569] hover:text-white transition-colors p-1 rounded"
          >
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-3 py-2.5 text-sm">
              {error}
            </div>
          )}

          {/* Pair */}
          <div>
            <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
              Pair *
            </label>
            <input
              type="text"
              value={form.pair}
              onChange={(e) => set('pair', e.target.value.toUpperCase())}
              className="w-full bg-[#0f0f13] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#475569] focus:border-[#6366f1] focus:outline-none transition-colors"
              placeholder="e.g. BTCUSDT"
            />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {COMMON_PAIRS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => set('pair', p)}
                  className={`text-[10px] font-semibold px-2 py-1 rounded transition-colors ${
                    form.pair === p
                      ? 'bg-[#6366f1]/20 text-[#818cf8] border border-[#6366f1]/40'
                      : 'bg-[#2a2a3a] text-[#64748b] border border-transparent hover:text-white hover:border-[#3a3a4a]'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Direction */}
          <div>
            <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
              Direction *
            </label>
            <div className="flex gap-2">
              {(['long', 'short'] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => set('direction', d)}
                  className={`flex-1 py-2.5 rounded-lg text-sm font-bold capitalize transition-all ${
                    form.direction === d
                      ? d === 'long'
                        ? 'bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/40'
                        : 'bg-[#ef4444]/15 text-[#ef4444] border border-[#ef4444]/40'
                      : 'bg-[#0f0f13] border border-[#2a2a3a] text-[#475569] hover:border-[#3a3a4a] hover:text-[#94a3b8]'
                  }`}
                >
                  {d === 'long' ? '▲ Long' : '▼ Short'}
                </button>
              ))}
            </div>
          </div>

          {/* Price fields */}
          <div className="grid grid-cols-3 gap-3">
            {(
              [
                { key: 'entry', label: 'Entry *' },
                { key: 'stop_loss', label: 'Stop Loss *' },
                { key: 'take_profit', label: 'Take Profit *' },
              ] as const
            ).map((f) => (
              <div key={f.key}>
                <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
                  {f.label}
                </label>
                <input
                  type="number"
                  step="any"
                  value={form[f.key]}
                  onChange={(e) => set(f.key, e.target.value)}
                  className="w-full bg-[#0f0f13] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#475569] focus:border-[#6366f1] focus:outline-none transition-colors"
                  placeholder="0.00"
                />
              </div>
            ))}
          </div>

          {/* Signal strength + Timestamp */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
                Strength{' '}
                <span className="text-[#6366f1] normal-case">{form.confidence}%</span>
              </label>
              <input
                type="range"
                min="1"
                max="100"
                value={form.confidence}
                onChange={(e) => set('confidence', e.target.value)}
                className="w-full accent-[#6366f1] mt-1"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
                Timestamp *
              </label>
              <input
                type="datetime-local"
                value={form.timestamp}
                onChange={(e) => set('timestamp', e.target.value)}
                className="w-full bg-[#0f0f13] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-white focus:border-[#6366f1] focus:outline-none transition-colors"
              />
            </div>
          </div>

          {/* Result */}
          <div>
            <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
              Result
            </label>
            <div className="flex gap-2">
              {(['pending', 'win', 'loss', 'expired'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => set('result', r)}
                  className={`flex-1 py-2 rounded-lg text-xs font-bold capitalize transition-all ${
                    form.result === r
                      ? r === 'win'
                        ? 'bg-[#22c55e]/15 text-[#22c55e] border border-[#22c55e]/40'
                        : r === 'loss'
                          ? 'bg-[#ef4444]/15 text-[#ef4444] border border-[#ef4444]/40'
                          : r === 'expired'
                            ? 'bg-[#64748b]/15 text-[#94a3b8] border border-[#64748b]/40'
                            : 'bg-amber-500/15 text-amber-400 border border-amber-500/40'
                      : 'bg-[#0f0f13] border border-[#2a2a3a] text-[#475569] hover:border-[#3a3a4a] hover:text-[#94a3b8]'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {/* Note — main reason for the trade */}
          <div>
            <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
              Note{' '}
              <span className="text-[#475569] normal-case">{form.note.length}/500</span>
            </label>
            <textarea
              value={form.note}
              onChange={(e) => set('note', e.target.value.slice(0, 500))}
              maxLength={500}
              rows={3}
              className="w-full bg-[#0f0f13] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#475569] focus:border-[#6366f1] focus:outline-none transition-colors resize-none"
              placeholder="Main reason for this trade (e.g. ADX confirms uptrend; EMA200/EMA50 aligned bullish; MACD bullish momentum)"
            />
          </div>

          {/* Close price — only when result is not pending */}
          {form.result !== 'pending' && (
            <div>
              <label className="block text-xs font-semibold text-[#94a3b8] mb-1.5 uppercase tracking-wider">
                Close Price
              </label>
              <input
                type="number"
                step="any"
                value={form.close_price}
                onChange={(e) => set('close_price', e.target.value)}
                className="w-full bg-[#0f0f13] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#475569] focus:border-[#6366f1] focus:outline-none transition-colors"
                placeholder="Actual close price"
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-lg text-sm font-semibold text-[#64748b] bg-[#0f0f13] border border-[#2a2a3a] hover:border-[#3a3a4a] hover:text-[#94a3b8] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 py-2.5 rounded-lg text-sm font-bold text-white bg-[#6366f1] hover:bg-[#4f46e5] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? 'Saving…' : signal ? 'Update Signal' : 'Create Signal'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
