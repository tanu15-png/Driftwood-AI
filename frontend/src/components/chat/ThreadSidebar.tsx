import { LogOut, MessageSquare, SquarePen, Trash2 } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import ErrorBanner from '@/components/chat/ErrorBanner'
import type { Thread } from '@/lib/api'

export default function ThreadSidebar({ threads, error, email, deletingId, onNew, onSelect, onDelete, onRetry, onSignOut }: {
  threads: Thread[] | null
  error: string | null
  email: string
  deletingId: string | null
  onNew: () => void
  onSelect: () => void
  onDelete: (thread: Thread) => void
  onRetry: () => void
  onSignOut: () => void
}) {
  return <div className="flex h-full flex-col bg-sidebar">
    <div className="space-y-5 px-3 pt-5 pb-4">
      <div className="flex items-center gap-2.5 px-2"><span className="grid size-8 place-items-center rounded-full border bg-white"><MessageSquare className="size-4" /></span><span className="text-sm font-semibold">Document Copilot</span></div>
      <Button variant="ghost" className="w-full justify-start gap-3 rounded-xl" onClick={onNew}><SquarePen className="size-4" />New chat</Button>
    </div>
    <nav aria-label="Past conversations" className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-4">
      <p className="mb-3 px-2 text-xs font-medium text-muted-foreground">Your conversations</p>
      {threads === null && !error && <p className="px-2 text-sm text-muted-foreground">Loading conversations…</p>}
      {error && <div className="space-y-2"><ErrorBanner>{error}</ErrorBanner><Button variant="outline" size="sm" onClick={onRetry}>Retry loading conversations</Button></div>}
      {threads?.length === 0 && <p className="px-2 text-sm text-muted-foreground">Your conversations will appear here.</p>}
      {threads?.map((thread) => <div key={thread.id} className="group relative flex items-center rounded-xl hover:bg-sidebar-accent/60">
        <NavLink to={`/t/${thread.id}`} onClick={onSelect} title={thread.title ?? 'New conversation'}
          className={({ isActive }) => `min-w-0 flex-1 rounded-xl py-2.5 pr-10 pl-3 text-sm ${isActive ? 'bg-sidebar-accent' : ''}`}>
          <span className="block truncate">{thread.title ?? 'New conversation'}</span>
          <time dateTime={thread.updated_at} className="mt-0.5 block text-[11px] text-muted-foreground">{new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(thread.updated_at))}</time>
        </NavLink>
        <Button variant="ghost" size="icon-xs" className="absolute right-2 text-muted-foreground hover:text-destructive md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
          disabled={deletingId !== null} aria-label={`Delete conversation: ${thread.title ?? 'New conversation'}`} title="Delete conversation" onClick={() => onDelete(thread)}><Trash2 className="size-3.5" /></Button>
      </div>)}
    </nav>
    <div className="flex items-center gap-3 border-t p-4">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-zinc-200 text-xs font-semibold">{email.slice(0, 1).toUpperCase()}</span>
      <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium" title={email}>{email}</p><p className="text-[11px] text-muted-foreground">Research workspace</p></div>
      <Button variant="ghost" size="icon-sm" onClick={onSignOut} aria-label="Sign out"><LogOut className="size-4" /></Button>
    </div>
  </div>
}
