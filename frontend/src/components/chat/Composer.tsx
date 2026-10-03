import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

export default function Composer({ onSend, onStop, busy = false, disabled = false }: {
  onSend: (text: string) => void
  onStop?: () => void
  busy?: boolean
  disabled?: boolean
}) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (!inputRef.current) return
    inputRef.current.style.height = 'auto'
    inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`
  }, [text])

  return (
    <form className="relative w-full rounded-3xl border border-transparent bg-muted p-3 shadow-sm focus-within:border-zinc-300"
      onSubmit={(event) => {
        event.preventDefault()
        if (!text.trim() || busy || disabled) return
        onSend(text.trim())
        setText('')
      }}>
      <Textarea ref={inputRef} value={text} rows={2} aria-label="Question about the filings"
        placeholder={busy ? 'Working on your question…' : 'Ask anything about the filings'}
        disabled={busy || disabled} onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault()
            event.currentTarget.form?.requestSubmit()
          }
        }}
        className="max-h-52 min-h-16 resize-none border-0 bg-transparent pr-12 text-base shadow-none focus-visible:ring-0 md:text-base" />
      <div className="mt-1 flex items-center justify-between gap-2 px-1">
        <span className="text-xs text-muted-foreground">SEC filings · Answers with evidence</span>
        {busy && onStop ? <Button type="button" size="icon" className="rounded-full" onClick={onStop} aria-label="Stop response"><Square className="size-3.5 fill-current" /></Button>
          : <Button type="submit" size="icon" className="rounded-full" disabled={busy || disabled || !text.trim()} aria-label="Send question"><ArrowUp className="size-5" /></Button>}
      </div>
    </form>
  )
}
