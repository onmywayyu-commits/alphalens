export type Relevance = 'high' | 'medium' | 'low'
export type Verification = 'unverified' | 'verified' | 'disputed'
export type EvidenceLevel = 'fact' | 'opinion' | 'inference'

export interface Account {
  handle: string
}

export interface Company {
  ticker: string
  name: string
}

export interface Evidence {
  id: string
  category: EvidenceLevel
  text: string
  verification: Verification | null
  source_post_ids: string[]
  evidence: string
}

export type ArchiveLinkStatus = 'missing' | 'invalid' | 'profile' | 'other_x_path' | 'status'

export interface ArchiveMedia {
  media_id: string
  original_filename: string
  position: number
  exists: boolean
  availability: 'available' | 'filename_match' | 'missing' | 'outside_archive' |
    'conflict' | 'unreadable' | 'invalid_file' | 'unsupported_extension'
  preview_path: string | null
}

export interface ArchivePost {
  record_id: string
  excel_row: number
  posted_date: string | null
  author_display_name: string | null
  source_author_handle: string | null
  source_verification: 'pending' | 'missing' | 'verified'
  source_url_status: ArchiveLinkStatus
  content_verification: 'pending' | 'verified'
  text_origin_status: 'unknown_manual_entry' | 'original' | 'translation' | 'manual_summary'
  quoted_content: string | null
  quoted_url: string | null
  quoted_url_status: ArchiveLinkStatus
  quoted_author_handle: string | null
  quoted_post_id: string | null
  analysis_status: 'not_analyzed' | 'analyzed'
  analysis_at: string | null
  media: ArchiveMedia[]
}

export interface ArchiveRelation {
  kind: 'shared_post_id' | 'identical_content' | 'numbered_thread_candidate' | 'archive_quote'
  record_ids: string[]
  excel_rows: number[]
}

export interface AnalysisPoint {
  text: string
  evidence_ids: string[]
}

export interface PostAnalysis {
  schema_version: 1
  analysis_status: 'completed'
  record_id: string
  source_record_ids: string[]
  analysis: {
    research_value: 'actionable' | 'background'
    summary: AnalysisPoint | null
    author_opinion: AnalysisPoint | null
    why_it_matters: AnalysisPoint | null
    investment_implication: AnalysisPoint | null
    counterevidence: AnalysisPoint[]
    risk_hypotheses: AnalysisPoint[]
    next_research_actions: AnalysisPoint[]
    related_sectors: string[]
    related_companies: string[]
    related_tickers: string[]
    claim_annotations: (AnalysisPoint & { category: 'fact' | 'opinion'; attribution: string })[]
  }
  evidence: Record<string, {
    kind: 'body' | 'quote' | 'image'
    record_id: string
    excerpt: string
    source_url: string | null
    source_verification: ArchivePost['source_verification']
    content_verification: ArchivePost['content_verification']
    attribution: string | null
    media_id: string | null
  }>
  fact_verification: 'unverified'
  media_analysis_status: 'no_media' | 'not_analyzed' | 'partial' | 'analyzed'
  prompt_version: string
  model_name: string
  generated_at: string
}

export type PostAnalysisExample = Pick<PostAnalysis, 'analysis' | 'evidence' | 'media_analysis_status'>

export interface Post {
  post_id: string | null
  author: string
  source_url: string | null
  published_at: string | null
  collected_at: string | null
  source_type: 'synthetic' | 'manual' | 'official_api'
  content: string
  is_demo: boolean
  title: string | null
  summary: string | null
  industry: string | null
  companies: Company[]
  information_type: string | null
  relevance: Relevance | null
  evidence: Evidence[]
  archive?: ArchivePost
  post_analysis?: PostAnalysis
  post_analysis_example?: PostAnalysisExample
}

export interface Idea {
  id: string
  title: string
  industry: string
  tickers: string[]
  status: string
  hypothesis: string
  supporting_logic: string
  counterargument: string
  catalyst: string
  risk: string
  questions: string[]
  source_post_ids: string[]
  is_demo: boolean
}

export interface Report {
  date: string
  summary: string
  events: string[]
  themes: string[]
  hypotheses: string[]
  questions: string[]
  risks: string[]
  source_post_ids: string[]
  is_demo: boolean
}

export interface BriefPoint {
  text: string
  item_ids: string[]
}

export type ThesisStatus = 'to_validate' | 'strengthened' | 'weakened' | 'invalidated'

export interface SignalCompanyScope {
  direct: string[]
  value_chain: string[]
}

interface DailyBriefV2 {
  schema_version: 2
  lead_insight: {
    title: string
    explanation: string
    related_sectors: string[]
    related_tickers: string[]
    item_ids: string[]
  } | null
  top_signals: {
    event_key: string
    title: string
    core_judgment?: string | null
    company_scope?: SignalCompanyScope | null
    thesis_status?: ThesisStatus | null
    what_happened: string[]
    why_it_matters: string
    investment_implication: string
    bull_case: string[]
    bear_case: string[]
    risks: string
    next_research_action: string
    related_tickers: string[]
    related_sectors: string[]
    selection_reason: string
    source_post_ids: string[]
    verification_status: 'records_verified' | 'partially_verified' | 'pending'
    criteria: Record<string, { level: number; reason: string }>
    evidence_quality: { level: number; reason: string }
  }[]
  research_themes: {
    theme_key: string
    title: string
    current_observation: string
    related_companies: string[]
    item_ids: string[]
    conflicting_item_ids: string[]
    source_count?: number
    history?: { date: string; new_source_count: number }
  }[]
  other_updates: { title: string; record_id: string; industry: string; item_id: string }[]
  limitations: string[]
  source_verification_summary: { verified: number; pending: number; missing: number }
}

export interface BriefRunData {
  daily_v2?: DailyBriefV2
  date: string
  run_id: string
  mode: 'rehearsal' | 'replay' | 'api'
  provider: string
  model: string | null
  generated_at: string
  input_sha256: string
  extraction_sha256: string
  extract_prompt: string
  report_prompt: string
  coverage: {
    record_count: number
    distinct_post_count: number
    source_link_count: number
    verified_source_count: number
    image_count: number
  }
  image_states: { not_read: number; unreadable: number; readable: number }
  records: { record_id: string; excel_row: number; source_verification: ArchivePost['source_verification'] }[]
  brief: {
    summary: BriefPoint | null
    events: BriefPoint[]
    themes: BriefPoint[]
    questions: BriefPoint[]
    risks: BriefPoint[]
    hypotheses: {
      comparison_key: string
      statement: string
      support_item_ids: string[]
      counter_item_ids: string[]
      questions: string[]
    }[]
  }
  evidence: Record<string, {
    category: EvidenceLevel
    text: string
    citations: {
      record_id: string
      excel_row: number
      kind: 'body' | 'quote' | 'image'
      source_verification: ArchivePost['source_verification']
      source_url?: string | null
      source_post_id?: string | null
      excerpt?: string
      media_id?: string
    }[]
  }>
}

export interface Dashboard {
  schema_version: 1
  mode: 'demo' | 'research'
  updated_at: string | null
  accounts: Account[]
  posts: Post[]
  ideas: Idea[]
  reports: Report[]
  relations?: ArchiveRelation[]
  brief_runs?: BriefRunData[]
}
