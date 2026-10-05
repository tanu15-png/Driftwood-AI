import { isTextUIPart } from 'ai'
import { FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import FilingMarkdown from './FilingMarkdown'
import type { ChatMessage, CitationSelection } from '@/lib/chat-types'

export default function MessageBubble({ message, selected, onCitation }: {
  message: ChatMessage
  selected: CitationSelection | null
  onCitation: (selection: CitationSelection) => void
}) {
  const text = message.parts.filter(isTextUIPart).map((part) => part.text).join('')
  const citations = message.parts.find((part) => part.type === 'data-citations')?.data ?? []
  const sources = message.parts.find((part) => part.type === 'data-sources')?.data ?? []
  const grounding = message.parts.find((part) => part.type === 'data-grounding')?.data.status
  const evidence = citations.flatMap((citation) => {
    const source = sources.find((item) => item.id === citation.chunk_id)
    return source ? [{ citation, source }] : []
  })
  const isUser = message.role === 'user'
  const refusal = grounding === 'insufficient_evidence' || grounding === 'investment_advice'

  function citationButton(id: number, label: string, key: string, inline = false) {
    const item = evidence.find((entry) => entry.citation.id === id)
    if (!item) return label
    const active = selected?.messageId === message.id && selected.citation.id === id
    return <Button key={key} variant="ghost" size="xs" type="button"
      className={inline
        ? 'mx-0.5 h-5 rounded-full bg-zinc-100 px-1.5 align-baseline text-[11px] text-zinc-600'
        : 'h-auto max-w-full gap-1.5 rounded-full border bg-white px-3 py-1.5 text-left text-xs whitespace-normal'}
      aria-label={`Open citation ${id}: ${item.source.company}`}
      aria-expanded={active} aria-controls={active ? 'citation-sidebar' : undefined}
      onClick={() => onCitation({ messageId: message.id, ...item })}>
      {!inline && <FileText className="size-3.5 shrink-0 text-muted-foreground" />}{label}
    </Button>
  }

  return (
    <article aria-label={isUser ? 'Your question' : 'Assistant answer'}
      className={isUser ? 'flex justify-end' : 'flex justify-start'}>
      <div className={isUser
        ? 'max-w-[85%] rounded-3xl bg-muted px-5 py-3 text-base leading-7'
        : `min-w-0 w-full text-base leading-7 ${refusal ? 'rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-950' : ''}`}>
        {!isUser && grounding && <p className="mb-3 text-xs font-medium text-muted-foreground">
          {grounding === 'supported' ? 'Cited filing evidence' : grounding === 'insufficient_evidence' ? 'Insufficient filing evidence' : 'Investment advice request declined'}
        </p>}
        {isUser ? <div className="whitespace-pre-wrap break-words">{text}</div>
          : <FilingMarkdown text={text} renderCitation={(id, label, key) => citationButton(id, label, key, true)} />}
        {!isUser && evidence.length > 0 && <div className="mt-5 flex flex-wrap gap-2" aria-label="Citations">
          {evidence.map(({ citation, source }) => citationButton(citation.id,
            `[${citation.id}] ${source.ticker} · ${source.filing_type} FY${source.fiscal_year}`, String(citation.id)))}
        </div>}
        {!isUser && !grounding && evidence.length === 0 && text && <p className="mt-2 text-xs text-muted-foreground">Citation details unavailable for this message.</p>}
      </div>
    </article>
  )
}
