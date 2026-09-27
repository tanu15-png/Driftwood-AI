/**
 * Thin fetch wrapper: absolute base URL, bearer injection, timeout, and typed
 * errors (network vs HTTP) so the UI can distinguish "server down" from
 * "server said no".
 */

import { env } from '@/lib/env'
import { supabase } from '@/lib/supabase'

const DEFAULT_TIMEOUT_MS = 15_000

/** The backend could not be reached at all (down, CORS, offline). */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('Could not reach the server. Is the backend running?')
    this.name = 'NetworkError'
    this.cause = cause
  }
}

/** The backend answered with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function bearerHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Non-JSON body — fall through to the generic message.
  }
  return `Request failed with status ${response.status}`
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${env.apiBaseUrl.replace(/\/$/, '')}${path}`

  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(await bearerHeaders()),
        ...init.headers,
      },
      signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    })
  } catch (cause) {
    throw new NetworkError(cause)
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
