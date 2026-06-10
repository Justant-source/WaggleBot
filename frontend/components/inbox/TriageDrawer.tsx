'use client'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { X, ChevronLeft, ChevronRight, Image as ImageIcon, CheckCheck } from 'lucide-react'
import { AiFitnessBadge } from './AiFitnessBadge'
import { CommentList } from './CommentList'
import type { Post } from '@/lib/types'

interface PostStats { views?: number; likes?: number; comments_count?: number }

interface Props {
  post: Post | null
  posts: Post[]
  detailIdx: number | null
  onClose: () => void
  onApprove: (id: number) => Promise<void>
  onDecline: (id: number) => Promise<void>
  onNavigate: (idx: number) => void
  onAnalyzeRequest: (id: number) => void
  analyzingIds: Set<number>
}

export function TriageDrawer({
  post, posts, detailIdx, onClose, onApprove, onDecline, onNavigate, onAnalyzeRequest, analyzingIds,
}: Props) {
  if (!post) return null

  const stats = (post.stats ?? {}) as PostStats
  const images = Array.isArray(post.images) ? (post.images as string[]) : []
  const canPrev = detailIdx !== null && detailIdx > 0
  const canNext = detailIdx !== null && detailIdx < posts.length - 1

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* panel */}
      <div className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        {/* header */}
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-6 py-4">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline">{post.siteCode}</Badge>
              <AiFitnessBadge
                post={post}
                onAnalyzeRequest={() => onAnalyzeRequest(post.id)}
                isAnalyzing={analyzingIds.has(post.id)}
              />
            </div>
            <h2 className="text-lg font-semibold leading-snug text-gray-900">{post.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            title="닫기 (Esc)"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* meta */}
        <div className="flex flex-wrap gap-x-6 gap-y-1 border-b border-gray-100 px-6 py-3 text-sm text-gray-500">
          <span>조회 <b className="text-gray-700">{stats.views ?? 0}</b></span>
          <span>추천 <b className="text-gray-700">{stats.likes ?? 0}</b></span>
          <span>댓글 <b className="text-gray-700">{stats.comments_count ?? 0}</b></span>
          <span>수집 {post.createdAt ? new Date(post.createdAt).toLocaleString('ko-KR') : '-'}</span>
        </div>

        {/* AI 이유 */}
        {post.aiReason && (
          <div className="mx-6 mt-4 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">
            <span className="font-medium">AI 분석:</span> {post.aiReason}
          </div>
        )}

        {/* body (scrollable) */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {post.content ? (
            <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-gray-800">
              {post.content}
            </p>
          ) : (
            <p className="text-sm text-gray-400">본문 내용이 없습니다.</p>
          )}

          {images.length > 0 && (
            <div className="mt-6">
              <div className="mb-2 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-gray-400">
                <ImageIcon className="h-3.5 w-3.5" /> 이미지 {images.length}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {images.map((src, i) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <a key={i} href={src} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg border border-gray-200">
                    <img
                      src={src}
                      alt={`이미지 ${i + 1}`}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      className="h-auto w-full object-cover"
                      onError={(e) => { (e.currentTarget.parentElement as HTMLElement).style.display = 'none' }}
                    />
                  </a>
                ))}
              </div>
            </div>
          )}

          <CommentList postId={post.id} />
        </div>

        {/* navigation arrows */}
        <div className="flex items-center justify-between border-t border-gray-100 px-6 py-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => detailIdx !== null && onNavigate(detailIdx - 1)}
            disabled={!canPrev}
          >
            <ChevronLeft className="h-4 w-4" />이전
          </Button>
          <span className="text-xs text-gray-400 select-none">
            J/K 이동 · A 승인 · D 거절 · Esc 닫기
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => detailIdx !== null && onNavigate(detailIdx + 1)}
            disabled={!canNext}
          >
            다음<ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {/* footer actions */}
        <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" className="text-red-600" onClick={() => onDecline(post.id)}>거절</Button>
          <Button onClick={() => onApprove(post.id)}>
            <CheckCheck className="mr-1 h-4 w-4" /> 승인 (대본 생성)
          </Button>
        </div>
      </div>
    </div>
  )
}
