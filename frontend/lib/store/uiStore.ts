import { create } from 'zustand'

interface UiState {
  globalLoading: boolean
  setGlobalLoading: (loading: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  globalLoading: false,
  setGlobalLoading: (loading) => set({ globalLoading: loading }),
}))
