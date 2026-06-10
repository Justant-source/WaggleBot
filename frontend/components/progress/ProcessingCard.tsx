'use client'

import { useEffect, useState } from 'react'
import { PhaseStepper } from './PhaseStepper'
import { Badge } from '@/components/ui/badge'
import type { ProcessingPost } from '@/lib/types'

interface Props {
  post: ProcessingPost
}

function useElapsed(startedAt?: string): string {
  const [elapsed, setElapsed] = useState('')

  useEffect(() => {
    if (!startedAt) { setElapsed(''); return }

    const update = () => {
      const diffMs = Date.now() - new Date(startedAt).getTime()
      const totalSec = Math.floor(diffMs / 1000)
      const min = Math.floor(totalSec / 60)
      const sec = totalSec % 60
      setElapsed(`${min}분 ${sec}초`)
    }

    update()
    const t = setInterval(update, 1000)
    return () => clearInterval(t)
  }, [startedAt])

  return elapsed
}

export function ProcessingCard({ post }: Props) {
  const progress = post.progress
  const elapsed = useElapsed(progress?.phaseStartedAt)

  const isStale = progress?.updatedAt
    ? Date.now() - new Date(progress.updatedAt).getTime() > 15 * 60 * 1000
    : post.updatedAt
    ? Date.now() - new Date(post.updatedAt).getTime() > 15 * 60 * 1000
    : false

  const isVideoPhase = progress?.currentPhase === 7
  const scenesDone = progress?.scenesDone ?? 0
  const totalScenes = progress?.totalScenes ?? 0
  const sceneProgress = totalScenes > 0 ? (scenesDone / totalScenes) * 100 : 0

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 text-sm">
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="truncate font-medium text-gray-900 flex-1">{post.title}</p>
        <div className="flex shrink-0 items-center gap-1.5">
          {isStale && (
            <Badge variant="outline" className="bg-amber-50 border-amber-200 text-amber-700 text-xs">
              ⚠ 응답 없음
            </Badge>
          )}
          <Badge>{post.status}</Badge>
        </div>
      </div>

      <PhaseStepper
        currentPhase={progress?.currentPhase}
        done={progress?.done}
      />

      {isVideoPhase && totalScenes > 0 && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span>비디오 {scenesDone}/{totalScenes} 씬</span>
            <span>{Math.round(sceneProgress)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-gray-100">
            <div
              className="h-1.5 rounded-full bg-primary transition-all"
              style={{ width: `${sceneProgress}%` }}
            />
          </div>
        </div>
      )}

      {elapsed && (
        <p className="mt-1.5 text-xs text-gray-400">경과: {elapsed}</p>
      )}
    </div>
  )
}
