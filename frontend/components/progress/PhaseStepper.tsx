'use client'

import { Check } from 'lucide-react'

const PHASES = [
  { num: 1, label: '분석' },
  { num: 2, label: '대본' },
  { num: 3, label: '검증' },
  { num: 4, label: '씬구성' },
  { num: 5, label: 'TTS' },
  { num: 6, label: '프롬프트' },
  { num: 7, label: '비디오' },
  { num: 8, label: '렌더링' },
]

interface Props {
  currentPhase?: number | null
  done?: boolean
  skippedPhases?: number[]
}

export function PhaseStepper({ currentPhase, done, skippedPhases }: Props) {
  const current = currentPhase ?? 0

  return (
    <div className="flex items-center gap-0.5 overflow-x-auto py-1">
      {PHASES.map((phase, idx) => {
        const isCompleted = done ? true : phase.num < current
        const isCurrent = !done && phase.num === current
        const isFuture = !done && phase.num > current
        const isSkipped = skippedPhases?.includes(phase.num) ?? false

        return (
          <div key={phase.num} className="flex items-center">
            {/* step circle */}
            <div className="flex flex-col items-center">
              <div
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold border transition-all ${
                  isSkipped
                    ? 'border-gray-200 bg-gray-50 text-gray-300'
                    : isCompleted
                    ? 'bg-green-500 border-green-500 text-white'
                    : isCurrent
                    ? 'bg-primary border-primary text-primary-foreground ring-2 ring-primary ring-offset-1 animate-pulse'
                    : 'bg-white border-gray-300 text-gray-400'
                }`}
              >
                {isCompleted && !isSkipped ? <Check className="h-2.5 w-2.5" /> : phase.num}
              </div>
              <span
                className={`mt-0.5 text-[9px] leading-none ${
                  isSkipped
                    ? 'line-through text-gray-300'
                    : isCompleted
                    ? 'text-green-600'
                    : isCurrent
                    ? 'text-primary font-medium'
                    : 'text-gray-400'
                }`}
              >
                {phase.label}
              </span>
            </div>

            {/* connector */}
            {idx < PHASES.length - 1 && (
              <div
                className={`mx-0.5 h-px w-4 shrink-0 ${
                  phase.num < current ? 'bg-green-400' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
