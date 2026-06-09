import { create } from 'zustand'
import type { Post } from '@/lib/types'

interface InboxState {
  selectedIds: Set<number>
  page: number
  toggleSelect: (id: number) => void
  selectAll: (posts: Post[]) => void
  clearSelection: () => void
  setPage: (page: number) => void
}

export const useInboxStore = create<InboxState>((set) => ({
  selectedIds: new Set(),
  page: 0,
  toggleSelect: (id) => set((s) => {
    const next = new Set(s.selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return { selectedIds: next }
  }),
  selectAll: (posts) => set({ selectedIds: new Set(posts.map((p) => p.id)) }),
  clearSelection: () => set({ selectedIds: new Set() }),
  setPage: (page) => set({ page }),
}))
