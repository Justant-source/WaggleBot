'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { overviewApi } from '@/lib/api/overview'
import { analyticsApi, type PerformanceRow } from '@/lib/api/analytics'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { AdminSection } from '@/components/admin/AdminSection'
import { ProcessingCard } from '@/components/progress/ProcessingCard'
import { Button } from '@/components/ui/button'
import { Loader2, Inbox, Film, AlertCircle, ArrowRight } from 'lucide-react'
import type { OverviewData } from '@/lib/types'

const STATUS_ORDER = [
  'COLLECTED', 'EDITING', 'APPROVED', 'PROCESSING',
  'PREVIEW_RENDERED', 'RENDERED', 'UPLOADED',
]

const STATUS_COLOR: Record<string, string> = {
  COLLECTED: 'bg-gray-400',
  EDITING: 'bg-blue-400',
  APPROVED: 'bg-indigo-500',
  PROCESSING: 'bg-violet-500',
  PREVIEW_RENDERED: 'bg-amber-400',
  RENDERED: 'bg-orange-400',
  UPLOADED: 'bg-green-500',
}

export default function OverviewPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [performance, setPerformance] = useState<PerformanceRow[]>([])
  const [loading, setLoading] = useState(true)

  const todaySince = new Date(new Date().setHours(0, 0, 0, 0)).toISOString()

  const load = async () => {
    try {
      const [ov, perf] = await Promise.all([
        overviewApi.get(todaySince),
        analyticsApi.performance(5),
      ])
      setOverview(ov)
      setPerformance(perf)
    } catch {}
    finally { setLoading(false) }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  const counts = overview?.counts ?? {}
  const today = overview?.today ?? { crawled: 0, uploaded: 0, declined: 0 }
  const waitCount = (counts['COLLECTED'] ?? 0) + (counts['EDITING'] ?? 0) + (counts['APPROVED'] ?? 0)
  const failedCount = counts['FAILED'] ?? 0

  // Funnel max value for relative bar widths
  const funnelMax = Math.max(...STATUS_ORDER.map((s) => counts[s] ?? 0), 1)

  const processingPosts = (overview?.processing ?? []).slice(0, 3)
  const hasMoreProcessing = (overview?.processing ?? []).length > 3

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">오버뷰</h1>

      {/* Row 1: KPI 카드 */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <AdminStatCard
          label="오늘 수집"
          value={today.crawled}
          className="border-blue-100"
        />
        <AdminStatCard
          label="오늘 업로드"
          value={today.uploaded}
          className="border-green-100"
        />
        <AdminStatCard
          label="처리 대기"
          value={waitCount}
          className="border-indigo-100"
        />
        <AdminStatCard
          label="실패"
          value={failedCount}
          className={failedCount > 0 ? 'border-red-200 bg-red-50' : ''}
        />
      </div>

      {/* Row 2: 퍼널 + 처리 중 */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 미니 퍼널 */}
        <AdminSection title="상태별 현황">
          <div className="space-y-2">
            {STATUS_ORDER.map((status) => {
              const count = counts[status] ?? 0
              const width = funnelMax > 0 ? (count / funnelMax) * 100 : 0
              return (
                <div key={status} className="flex items-center gap-3 text-sm">
                  <span className="w-32 shrink-0 text-xs text-gray-500 uppercase">{status.toLowerCase().replace('_', ' ')}</span>
                  <div className="flex-1 h-4 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${STATUS_COLOR[status] ?? 'bg-gray-400'}`}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right font-mono text-xs text-gray-700">{count}</span>
                </div>
              )
            })}
          </div>
        </AdminSection>

        {/* 처리 중 */}
        <AdminSection
          title="처리 중"
          action={
            hasMoreProcessing ? (
              <Link href="/admin/progress" className="text-xs text-blue-600 hover:underline flex items-center gap-0.5">
                진행상황 보기 <ArrowRight className="h-3 w-3" />
              </Link>
            ) : undefined
          }
        >
          {processingPosts.length === 0 ? (
            <p className="text-sm text-gray-400">처리 중인 항목 없음</p>
          ) : (
            <div className="space-y-2">
              {processingPosts.map((post) => (
                <ProcessingCard key={post.id} post={post} />
              ))}
            </div>
          )}
        </AdminSection>
      </div>

      {/* Row 3: 최근 업로드 성과 */}
      {performance.length > 0 && (
        <AdminSection title="최근 업로드 성과">
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">제목</th>
                  <th className="px-3 py-2 text-right w-20">조회</th>
                  <th className="px-3 py-2 text-right w-20">좋아요</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {performance.map((row) => (
                  <tr key={row.postId} className="hover:bg-gray-50">
                    <td className="px-3 py-2 max-w-xs">
                      {row.videoId ? (
                        <a
                          href={`https://www.youtube.com/watch?v=${row.videoId}`}
                          target="_blank"
                          rel="noreferrer"
                          className="truncate block text-blue-600 hover:underline"
                        >
                          {row.title}
                        </a>
                      ) : (
                        <span className="truncate block text-gray-800">{row.title}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-700">
                      {(row.analytics.views ?? 0).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-700">
                      {(row.analytics.likes ?? 0).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AdminSection>
      )}

      {/* 바로가기 버튼 */}
      <div className="mt-6 flex gap-3">
        <Button asChild variant="outline">
          <Link href="/admin/inbox">
            <Inbox className="mr-1.5 h-4 w-4" />수신함으로
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/admin/editor">
            <Film className="mr-1.5 h-4 w-4" />편집실로
          </Link>
        </Button>
        {failedCount > 0 && (
          <Button asChild variant="outline" className="text-red-600 border-red-200 hover:bg-red-50">
            <Link href="/admin/progress">
              <AlertCircle className="mr-1.5 h-4 w-4" />실패 {failedCount}건 확인
            </Link>
          </Button>
        )}
      </div>
    </div>
  )
}
