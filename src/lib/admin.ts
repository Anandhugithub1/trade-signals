/**
 * Admin access check.
 *
 * Set NEXT_PUBLIC_ADMIN_EMAILS in .env.local (comma-separated).
 * Example:
 *   NEXT_PUBLIC_ADMIN_EMAILS=you@example.com,partner@example.com
 *
 * If the env var is empty the check always returns false so no one
 * can access admin routes without explicitly configuring an admin.
 */
export function isAdmin(email: string | null | undefined): boolean {
  if (!email) return false
  const raw = process.env.NEXT_PUBLIC_ADMIN_EMAILS ?? ''
  if (!raw.trim()) return false
  const admins = raw.split(',').map((e) => e.trim().toLowerCase())
  return admins.includes(email.toLowerCase())
}
