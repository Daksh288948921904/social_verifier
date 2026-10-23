export interface Session {
  id: string
  url: string
  source_type: 'youtube_live' | 'direct'
  status: 'starting' | 'capturing' | 'stopped' | 'error'
  created_at: string
  started_at: string | null
  ended_at: string | null
}

export interface NewspaperArticle {
  clip_id: string
  headline: string
  body: string
}

export interface NewspaperSection {
  name: string
  articles: NewspaperArticle[]
}

export interface NewspaperContent {
  masthead: string
  sections: NewspaperSection[]
}

export interface Newspaper {
  session_id: string
  content: string
  created_at: string
}

export interface FullArticle {
  clip_id: string
  article: string
}

export interface Clip {
  id: string
  session_id: string
  title: string
  summary: string
  start_seconds: number
  end_seconds: number
  status: string
  created_at: string
}

export type ClipReelStatus = 'generating' | 'done' | 'error'

export interface ClipReel {
  id: string
  clip_id: string
  status: ClipReelStatus
  hook_text: string | null
  audio_style: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type SessionEvent =
  | { type: 'status'; status: string }
  | { type: 'transcript_tick'; text: string; start: number; end: number }
  | { type: 'segment_boundary_detected'; title: string; summary: string; start: number; end: number }
  | { type: 'clip_ready'; clip_id: string; title: string; video_url: string; thumbnail_url: string }
  | { type: 'error'; message: string }

export type Verdict = 'true' | 'false' | 'misleading' | 'partially true' | 'unverifiable'

export interface ClaimVerification {
  quote: string
  timestamp: string
  claim: string
  verdict: Verdict
  analysis: string
  sources: string[]
  grounded: boolean
  official_sources: string[]
  official_verdict: GovVerdict
  official_analysis: string
  start_seconds: number
  end_seconds: number
}

export type GovVerdict = 'confirmed' | 'contradicted' | 'partially confirmed' | 'not addressed' | 'no source found'

export type ReelCheckStatus =
  | 'queued'
  | 'downloading'
  | 'transcribing'
  | 'extracting_claims'
  | 'verifying_claims'
  | 'concluding'
  | 'done'
  | 'error'

export interface ReelCheck {
  id: string
  url: string
  status: ReelCheckStatus
  progress: string
  manuscript: string | null
  claims: ClaimVerification[]
  conclusion: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type BatchStatus = 'processing' | 'done'

export interface Batch {
  id: string
  status: BatchStatus
  created_at: string
  completed_at: string | null
  checks: ReelCheck[]
}

export interface TimelineItem {
  type: 'claim' | 'upload'
  claim_index: number | null
  upload_id: string | null
}

export interface Timeline {
  check_id: string
  items: TimelineItem[]
}

export interface EditorUpload {
  id: string
  check_id: string
  filename: string
  duration_seconds: number
}

export type EditorExportStatus = 'compiling' | 'done' | 'error'

export interface EditorExport {
  id: string
  check_id: string
  status: EditorExportStatus
  output_path: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type InstagramKitStatus = 'generating' | 'done' | 'error'

export interface InstagramKit {
  id: string
  export_id: string
  check_id: string
  status: InstagramKitStatus
  caption: string | null
  best_time: string | null
  audio_style: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type DebunkScriptStatus = 'generating' | 'done' | 'error'

export interface DebunkBeat {
  claim_index: number
  claim_quote: string
  verdict: Verdict
  reaction_narration: string
  humor_cue: string | null
  question_cue: string | null
}

export interface DebunkScript {
  id: string
  check_id: string
  status: DebunkScriptStatus
  title: string | null
  intro_hook: string | null
  beats: DebunkBeat[]
  outro_cta: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type SearchResultSource = 'youtube' | 'web' | 'instagram'
export type SearchResultStatus = 'pending' | 'fetching' | 'done' | 'error'

export interface SearchResult {
  id: string
  search_id: string
  source: SearchResultSource
  title: string
  url: string
  thumbnail_url: string | null
  description: string
  published_at: string | null
  status: SearchResultStatus
  video_path: string | null
  error_message: string | null
}

export interface SearchResponse {
  search_id: string
  query: string
  results: SearchResult[]
  errors: Record<string, string>
}

export type FootageKeywordStatus = 'idle' | 'queued' | 'searching' | 'analyzing' | 'done' | 'error'

export interface FootageMoment {
  start: number
  end: number
  label: string
  description: string
  fit: string
  score: number
  estimated?: boolean
}

export interface FootageVideo {
  id: string
  video_id: string
  title: string
  channel: string
  thumbnail_url: string | null
  published_at: string | null
  duration_seconds: number | null
  has_transcript: boolean
  analyzed: boolean
  relevance: number | null
  verdict: string
  moments: FootageMoment[]
}

export interface FootageKeyword {
  id: string
  position: number
  text: string
  rationale: string
  status: FootageKeywordStatus
  progress: string
  error_message: string | null
  batch_id: string | null
  completed_at: string | null
  videos: FootageVideo[]
}

export interface FootageSegment {
  id: string
  position: number
  title: string
  summary: string
  visual_needs: string
  script_excerpt: string
  keywords: FootageKeyword[]
}

export interface FootageBatch {
  id: string
  status: 'running' | 'done'
  created_at: string
  completed_at: string | null
  total: number
  finished: number
}

export interface FootageProject {
  id: string
  title: string
  mode: 'script' | 'keywords'
  status: 'analyzing' | 'ready' | 'error'
  error_message: string | null
  created_at: string
  segments: FootageSegment[]
  batches: FootageBatch[]
  keywords_per_wave: number
  clips: FootageClip[]
}

export interface FootageProjectSummary {
  id: string
  title: string
  mode: 'script' | 'keywords'
  status: 'analyzing' | 'ready' | 'error'
  created_at: string
  segment_count: number
  keyword_count: number
  done_keyword_count: number
  video_count: number
}

export interface FootageClip {
  id: string
  video_id: string
  video_title: string
  filename: string
  label: string
  start_seconds: number
  end_seconds: number
  status: 'downloading' | 'done' | 'error'
  error_message: string | null
  created_at: string
}

export interface FootageClipRequest {
  video_id: string
  video_title: string
  segment_position: number
  label: string
  start: number
  end: number
}
