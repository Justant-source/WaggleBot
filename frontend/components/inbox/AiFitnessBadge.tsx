'use client'

import { useState } from 'react'
import { Sparkles, Loader2, Star } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Post } from '@/lib/types'

interface Props {
  post: Post
  onAnalyzeRequest: () => void
  isAnalyzing: boolean
}

export function AiFitnessBadge({ post, onAnalyzeRequest, isAnalyzing }: Props) {
  const hasScore = post.aiScore !== null && post.aiScore !== undefined

  if (!hasScore) {
    return (
      <div className="flex items-center gap-1">
        <Badge variant="outline" className="bg-gray-100 text-gray-500 text-xs">미분석</Badge>
        <Button
          size="sm"
          variant="ghost"
          className="h-5 w-5 p-0"
          onClick={(e) => { e.stopPropagation(); onAnalyzeRequest() }}
          disabled={isAnalyzing}
          title="AI 적합도 분석"
        >
          {isAnalyzing
            ? <Loader2 className="h-3 w-3 animate-spin" />
            : <Sparkles className="h-3 w-3 text-gray-400" />
          }
        </Button>
      </div>
    )
  }

  const score = post.aiScore as number

  let colorClass: string
  if (score >= 70) {
    colorClass = 'bg-green-100 text-green-800'
  } else if (score >= 40) {
    colorClass = 'bg-amber-100 text-amber-800'
  } else {
    colorClass = 'bg-gray-100 text-gray-600'
  }

  return (
    <div
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${colorClass} cursor-default`}
      title={post.aiReason ?? undefined}
    >
      {post.aiRecommended && <Star className="h-3 w-3 fill-current" />}
      AI {score}
    </div>
  )
}
