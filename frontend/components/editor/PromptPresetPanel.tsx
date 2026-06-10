'use client'

import { useEffect, useRef, useState } from 'react'
import { editorApi } from '@/lib/api/editor'
import { Button } from '@/components/ui/button'
import { Loader2, Sparkles } from 'lucide-react'
import type { PromptPreset } from '@/lib/types'

interface Props {
  postId: number
  initialInstructions?: string | null
  onGenerate: (instructions: string) => void
  isGenerating: boolean
}

export function PromptPresetPanel({ postId, initialInstructions, onGenerate, isGenerating }: Props) {
  const [presets, setPresets] = useState<PromptPreset[]>([])
  const [instructions, setInstructions] = useState(initialInstructions ?? '')

  useEffect(() => {
    editorApi.promptPresets().then((res) => setPresets(res.presets)).catch(() => {})
  }, [])

  useEffect(() => {
    setInstructions(initialInstructions ?? '')
  }, [initialInstructions])

  const handlePresetClick = (preset: PromptPreset) => {
    setInstructions((prev) => {
      const trimmed = prev.trim()
      return trimmed ? `${trimmed}\n${preset.extra_instructions}` : preset.extra_instructions
    })
  }

  const maxLength = 1000
  const charCount = instructions.length

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">프롬프트 프리셋</p>

      {presets.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {presets.map((preset) => (
            <button
              key={preset.key}
              onClick={() => handlePresetClick(preset)}
              className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-100 transition-colors"
              title={preset.extra_instructions}
            >
              {preset.label}
            </button>
          ))}
        </div>
      )}

      <div className="relative">
        <textarea
          className="w-full rounded border border-gray-200 p-2.5 text-sm leading-relaxed resize-none focus:outline-none focus:ring-1 focus:ring-blue-300"
          rows={4}
          maxLength={maxLength}
          placeholder="AI 대본 생성 지시문을 입력하세요..."
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
        <span className={`absolute bottom-2 right-2 text-xs ${charCount >= maxLength ? 'text-red-500' : 'text-gray-400'}`}>
          {charCount}/{maxLength}
        </span>
      </div>

      <div className="mt-3">
        <Button
          size="sm"
          onClick={() => onGenerate(instructions)}
          disabled={isGenerating}
          className="w-full"
        >
          {isGenerating
            ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />생성 중...</>
            : <><Sparkles className="mr-1.5 h-3.5 w-3.5" />AI 대본 재생성</>
          }
        </Button>
      </div>
    </div>
  )
}
