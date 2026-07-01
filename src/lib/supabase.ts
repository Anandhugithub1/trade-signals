import { createBrowserClient } from '@supabase/ssr'

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const isConfigured =
  Boolean(url && key) && url.startsWith('https://') && !url.includes('your_')

export function createClient() {
  return createBrowserClient(url, key)
}

// Singleton for client components
export const supabase = isConfigured ? createClient() : null!
