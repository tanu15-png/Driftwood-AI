import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { supabase } from '@/lib/supabase'

const field =
  'flex w-full flex-col gap-1.5 [&>label]:text-sm [&>label]:font-medium [&>label]:text-foreground'

function AuthError({ children }: { children: string }) {
  return (
    <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {children}
    </p>
  )
}

/** Map Supabase's raw auth messages to plain analyst-facing copy. */
function describeAuthError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login')) return 'Wrong email or password.'
  if (m.includes('email not confirmed')) return 'Please confirm your email first.'
  if (m.includes('rate limit')) return 'Too many attempts. Wait a minute and try again.'
  return message
}

export default function SignInPage() {
  const { session, loading } = useAuth()
  const location = useLocation()
  // RequireAuth passes the route the user was trying to reach; land there.
  const from = (location.state as { from?: string } | null)?.from ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Covers both "already signed in" and "just signed in": onAuthStateChange
  // flips the session, this re-renders, and the router moves into the app.
  if (!loading && session) return <Navigate to={from} replace />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) setError(describeAuthError(error.message))
      // Success: the session redirect above handles navigation.
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-sm flex-col justify-center gap-6 px-4">
      <header className="space-y-1 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Document Copilot</h1>
        <p className="text-sm text-muted-foreground">Sign in to your workspace</p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className={field}>
          <label htmlFor="email">Email</label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="analyst@example.com"
          />
        </div>
        <div className={field}>
          <label htmlFor="password">Password</label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <AuthError>{error}</AuthError>}

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        No account?{' '}
        <Link to="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign up
        </Link>
      </p>
    </main>
  )
}
