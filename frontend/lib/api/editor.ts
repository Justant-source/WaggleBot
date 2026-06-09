import { get, post, put } from './client'
import type { Post, Content, ScriptData, Job, PageResponse } from '@/lib/types'

interface EditorPostDetail {
  post: Post
  script: ScriptData | null
  maxCharsPerLine: number
  maxBodyItems: number
}

export const editorApi = {
  list: (params?: { page?: number; size?: number }) =>
    get<{ content: Post[]; totalElements: number }>('/api/editor', params as Record<string, unknown>),
  get: (id: number) => get<EditorPostDetail>(`/api/editor/${id}`),
  saveScript: (id: number, script: ScriptData) => put<{ saved: boolean }>(`/api/editor/${id}/script`, script),
  generate: (id: number, opts?: { model?: string; extra_instructions?: string }) =>
    post<{ jobId: number }>(`/api/editor/${id}/generate`, opts),
  ttsPreview: (id: number, opts?: { voice?: string }) =>
    post<{ jobId: number }>(`/api/editor/${id}/tts-preview`, opts),
  confirm: (id: number) => post<{ postId: number; status: string }>(`/api/editor/${id}/confirm`),
  pollJob: (jobId: number) => get<Job>(`/api/editor/jobs/${jobId}`),
}
