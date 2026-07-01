import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'
import ConditionalShell from '@/components/ConditionalShell'
import { ToastProvider } from '@/components/Toast'

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] })
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'TradePilot Admin',
  description: 'Trade signals management dashboard',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body className="min-h-screen bg-[#0f0f13] text-white antialiased">
        <ToastProvider>
          <ConditionalShell>{children}</ConditionalShell>
        </ToastProvider>
      </body>
    </html>
  )
}
