/**
 * Typed API client for the FastAPI backend. Grows one method per route.
 */

import { apiFetch } from '@/lib/http'

export interface Me {
  id: string
  email: string
}

export const api = {
  me: () => apiFetch<Me>('/me'),
}
