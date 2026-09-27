import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/lib/auth'

/**
 * Auth gate: unauthenticated users never reach chat routes. While the first
 * session lookup is pending we render nothing (avoid flashing the login page
 * for users who are actually signed in).
 */
export function RequireAuth() {
  const { session, loading } = useAuth()
  const location = useLocation()

  if (loading) return null
  if (!session) return <Navigate to="/signin" replace state={{ from: location.pathname }} />
  return <Outlet />
}
