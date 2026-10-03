import type { Citation, SourcePassage } from '@/lib/chat-types'
import { filingLinks } from '@/lib/filing-links'

export default function CitationEvidence({
  citation, source,
}: { citation: Citation; source: SourcePassage }) {
  const quoteStart = source.chunk_text.indexOf(citation.quote)
  const links = filingLinks(source.source_url, citation.quote)

  return (
    <section aria-label={`Evidence for citation ${citation.id}`} className="space-y-6 p-5 text-sm leading-6">
      <div>
        <h3 className="font-semibold">[{citation.id}] {source.company} ({source.ticker})</h3>
        <p className="text-xs text-muted-foreground">
          {source.filing_type} · FY{source.fiscal_year} · Filed {source.filing_date}
        </p>
        <p className="text-xs text-muted-foreground">
          {source.page !== null ? `Page ${source.page}` : 'Page unavailable (HTML filing)'}
          {' · '}{source.section ?? 'Section unavailable'}
        </p>
      </div>
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Cited excerpt</p>
        <blockquote className="rounded-xl border-l-2 border-zinc-400 bg-muted p-4 whitespace-pre-wrap break-words">{citation.quote}</blockquote>
      </div>
      <details open>
        <summary className="cursor-pointer text-sm font-medium">Full retrieved passage</summary>
        <p className="mt-3 whitespace-pre-wrap break-words text-sm text-zinc-600">
          {quoteStart < 0 ? source.chunk_text : <>
            {source.chunk_text.slice(0, quoteStart)}
            <mark className="bg-amber-200 text-black">{citation.quote}</mark>
            {source.chunk_text.slice(quoteStart + citation.quote.length)}
          </>}
        </p>
      </details>
      {links && <div className="space-y-2 text-xs">
        <a href={links.highlighted ?? links.original} target="_blank" rel="noopener noreferrer" className="text-primary underline">Open original SEC filing ↗</a>
        {links.highlighted && <>
          <p className="text-muted-foreground">Tries to highlight the cited excerpt. If no highlight appears, search the filing for the excerpt above.</p>
          <a href={links.original} target="_blank" rel="noopener noreferrer" className="block text-muted-foreground underline">Open without highlighting ↗</a>
        </>}
      </div>}
    </section>
  )
}
