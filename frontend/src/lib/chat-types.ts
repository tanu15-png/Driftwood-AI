import type { UIMessage } from 'ai'

export interface Citation {
  id: number
  chunk_id: string
  quote: string
}

export interface SourcePassage {
  id: string
  document_id: string
  chunk_text: string
  ticker: string
  company: string
  fiscal_year: number
  filing_type: string
  filing_date: string
  source_url: string
  page: number | null
  section: string | null
}

export interface CitationSelection {
  messageId: string
  citation: Citation
  source: SourcePassage
}

export type ChatMessage = UIMessage<unknown, {
  citations: Citation[]
  sources: SourcePassage[]
  grounding: { status: 'supported' | 'insufficient_evidence' | 'investment_advice' }
}>
