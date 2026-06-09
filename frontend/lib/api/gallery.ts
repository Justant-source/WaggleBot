import { get, post } from './client'
export const galleryApi = {
  list: (params?: { page?: number; size?: number }) =>
    get<{ items: unknown[]; total: number; page: number }>('/api/gallery', params as Record<string, unknown>),
  hdRender: (id: number) => post<{ jobId: number }>(`/api/gallery/${id}/hd-render`),
  upload: (id: number, platform = 'youtube') =>
    post<{ jobId: number }>(`/api/gallery/${id}/upload`, { platform }),
}
