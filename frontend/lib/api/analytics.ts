import { get, post } from './client'
export const analyticsApi = {
  funnel: () => get<Record<string, number>>('/api/analytics/funnel'),
  fetchYt: (postId?: number) => post<{ jobId: number }>('/api/analytics/youtube/fetch', postId ? { postId } : undefined),
  insights: () => post<{ jobId: number }>('/api/analytics/insights'),
  feedbackApply: () => post<{ jobId: number }>('/api/analytics/feedback/apply'),
  abEvaluate: (groupId: string) => post<{ jobId: number }>('/api/analytics/ab/evaluate', { groupId }),
  abApplyWinner: (groupId: string) => post<{ jobId: number }>('/api/analytics/ab/apply-winner', { groupId }),
  pollJob: (jobId: number) => get<{ id: number; status: string; result: unknown }>(`/api/analytics/jobs/${jobId}`),
}
