import { get, post } from './client'
import type { Post, Job, PageResponse } from '@/lib/types'

interface InboxListResponse {
  posts: Post[]
  total: number
  page: number
  size: number
  counts: { tier1: number; tier2: number; tier3: number }
}

export const inboxApi = {
  list: (params?: { page?: number; size?: number }) =>
    get<InboxListResponse>('/api/inbox', params as Record<string, unknown>),
  approve: (id: number) => post<{ postId: number; status: string; jobId: number }>(`/api/inbox/${id}/approve`),
  decline: (id: number) => post<{ postId: number; status: string }>(`/api/inbox/${id}/decline`),
  batch: (ids: number[], action: 'approve' | 'decline') =>
    post<{ processed: number; failed: Array<{ id: number; error: string }>; action: string }>('/api/inbox/batch', { ids, action }),
  analyze: (id: number) => post<{ jobId: number }>(`/api/inbox/${id}/analyze`),
  triggerCrawl: () => post<{ jobId: number }>('/api/inbox/crawl'),
  pollJob: (jobId: number) => get<Job>(`/api/inbox/jobs/${jobId}`),
}
