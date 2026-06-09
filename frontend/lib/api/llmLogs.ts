import { get } from './client'
import type { LlmLog, PageResponse } from '@/lib/types'
export const llmLogsApi = {
  list: (params?: { page?: number; size?: number; callType?: string; postId?: number; success?: boolean }) =>
    get<{ content: LlmLog[]; totalElements: number; totalPages: number }>('/api/llm-logs', params as Record<string, unknown>),
  get: (id: number) => get<LlmLog>(`/api/llm-logs/${id}`),
}
