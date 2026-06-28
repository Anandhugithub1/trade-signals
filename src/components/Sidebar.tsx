'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase'
import { isAdmin } from '@/lib/admin'
import type { User } from '@supabase/supabase-js'

const baseLinks = [
  {
    href: '/',
    label: 'Dashboard',
    adminOnly: false,
    icon: (
      <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    href: '/signals',
    label: 'Signals',
    adminOnly: false,
    icon: (
      <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
  },
  {
    href: '/analytics',
    label: 'Analytics',
    adminOnly: true,
    icon: (
      <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
]

export default function Sidebar() {
  const path = usePathname()
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data }) => setUser(data.user))
    const { data: listener } = supabase.auth.onAuthStateChange((_, session) => {
      setUser(session?.user ?? null)
    })
    return () => listener.subscription.unsubscribe()
  }, [])

  async function handleSignOut() {
    setSigningOut(true)
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  const initials = user?.email ? user.email[0].toUpperCase() : '?'
  const shortEmail = user?.email
    ? user.email.length > 22 ? user.email.slice(0, 20) + '…' : user.email
    : ''
  const admin = isAdmin(user?.email)
  const links = baseLinks.filter((l) => !l.adminOnly || admin)

  return (
    <aside className="w-56 shrink-0 min-h-screen bg-[#13131a] border-r border-[#2a2a3a] flex flex-col">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-[#2a2a3a]">
        <div className="flex items-baseline gap-2">
          <span className="text-base font-bold text-white tracking-tight">TradePilot</span>
          <span className="text-[10px] font-bold text-[#6366f1] bg-[#6366f1]/10 px-1.5 py-0.5 rounded uppercase tracking-widest">
            {admin ? 'Admin' : 'Viewer'}
          </span>
        </div>
        <p className="text-[11px] text-[#475569] mt-0.5">Signal Management</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-0.5">
        {links.map((l) => {
          const active = path === l.href
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-[#6366f1]/15 text-[#818cf8] border border-[#6366f1]/25'
                  : 'text-[#64748b] hover:text-[#94a3b8] hover:bg-[#1f1f2e] border border-transparent'
              }`}
            >
              <span className={active ? 'text-[#818cf8]' : 'text-[#475569]'}>{l.icon}</span>
              {l.label}
              {l.adminOnly && (
                <span className="ml-auto text-[9px] font-bold text-[#6366f1] bg-[#6366f1]/10 px-1.5 py-0.5 rounded">ADMIN</span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* User + logout */}
      <div className="p-3 border-t border-[#2a2a3a]">
        {user && (
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg mb-1">
            <div className="w-7 h-7 rounded-full bg-[#6366f1]/20 border border-[#6366f1]/30 flex items-center justify-center text-[11px] font-bold text-[#818cf8] shrink-0">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-[#94a3b8] truncate">{shortEmail}</p>
              <p className="text-[10px] text-[#334155]">Admin</p>
            </div>
          </div>
        )}
        <button
          onClick={handleSignOut}
          disabled={signingOut}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[#64748b] hover:text-[#ef4444] hover:bg-[#ef4444]/5 transition-all disabled:opacity-50"
        >
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          {signingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
    </aside>
  )
}
