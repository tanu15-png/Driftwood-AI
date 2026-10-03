import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import CitationEvidence from '@/components/chat/CitationEvidence'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import type { CitationSelection } from '@/lib/chat-types'

export default function CitationSidebar({ selection, onClose }: {
  selection: CitationSelection | null
  onClose: () => void
}) {
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1280px)').matches)
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1280px)')
    const update = () => setDesktop(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (!selection || !desktop) return
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [selection, desktop, onClose])

  if (!selection) return null
  if (!desktop) return <Sheet open onOpenChange={(open) => { if (!open) onClose() }}>
    <SheetContent id="citation-sidebar" side="right" className="gap-0 data-[side=right]:w-full sm:max-w-md">
      <SheetHeader className="border-b pb-4 pr-12">
        <SheetTitle>Source evidence</SheetTitle>
        <SheetDescription>Verify this claim against the filing.</SheetDescription>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto"><CitationEvidence key={`${selection.messageId}-${selection.citation.id}`} {...selection} /></div>
    </SheetContent>
  </Sheet>

  return <aside id="citation-sidebar" aria-label="Source evidence" className="flex h-full w-96 shrink-0 flex-col border-l bg-white 2xl:w-[420px]">
    <header className="flex items-center justify-between border-b px-5 py-4">
      <div><h2 className="font-semibold">Source evidence</h2><p className="text-xs text-muted-foreground">Verify this claim against the filing.</p></div>
      <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close citation sidebar"><X className="size-4" /></Button>
    </header>
    <div className="min-h-0 flex-1 overflow-y-auto"><CitationEvidence key={`${selection.messageId}-${selection.citation.id}`} {...selection} /></div>
  </aside>
}
