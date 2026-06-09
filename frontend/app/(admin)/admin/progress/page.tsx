'use client'
import { useEffect, useState } from 'react'
import { progressApi } from '@/lib/api/progress'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import type { Post } from '@/lib/types'

export default function ProgressPage() {
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [processing, setProcessing] = useState<Post[]>([])

  const load = () => progressApi.get().then((res) => { setCounts(res.counts); setProcessing(res.processing) })

  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [])

  const handleRetry = async (id: number) => {
    await progressApi.retry(id); toast.success('재시도 큐에 추가됨'); load()
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
        {processing.length === 0 ? <p className="text-sm text-gray-400">처리 중인 항목 없음</p> : (
          <div className="space-y-2">
            {processing.map((post) => (
              <div key={post.id} className="flex items-center justify-between rounded border border-gray-200 bg-white p-3 text-sm">
                <span className="font-medium">{post.title}</span>
                <Badge>{post.status}</Badge>
              </div>
            ))}
          </div>
        )}
      </AdminSection>
      <AdminSection title="실패 목록">
        {/* Reuse processing list filtered by FAILED status — handled server side in counts */}
        <p className="text-sm text-gray-400">FAILED 상태 게시글을 재시도하려면 아래 API로 호출: POST /api/progress/{"{id}"}/retry</p>
      </AdminSection>
    </div>
  )
}
