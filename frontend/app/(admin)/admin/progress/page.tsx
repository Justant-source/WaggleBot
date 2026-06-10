'use client'
import { useEffect, useState } from 'react'
import { progressApi } from '@/lib/api/progress'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { AdminSection } from '@/components/admin/AdminSection'
import { ProcessingCard } from '@/components/progress/ProcessingCard'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import type { Post, ProcessingPost } from '@/lib/types'

function FailedPostCard({ post, onRetry }: { post: Post; onRetry: (id: number) => Promise<void> }) {
  const [expanded, setExpanded] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const handleRetry = async () => {
    setRetrying(true)
    try {
      await onRetry(post.id)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="rounded border border-red-200 bg-white p-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-gray-900">{post.title}</p>
          {post.lastError && (
            <div className="mt-1">
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="text-xs text-red-500 hover:underline"
              >
                {expanded ? '오류 접기' : '오류 펼치기'}
              </button>
              {expanded && (
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-red-50 p-2 text-xs text-red-700">
                  {post.lastError}
                </pre>
              )}
            </div>
          )}
          {!post.lastError && (
            <p className="mt-1 text-xs text-gray-400">오류 메시지 없음</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="destructive">FAILED</Badge>
          <Button size="sm" variant="outline" disabled={retrying} onClick={handleRetry}>
            {retrying ? '처리 중...' : '재시도'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ProgressPage() {
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [processing, setProcessing] = useState<ProcessingPost[]>([])
  const [failed, setFailed] = useState<Post[]>([])

  const load = () =>
    progressApi.get().then((res) => {
      setCounts(res.counts)
      setProcessing(res.processing)
      setFailed(res.failed ?? [])
    })

  useEffect(() => {
    load()
    // 처리 중인 항목이 있으면 5초 간격, 없으면 10초
    const interval = processing.length > 0 ? 5000 : 10000
    const t = setInterval(load, interval)
    return () => clearInterval(t)
  }, [processing.length])

  const handleRetry = async (id: number) => {
    await progressApi.retry(id)
    toast.success('재시도 큐에 추가됨')
    load()
  }

  const statusOrder = ['COLLECTED', 'EDITING', 'APPROVED', 'PROCESSING', 'PREVIEW_RENDERED', 'RENDERED', 'UPLOADED', 'FAILED', 'DECLINED']

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">진행현황</h1>
      <div className="mb-6 grid grid-cols-3 gap-3 sm:grid-cols-5">
        {statusOrder.map((s) => (
          <AdminStatCard key={s} label={s.toLowerCase().replace('_', ' ')} value={counts[s] ?? 0} />
        ))}
      </div>
      <AdminSection title="처리 중">
        {processing.length === 0 ? (
          <p className="text-sm text-gray-400">처리 중인 항목 없음</p>
        ) : (
          <div className="space-y-2">
            {processing.map((post) => (
              <ProcessingCard key={post.id} post={post} />
            ))}
          </div>
        )}
      </AdminSection>
      <AdminSection title="실패 목록">
        {failed.length === 0 ? (
          <p className="text-sm text-gray-400">실패한 항목 없음</p>
        ) : (
          <div className="space-y-2">
            {failed.map((post) => (
              <FailedPostCard key={post.id} post={post} onRetry={handleRetry} />
            ))}
          </div>
        )}
      </AdminSection>
    </div>
  )
}
