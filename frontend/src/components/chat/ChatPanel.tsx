import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CitationSidebar from '@/components/chat/CitationSidebar'
import Composer from '@/components/chat/Composer'
import ErrorBanner from '@/components/chat/ErrorBanner'
import MessageBubble from '@/components/chat/MessageBubble'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import type { ChatMessage, CitationSelection } from '@/lib/chat-types'
import { env } from '@/lib/env'
import { errorMessage } from '@/lib/error-message'

export default function ChatPanel({ threadId, draft, onTurnFinished }: {
  threadId: string
  draft: string | null
  onTurnFinished: () => void
}) {
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [selection, setSelection] = useState<CitationSelection | null>(null)
  const closeEvidence = useCallback(() => setSelection(null), [])
  const navigate = useNavigate()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [transport] = useState(() => new DefaultChatTransport<ChatMessage>({
    api: `${env.apiBaseUrl}/chat/stream`,
    fetch: api.chatFetch,
    prepareSendMessagesRequest: ({ messages }) => ({ body: { threadId, messages } }),
  }))
  const { messages, sendMessage, setMessages, status, error, stop, regenerate, clearError } = useChat<ChatMessage>({
    transport,
    onFinish: ({ isAbort, isError, isDisconnect }) => {
      if (!isAbort && !isError && !isDisconnect) onTurnFinished()
    },
  })
  useEffect(() => {
    let cancelled = false
    api.threadMessages(threadId).then((rows) => {
      if (!cancelled) {
        setMessages(rows)
        setHistoryLoaded(true)
      }
    }).catch((err: unknown) => { if (!cancelled) setHistoryError(errorMessage(err)) })
    return () => { cancelled = true }
  }, [threadId, setMessages])
  useEffect(() => () => { void stop() }, [stop])
  const sentDraft = useRef(false)
  useEffect(() => {
    if (sentDraft.current || !draft || !historyLoaded) return
    sentDraft.current = true
    void sendMessage({ text: draft })
    navigate(`/t/${threadId}`, { replace: true, state: null })
  }, [draft, historyLoaded, sendMessage, navigate, threadId])
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])
  const busy = status === 'submitted' || status === 'streaming'
  const streamError = status === 'error' && error ? errorMessage(error) : null

  return <div className="flex min-h-0 flex-1">
    <section className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-5">
        <div className="mx-auto max-w-3xl space-y-9 pt-8 pb-12">
          {!historyLoaded && !historyError && <p className="text-sm text-muted-foreground">Loading conversation…</p>}
          {historyError && <div className="space-y-2"><ErrorBanner>{historyError}</ErrorBanner><Button variant="outline" onClick={() => navigate(0)}>Reload conversation</Button></div>}
          {historyLoaded && messages.length === 0 && !busy && <p className="pt-20 text-center text-muted-foreground">Ask about the filings. Open any citation to inspect its source.</p>}
          {messages.map((message) => <MessageBubble key={message.id} message={message} selected={selection} onCitation={setSelection} />)}
          {status === 'submitted' && <p role="status" className="animate-pulse text-sm text-muted-foreground">Searching the filings and checking evidence…</p>}
        </div>
      </div>
      <footer className="px-5 pt-2 pb-3">
        <div className="mx-auto max-w-3xl">
          {streamError && <div className="mb-3 space-y-2"><ErrorBanner>{`Latest request failed: ${streamError}`}</ErrorBanner><div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => { closeEvidence(); clearError(); void regenerate() }}>Retry</Button>
            <Button variant="ghost" size="sm" onClick={clearError}>Dismiss</Button>
          </div></div>}
          <Composer disabled={!historyLoaded} busy={busy} onStop={() => { void stop() }} onSend={(text) => { clearError(); void sendMessage({ text }) }} />
          <p className="mt-2 text-center text-[11px] text-muted-foreground">Verify answers against the cited filings. Research, not investment advice.</p>
        </div>
      </footer>
    </section>
    <CitationSidebar selection={selection} onClose={closeEvidence} />
  </div>
}
