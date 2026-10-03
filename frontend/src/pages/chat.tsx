import { PanelLeft, MessageSquare, ArrowUpRight } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import ChatPanel from '@/components/chat/ChatPanel'
import Composer from '@/components/chat/Composer'
import DeleteChatDialog from '@/components/chat/DeleteChatDialog'
import ThreadSidebar from '@/components/chat/ThreadSidebar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { useAuth } from '@/lib/auth'
import { api, type Thread } from '@/lib/api'
import { errorMessage } from '@/lib/error-message'

const suggestions = [
  { title: 'Apple revenue mix', question: "Compare Apple's iPhone and Services revenue in fiscal 2024." },
  { title: 'Microsoft cloud growth', question: "What did Microsoft disclose about Azure growth in fiscal 2024?" },
  { title: 'NVIDIA demand', question: "What does NVIDIA's latest 10-K say about Data Center demand?" },
  { title: 'Amazon operating income', question: "Compare AWS and North America operating income in Amazon's fiscal 2024 filing." },
]

export default function ChatPage() {
  const { user, signOut } = useAuth()
  const { threadId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [threadsError, setThreadsError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  const [showSidebar, setShowSidebar] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<Thread | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refreshThreads = useCallback(() => setRefreshKey((value) => value + 1), [])
  useEffect(() => {
    let cancelled = false
    api.listThreads().then((rows) => {
      if (!cancelled) { setThreads(rows); setThreadsError(null) }
    }).catch((err: unknown) => { if (!cancelled) setThreadsError(errorMessage(err)) })
    return () => { cancelled = true }
  }, [refreshKey])

  async function startThread(text: string) {
    setCreating(true)
    try {
      const thread = await api.createThread()
      navigate(`/t/${thread.id}`, { state: { draft: text }, replace: true })
      refreshThreads()
    } catch (err: unknown) { setThreadsError(errorMessage(err)) }
    finally { setCreating(false) }
  }
  async function deleteThread(thread: Thread) {
    setMobileNav(false)
    setDeleteTarget(null)
    setDeletingId(thread.id)
    if (thread.id === threadId) navigate('/', { replace: true })
    try {
      await api.deleteThread(thread.id)
      setThreads((rows) => rows?.filter((row) => row.id !== thread.id) ?? null)
      refreshThreads()
    } catch (err: unknown) { setThreadsError(errorMessage(err)) }
    finally { setDeletingId(null) }
  }
  const sidebar = <ThreadSidebar threads={threads} error={threadsError} email={user?.email ?? ''}
    deletingId={deletingId} onNew={() => { setMobileNav(false); navigate('/') }}
    onSelect={() => setMobileNav(false)} onDelete={setDeleteTarget}
    onRetry={() => { setThreadsError(null); refreshThreads() }} onSignOut={() => { void signOut() }} />

  return <div className="flex h-svh overflow-hidden bg-white">
    {showSidebar && <aside className="hidden w-64 shrink-0 md:block">{sidebar}</aside>}
    <Sheet open={mobileNav} onOpenChange={setMobileNav}>
      <SheetContent side="left" className="gap-0 bg-sidebar p-0 data-[side=left]:w-72">
        <SheetTitle className="sr-only">Conversations</SheetTitle>
        <SheetDescription className="sr-only">Open, create, or delete your conversations.</SheetDescription>
        {sidebar}
      </SheetContent>
    </Sheet>
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-16 shrink-0 items-center gap-2 px-4">
        <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open conversations" onClick={() => setMobileNav(true)}><PanelLeft className="size-5" /></Button>
        <Button variant="ghost" size="icon-sm" className="hidden md:inline-flex" aria-label={showSidebar ? 'Hide conversations' : 'Show conversations'} onClick={() => setShowSidebar(!showSidebar)}><PanelLeft className="size-5" /></Button>
        <span className="text-lg font-semibold tracking-tight">Document Copilot</span>
        <span className="ml-auto rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground">SEC research</span>
      </header>
      {threadId ? <ChatPanel key={threadId} threadId={threadId}
        draft={(location.state as { draft?: string } | null)?.draft ?? null} onTurnFinished={refreshThreads} />
        : <section className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-5 pb-16">
          <div className="w-full max-w-3xl space-y-7">
            <div className="space-y-3 text-center">
              <span className="mx-auto grid size-12 place-items-center rounded-2xl border"><MessageSquare className="size-6" /></span>
              <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">What would you like to know?</h1>
              <p className="text-sm text-muted-foreground">Explore the filings. Follow the evidence.</p>
            </div>
            <Composer busy={creating} onSend={(text) => { void startThread(text) }} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {suggestions.map((item) => <button key={item.title} type="button" disabled={creating}
                className="flex items-center justify-between gap-3 rounded-2xl border p-4 text-left transition-colors hover:bg-muted disabled:opacity-50"
                onClick={() => { void startThread(item.question) }}><span className="text-sm">{item.title}</span><ArrowUpRight className="size-4 text-muted-foreground" /></button>)}
            </div>
            <p className="text-center text-xs text-muted-foreground">Apple · Amazon · Alphabet · Microsoft · NVIDIA</p>
          </div>
        </section>}
    </main>
    <DeleteChatDialog thread={deleteTarget} onClose={() => setDeleteTarget(null)} onConfirm={(thread) => { void deleteThread(thread) }} />
  </div>
}
