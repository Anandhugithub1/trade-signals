'use client'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

type ToastType = 'error' | 'success' | 'info'

interface Toast {
  id: string
  message: string
  type: ToastType
}

interface ToastCtx {
  toast: (message: string, type?: ToastType) => void
  error: (message: string) => void
  success: (message: string) => void
}

const Ctx = createContext<ToastCtx>({
  toast: () => {},
  error: () => {},
  success: () => {},
})

export function useToast() {
  return useContext(Ctx)
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    clearTimeout(timers.current.get(id))
    timers.current.delete(id)
  }, [])

  const toast = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = Math.random().toString(36).slice(2)
      setToasts((prev) => [...prev.slice(-4), { id, message, type }])
      const timer = setTimeout(() => dismiss(id), 4500)
      timers.current.set(id, timer)
    },
    [dismiss],
  )

  // cleanup on unmount
  useEffect(
    () => () => timers.current.forEach(clearTimeout),
    [],
  )

  return (
    <Ctx.Provider value={{ toast, error: (m) => toast(m, 'error'), success: (m) => toast(m, 'success') }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`
              flex items-start gap-3 px-4 py-3 rounded-xl shadow-xl text-sm font-medium
              pointer-events-auto border
              ${t.type === 'error'
                ? 'bg-[#2a1a1a] border-[#ef4444]/30 text-[#ef4444]'
                : t.type === 'success'
                  ? 'bg-[#0f2a1a] border-[#22c55e]/30 text-[#22c55e]'
                  : 'bg-[#1a1a24] border-[#6366f1]/30 text-[#818cf8]'}
            `}
          >
            <span className="mt-0.5 shrink-0">
              {t.type === 'error'  && '✕'}
              {t.type === 'success' && '✓'}
              {t.type === 'info'   && 'ℹ'}
            </span>
            <span className="flex-1 leading-snug">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

/** Maps a raw Supabase/fetch error to a user-friendly string. */
export function friendlyError(err: unknown): string {
  if (!err) return 'Something went wrong.'
  const msg = err instanceof Error ? err.message : String(err)
  if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('fetch')) {
    return 'Network error — check your connection.'
  }
  if (msg.includes('JWT') || msg.includes('auth') || msg.includes('401')) {
    return 'Session expired — please sign in again.'
  }
  if (msg.includes('permission') || msg.includes('RLS') || msg.includes('policy') || msg.includes('42501')) {
    return 'Permission denied — check your Supabase RLS policies.'
  }
  if (msg.includes('not found') || msg.includes('42P01')) {
    return 'Table not found — run the Supabase setup SQL first.'
  }
  if (msg.includes('duplicate') || msg.includes('23505')) {
    return 'Duplicate entry — this record already exists.'
  }
  // Truncate long raw messages
  return msg.length > 120 ? msg.slice(0, 117) + '…' : msg
}
