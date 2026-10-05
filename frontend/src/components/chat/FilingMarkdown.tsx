import { Children, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatFilingTables } from '@/lib/filing-tables'

export default function FilingMarkdown({ text, highlight, renderCitation }: {
  text: string
  highlight?: string
  renderCitation?: (id: number, label: string, key: string) => ReactNode
}) {
  function inline(children: ReactNode): ReactNode {
    return Children.map(children, (child, index) => {
      if (typeof child !== 'string') return child
      const parts = renderCitation ? child.split(/(\[\d+\])/g) : [child]
      return parts.map((part, partIndex) => {
        const key = `${index}-${partIndex}`
        const citation = /^\[(\d+)\]$/.exec(part)
        if (citation && renderCitation) return renderCitation(Number(citation[1]), part, key)
        if (!highlight || !part.trim()) return part
        const start = part.indexOf(highlight)
        if (start >= 0) return <span key={key}>{part.slice(0, start)}<mark className="bg-amber-200 text-black">{highlight}</mark>{part.slice(start + highlight.length)}</span>
        // A quoted table row becomes several cells after formatting.
        if (highlight.includes(part.trim())) return <mark key={key} className="bg-amber-200 text-black">{part}</mark>
        return part
      })
    })
  }

  return <div className="min-w-0 space-y-3 break-words">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      p: ({ children }) => <p className="whitespace-pre-wrap">{inline(children)}</p>,
      table: ({ children }) => <div className="max-w-full overflow-x-auto rounded-lg border"><table className="w-full border-collapse text-left text-sm leading-6">{children}</table></div>,
      th: ({ children }) => <th className="border-b border-r bg-muted px-3 py-2 align-top font-semibold last:border-r-0">{inline(children)}</th>,
      td: ({ children }) => <td className="min-w-24 border-b border-r px-3 py-2 align-top last:border-r-0">{inline(children)}</td>,
      tr: ({ children }) => <tr className="even:bg-muted/40">{children}</tr>,
      ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
      li: ({ children }) => <li>{inline(children)}</li>,
      strong: ({ children }) => <strong>{inline(children)}</strong>,
      em: ({ children }) => <em>{inline(children)}</em>,
      h1: ({ children }) => <h1 className="text-xl font-semibold">{inline(children)}</h1>,
      h2: ({ children }) => <h2 className="text-lg font-semibold">{inline(children)}</h2>,
      h3: ({ children }) => <h3 className="font-semibold">{inline(children)}</h3>,
      a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a>,
    }}>{formatFilingTables(text)}</ReactMarkdown>
  </div>
}
