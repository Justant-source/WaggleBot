import { get, post } from './client'

export interface PerformanceRow {
  postId: number
  title: string
  videoId: string | null
  analytics: { views: number; likes: number; comments: number }
}

export const analyticsApi = {
  funnel: () => get<Record<string, number>>('/api/analytics/funnel'),
  performance: (limit = 20) => get<PerformanceRow[]>(`/api/analytics/performance?limit=${limit}`),
  fetchYt: (postId?: number) => post<{ jobId: number }>('/api/analytics/youtube/fetch', postId ? { postId } : undefined),
  insights: () => post<{ jobId: number }>('/api/analytics/insights'),
  feedbackApply: () => post<{ jobId: number }>('/api/analytics/feedback/apply'),
  abCreate: (name: string, presetA: string, presetB: string) =>
    post<{ jobId: number }>('/api/analytics/ab/create', { name, presetA, presetB }),
  abEvaluate: (groupId: string) => post<{ jobId: number }>('/api/analytics/ab/evaluate', { groupId }),
  abApplyWinner: (groupId: string) => post<{ jobId: number }>('/api/analytics/ab/apply-winner', { groupId }),
  pollJob: (jobId: number) => get<{ id: number; status: string; result: unknown }>(`/api/analytics/jobs/${jobId}`),
}
