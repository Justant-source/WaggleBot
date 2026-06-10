export interface Post {
  id: number
  siteCode: string
  originId: string
  title: string
  content: string | null
  images: unknown | null
  stats: unknown | null
  status: PostStatus
  engagementScore: number
  retryCount: number
  lastError?: string | null
  createdAt: string
  updatedAt: string
}

export type PostStatus =
  | 'COLLECTED' | 'EDITING' | 'APPROVED' | 'PROCESSING'
  | 'PREVIEW_RENDERED' | 'RENDERED' | 'UPLOADED' | 'DECLINED' | 'FAILED'

export interface Content {
  id: number
  postId: number
  summaryText: string | null
  audioPath: string | null
  videoPath: string | null
  uploadMeta: Record<string, unknown> | null
  pipelineState: Record<string, unknown> | null
  createdAt: string
}

export interface ScriptBodyItem {
  type: 'body' | 'comment'
  lineCount: number
  lines: string[]
  author?: string
}

export type Mood =
  | 'humor' | 'touching' | 'anger' | 'sadness'
  | 'horror' | 'info' | 'controversy' | 'daily' | 'shock'

export interface ScriptData {
  hook: string
  body: ScriptBodyItem[]
  closer: string
  titleSuggestion: string
  tags: string[]
  mood: Mood | string
}

export interface LlmLog {
  id: number
  postId: number | null
  callType: string
  modelName: string | null
  strategy: string | null
  imageCount: number
  contentLength: number
  promptText: string | null
  rawResponse: string | null
  parsedResult: unknown | null
  success: boolean
  errorMessage: string | null
  durationMs: number | null
  createdAt: string
}

export type JobStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'ERROR'
export type JobType =
  | 'GENERATE_SCRIPT' | 'TTS_PREVIEW' | 'AI_FITNESS' | 'MANUAL_CRAWL'
  | 'HD_RENDER' | 'UPLOAD' | 'FETCH_YT_ANALYTICS' | 'AI_INSIGHT' | 'FEEDBACK_APPLY'
  | 'AB_CREATE' | 'AB_EVALUATE' | 'AB_APPLY_WINNER'

export interface Job {
  id: number
  jobType: JobType
  postId: number | null
  status: JobStatus
  result: Record<string, unknown> | null
  error: string | null
}

export interface PipelineSettings {
  llm_backend: 'cli' | 'api'
  llm_api_base_url: string
  llm_model: string
  llm_model_overrides: string
  tts_engine: string
  tts_voice: string
  auto_approve_enabled: string | boolean
  auto_approve_threshold: number | string
  auto_upload: string | boolean
  max_chars_per_line: number | string
  [key: string]: unknown
}

export interface PageResponse<T> {
  content: T[]
  totalElements: number
  totalPages: number
  number: number
  size: number
}
