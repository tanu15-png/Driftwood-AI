import { ApiError, NetworkError } from '@/lib/http'

export function errorMessage(err: unknown): string {
  if (err instanceof NetworkError) return 'Could not reach the backend. Check your connection, the server, and its CORS settings.'
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401: return 'Your session expired. Sign in again. (401)'
      case 403: return 'You do not have access to this conversation. (403)'
      case 404: return 'This conversation could not be found. (404)'
      case 422: return 'The question could not be accepted. Try a shorter, non-empty question. (422)'
      case 502: return `${err.message} (502)`
      case 500: return 'The server encountered an unexpected error. Please retry. (500)'
      case 503: return 'Filing retrieval is temporarily unavailable. Please retry later. (503)'
      default: return `Request failed (${err.status}): ${err.message}`
    }
  }
  return err instanceof Error ? err.message : 'Unexpected error'
}
