/**
 * Typed API client for the FastAPI backend. Grows one method per route.
 */

import { apiFetch, authenticatedFetch } from '@/lib/http'
import type { ChatMessage } from '@/lib/chat-types'

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
  chatFetch: authenticatedFetch,
  me: () => apiFetch<Me>('/me'),
  listThreads: () => apiFetch<Thread[]>('/threads'),
  createThread: (title?: string) =>
    apiFetch<Thread>('/threads', { method: 'POST', body: JSON.stringify({ title }) }),
  deleteThread: (threadId: string) => apiFetch<void>(`/threads/${threadId}`, { method: 'DELETE' }),
  threadMessages: (threadId: string) =>
    apiFetch<ChatMessage[]>(`/threads/${threadId}/messages`),
}
