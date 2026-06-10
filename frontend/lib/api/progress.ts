import { get, post } from './client'
import type { Post, ProcessingPost } from '@/lib/types'

export const progressApi = {
  get: () => get<{ counts: Record<string, number>; processing: ProcessingPost[]; failed: Post[] }>('/api/progress'),
  retry: (id: number) => post<{ postId: number; status: string }>(`/api/progress/${id}/retry`),
}
