/**
 * Typed API client for the FastAPI backend. Grows one method per route.
 */

import { apiFetch } from '@/lib/http'

export interface Me {
  id: string
  email: string
}

export interface Thread {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export const api = {
  me: () => apiFetch<Me>('/me'),
  listThreads: () => apiFetch<Thread[]>('/threads'),
  createThread: (title?: string) =>
    apiFetch<Thread>('/threads', { method: 'POST', body: JSON.stringify({ title }) }),
  threadMessages: (threadId: string) =>
    apiFetch<unknown[]>(`/threads/${threadId}/messages`),
}
