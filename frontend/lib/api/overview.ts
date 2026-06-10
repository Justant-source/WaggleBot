import { get } from './client'
import type { OverviewData } from '@/lib/types'

export const overviewApi = {
  get: (since?: string) =>
    get<OverviewData>('/api/overview', since ? { since } : undefined),
}
