import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
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
  if (m.includes('already registered')) return 'That email is already registered — sign in instead.'
  if (m.includes('password')) return 'Password must be at least 6 characters.'
  if (m.includes('rate limit')) return 'Too many attempts. Wait a minute and try again.'
  return message
}

export default function SignUpPage() {
  const { session } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [confirmationSent, setConfirmationSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // "Confirm email" is off for local dev, so Supabase signs the user in
  // immediately; send them to the app instead of showing the confirmation note.
  if (session) return <Navigate to="/" replace />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const { error } = await supabase.auth.signUp({ email, password })
      if (error) {
        setError(describeAuthError(error.message))
      } else {
        // With email confirmation on, Supabase returns a session only after
        // the user clicks the link; without it they're signed in above.
        setConfirmationSent(true)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-sm flex-col justify-center gap-6 px-4">
      <header className="space-y-1 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Document Copilot</h1>
        <p className="text-sm text-muted-foreground">Create your workspace account</p>
      </header>

      {confirmationSent ? (
        <p className="text-center text-sm text-muted-foreground">
          Check your inbox — we sent a confirmation link to <strong>{email}</strong>. Then sign in
          below.
        </p>
      ) : (
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
              autoComplete="new-password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && <AuthError>{error}</AuthError>}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? 'Creating account…' : 'Sign up'}
          </Button>
        </form>
      )}

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{' '}
        <Link to="/signin" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </main>
  )
}
