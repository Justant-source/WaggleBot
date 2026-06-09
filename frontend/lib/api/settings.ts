import { get, put } from './client'
import type { PipelineSettings } from '@/lib/types'
export const settingsApi = {
  get: () => get<PipelineSettings>('/api/settings'),
  save: (data: Partial<PipelineSettings>) => put<{ saved: boolean }>('/api/settings', data),
  getCredentials: () => get<Record<string, unknown>>('/api/settings/credentials'),
  saveCredentials: (data: Record<string, unknown>) => put<{ saved: boolean }>('/api/settings/credentials', data),
}
