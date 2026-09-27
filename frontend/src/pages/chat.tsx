import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, isTextUIPart, type UIMessage } from 'ai'
import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { api, type Thread } from '@/lib/api'
import { env } from '@/lib/env'
import { ApiError, NetworkError } from '@/lib/http'

function errorMessage(err: unknown): string {
  if (err instanceof NetworkError) return err.message
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Your session expired — sign in again.'
    if (err.status === 403) return 'You do not have access to this thread.'
    if (err.status === 404) return 'Thread not found.'
    return `Backend said ${err.status}: ${err.message}`
  }
  return err instanceof Error ? err.message : 'Unexpected error'
}

function ErrorBanner({ children }: { children: string }) {
  return (
    <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {children}
    </p>
  )
}

function MessageBubble({ message }: { message: UIMessage }) {
  const text = message.parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join('')
  const isUser = message.role === 'user'

  return (
    <div className={isUser ? 'flex justify-end' : 'flex justify-start'}>
      <div
        className={
          isUser
            ? 'max-w-[80%] rounded-2xl bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground'
            : 'max-w-[80%] rounded-2xl bg-muted px-4 py-2 text-sm whitespace-pre-wrap'
        }
      >
        {text}
      </div>
    </div>
  )
}

const field =
  'flex w-full flex-col gap-1.5 [&>label]:text-sm [&>label]:font-medium [&>label]:text-foreground'

/**
 * One active conversation: loads persisted history, streams replies via
 * /chat/stream. Remounted (keyed) on every thread switch, so useChat state
 * never leaks between threads.
 */
function ChatPanel({
  threadId,
  draft,
  onTurnFinished,
}: {
  threadId: string
  draft: string | null
  onTurnFinished: () => void
}) {
  const [text, setText] = useState('')
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // One transport per panel instance; it closes over this thread's id.
  const [transport] = useState(
    () =>
      new DefaultChatTransport({
        api: `${env.apiBaseUrl}/chat/stream`,
        prepareSendMessagesRequest: ({ messages }) => ({
          // Backend persists the last message and streams the reply.
          body: { threadId, messages },
        }),
      }),
  )

  const { messages, sendMessage, setMessages, status, stop, regenerate, clearError } = useChat({
    transport,
    onError: (err) => setStreamError(err.message),
    // Sidebar ordering/title refresh after each completed turn.
    onFinish: () => onTurnFinished(),
  })

  // Load persisted history once per thread (panel is keyed by threadId, so
  // state resets on switch — no manual error clearing needed).
  useEffect(() => {
    let cancelled = false
    api
      .threadMessages(threadId)
      .then((raw) => {
        if (!cancelled) setMessages(raw as UIMessage[])
      })
      .catch((err: unknown) => {
        if (!cancelled) setHistoryError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [threadId, setMessages])

  // First message of a brand-new thread: ChatPage created the thread and
  // handed us the text; send it exactly once.
  const sentDraftRef = useRef(false)
  useEffect(() => {
    if (sentDraftRef.current || !draft) return
    sentDraftRef.current = true
    void sendMessage({ text: draft })
  }, [draft, sendMessage])

  // Keep the newest message in view while streaming.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  const streaming = status === 'submitted' || status === 'streaming'

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {historyError && <ErrorBanner>{historyError}</ErrorBanner>}
        {messages.length === 0 && !historyError && !streaming && (
          <p className="pt-24 text-center text-sm text-muted-foreground">
            Ask a question about the filings. Grounded answers with citations arrive in Phase 6.
          </p>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {status === 'submitted' && (
          <p className="text-sm text-muted-foreground">Assistant is thinking…</p>
        )}
      </div>

      <footer className="border-t p-3">
        {streamError && (
          <div className="mb-2 flex items-center gap-2">
            <ErrorBanner>{`Stream failed: ${streamError}`}</ErrorBanner>
            <Button variant="outline" size="sm" onClick={() => void regenerate()}>
              Retry
            </Button>
            <Button variant="ghost" size="sm" onClick={clearError}>
              Dismiss
            </Button>
          </div>
        )}
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            const value = text.trim()
            if (!value || streaming) return
            setStreamError(null)
            void sendMessage({ text: value })
            setText('')
          }}
        >
          <Input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={streaming ? 'Assistant is replying…' : 'Ask about the filings…'}
            disabled={streaming}
          />
          {streaming ? (
            <Button type="button" variant="outline" onClick={stop}>
              Stop
            </Button>
          ) : (
            <Button type="submit" disabled={!text.trim()}>
              Send
            </Button>
          )}
        </form>
        {streaming && status === 'streaming' && (
          <p className="mt-1 text-xs text-muted-foreground">Streaming…</p>
        )}
      </footer>
    </section>
  )
}

function ChatPageInner() {
  const { user, signOut } = useAuth()
  const { threadId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [threadsError, setThreadsError] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [creating, setCreating] = useState(false)

  // Bumping this re-runs the sidebar fetch effect.
  const [refreshKey, setRefreshKey] = useState(0)
  const refreshThreads = useCallback(() => setRefreshKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    api
      .listThreads()
      .then((rows) => {
        if (!cancelled) {
          setThreads(rows)
          setThreadsError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setThreadsError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  // First message of a brand-new thread: create it, pass the text as a draft.
  async function startThread(value: string) {
    setCreating(true)
    try {
      const thread = await api.createThread()
      navigate(`/t/${thread.id}`, { state: { draft: value }, replace: true })
      refreshThreads()
    } catch (err: unknown) {
      setThreadsError(errorMessage(err))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex min-h-svh">
      <aside className="flex w-64 shrink-0 flex-col border-r bg-sidebar">
        <div className="p-3">
          <Button className="w-full" onClick={() => navigate('/')}>
            New chat
          </Button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-2 pb-2">
          {threads === null && (
            <p className="px-2 py-1 text-sm text-muted-foreground">Loading threads…</p>
          )}
          {threadsError && <ErrorBanner>{threadsError}</ErrorBanner>}
          {threads?.length === 0 && (
            <p className="px-2 py-1 text-sm text-muted-foreground">No conversations yet.</p>
          )}
          {threads?.map((thread) => (
            <NavLink
              key={thread.id}
              to={`/t/${thread.id}`}
              className={({ isActive }) =>
                `block truncate rounded-md px-2 py-1.5 text-sm ${
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                }`
              }
              title={thread.title ?? 'Untitled'}
            >
              {thread.title ?? 'Untitled'}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 border-t p-3 text-sm">
          <p className="truncate text-muted-foreground" title={user?.email ?? ''}>
            {user?.email}
          </p>
          <Button variant="outline" size="sm" className="w-full" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </aside>

      {threadId ? (
        <ChatPanel
          key={threadId}
          threadId={threadId}
          draft={(location.state as { draft?: string } | null)?.draft ?? null}
          onTurnFinished={() => refreshThreads()}
        />
      ) : (
        <section className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-4">
          <h1 className="text-2xl font-semibold tracking-tight">Document Copilot</h1>
          <form
            className="w-full max-w-md space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              const value = text.trim()
              if (!value || creating) return
              void startThread(value)
            }}
          >
            <div className={field}>
              <label htmlFor="new-question">Start a new conversation</label>
              <Input
                id="new-question"
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="Ask about the filings…"
                disabled={creating}
              />
            </div>
            <Button type="submit" className="w-full" disabled={!text.trim() || creating}>
              {creating ? 'Creating thread…' : 'Ask'}
            </Button>
          </form>
        </section>
      )}
    </div>
  )
}

export default function ChatPage() {
  return <ChatPageInner />
}
