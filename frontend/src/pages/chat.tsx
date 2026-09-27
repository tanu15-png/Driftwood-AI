import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { api, type Me } from '@/lib/api'
import { ApiError, NetworkError } from '@/lib/http'

/**
 * Placeholder chat surface. Exists to prove the auth round-trip: Supabase
 * session → bearer token → FastAPI /me. Replaced by the real chat in Phase 3.
 */
export default function ChatPage() {
  const { user, signOut } = useAuth()
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .me()
      .then((me) => {
        if (!cancelled) setMe(me)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof NetworkError) setError(err.message)
        else if (err instanceof ApiError) setError(`Backend said ${err.status}: ${err.message}`)
        else setError('Unexpected error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-2xl flex-col items-center justify-center gap-6 px-4">
      <h1 className="text-2xl font-semibold tracking-tight">Document Copilot</h1>

      {error ? (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : me ? (
        <p className="text-sm text-muted-foreground">
          Signed in via FastAPI as <span className="font-medium text-foreground">{me.email}</span>
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">Checking your session…</p>
      )}

      <p className="text-sm text-muted-foreground">
        Chat UI arrives in Phase 3. Authenticated user from Supabase:{' '}
        <span className="font-medium text-foreground">{user?.email ?? 'unknown'}</span>
      </p>

      <Button variant="outline" onClick={() => void signOut()}>
        Sign out
      </Button>
    </main>
  )
}
