import { create } from 'zustand'
import type { ScriptData } from '@/lib/types'

interface EditorState {
  script: ScriptData | null
  dirty: boolean
  setScript: (script: ScriptData) => void
  updateField: (field: keyof ScriptData, value: unknown) => void
  markClean: () => void
}

export const useEditorStore = create<EditorState>((set) => ({
  script: null,
  dirty: false,
  setScript: (script) => set({ script, dirty: false }),
  updateField: (field, value) =>
    set((s) => ({ script: s.script ? { ...s.script, [field]: value } : s.script, dirty: true })),
  markClean: () => set({ dirty: false }),
}))
