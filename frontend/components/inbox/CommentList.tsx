'use client'

import { useEffect, useState } from 'react'
import { inboxApi } from '@/lib/api/inbox'
import { Skeleton } from '@/components/ui/skeleton'

interface Comment {
  id: number
  author: string
  content: string
  likes: number
}

interface Props {
  postId: number
}

export function CommentList({ postId }: Props) {
  const [comments, setComments] = useState<Comment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    inboxApi.comments(postId, 5)
      .then((res) => setComments(res.comments))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [postId])

  if (loading) {
    return (
      <div className="mt-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">베스트 댓글</p>
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-1">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-4 w-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!comments.length) return null

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">베스트 댓글</p>
      <div className="space-y-2">
        {comments.slice(0, 5).map((c) => (
          <div key={c.id} className="rounded bg-gray-50 px-3 py-2 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <span className="font-semibold text-gray-800">{c.author}</span>
                <p className="mt-0.5 text-gray-600 break-words">{c.content}</p>
              </div>
              <span className="shrink-0 text-xs text-gray-400">👍{c.likes}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
