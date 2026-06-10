'use client'

import { useState } from 'react'
import type { Post } from '@/lib/types'

interface PostStats { views?: number; likes?: number; comments_count?: number }

interface Props {
  post: Post
}

export function ScoreBreakdown({ post }: Props) {
  const [open, setOpen] = useState(false)
  const stats = (post.stats ?? {}) as PostStats
  const views = stats.views ?? 0
  const likes = stats.likes ?? 0
  const comments = stats.comments_count ?? 0
  const age = (Date.now() - new Date(post.createdAt).getTime()) / (1000 * 3600)
  const decay = Math.pow(0.5, age / 6)

  return (
    <div className="relative inline-block">
      <button
        className="font-mono text-sm hover:text-blue-600 hover:underline"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
        title="점수 구성 보기"
      >
        {Math.round(post.engagementScore)}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-6 z-50 w-52 rounded-lg border border-gray-200 bg-white p-3 shadow-lg text-xs">
            <p className="mb-2 font-semibold text-gray-700">점수 구성</p>
            <table className="w-full">
              <tbody className="divide-y divide-gray-100">
                <tr>
                  <td className="py-0.5 text-gray-500">조회 {views} × 0.1</td>
                  <td className="py-0.5 text-right font-mono">{(views * 0.1).toFixed(0)}</td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500">추천 {likes} × 2.0</td>
                  <td className="py-0.5 text-right font-mono">{(likes * 2.0).toFixed(0)}</td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500">댓글 {comments} × 1.5</td>
                  <td className="py-0.5 text-right font-mono">{(comments * 1.5).toFixed(0)}</td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500">시간감쇠 ×{decay.toFixed(2)}</td>
                  <td className="py-0.5 text-right text-gray-400">{Math.round(age)}h 전</td>
                </tr>
              </tbody>
            </table>
            <div className="mt-1.5 border-t border-gray-200 pt-1.5 flex justify-between font-semibold">
              <span className="text-gray-700">총점</span>
              <span className="font-mono">{Math.round(post.engagementScore)}</span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
