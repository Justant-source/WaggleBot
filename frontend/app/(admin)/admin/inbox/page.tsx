'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { inboxApi } from '@/lib/api/inbox'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Post } from '@/lib/types'
import { useInboxStore } from '@/lib/store/inboxStore'
import { usePollingJob } from '@/lib/hooks/usePollingJob'
import { Loader2, RefreshCw, CheckCheck, XCircle } from 'lucide-react'

export default function InboxPage() {
  const [data, setData] = useState<{ posts: Post[]; total: number; counts: { tier1: number; tier2: number; tier3: number } } | null>(null)
  const [loading, setLoading] = useState(true)
  const [crawlJobId, setCrawlJobId] = useState<number | null>(null)
  const { page, selectedIds, toggleSelect, clearSelection, setPage } = useInboxStore()

  const crawlJob = usePollingJob(crawlJobId, (id) => inboxApi.pollJob(id))

  const load = async () => {
    try {
      setLoading(true)
      const res = await inboxApi.list({ page, size: 20 })
      setData(res)
    } catch { toast.error('수신함 로드 실패') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [page])

  useEffect(() => {
    if (crawlJob.status === 'DONE') { toast.success('크롤링 완료'); load() }
    if (crawlJob.status === 'ERROR') toast.error('크롤링 실패')
  }, [crawlJob.status])

  const handleApprove = async (id: number) => {
    try { await inboxApi.approve(id); toast.success('승인됨'); load() }
    catch { toast.error('승인 실패') }
  }

  const handleDecline = async (id: number) => {
    try { await inboxApi.decline(id); toast.success('거절됨'); load() }
    catch { toast.error('거절 실패') }
  }

  const handleBatchApprove = async () => {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    await inboxApi.batch(ids, 'approve')
    toast.success(`${ids.length}개 승인`)
    clearSelection(); load()
  }

  const handleCrawl = async () => {
    const res = await inboxApi.triggerCrawl()
    setCrawlJobId(res.jobId)
    toast.info('크롤링 시작...')
  }

  const getTier = (score: number) => {
    if (score >= 80) return 'tier1'
    if (score >= 30) return 'tier2'
    return 'tier3'
  }

  const tierBadge = (score: number) => {
    const t = getTier(score)
    if (t === 'tier1') return <Badge variant="success">상위</Badge>
    if (t === 'tier2') return <Badge variant="warning">중위</Badge>
    return <Badge variant="outline">하위</Badge>
  }

  const totalPages = data ? Math.ceil(data.total / 20) : 1

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">수신함</h1>
        <div className="flex gap-2">
          {selectedIds.size > 0 && (
            <Button size="sm" onClick={handleBatchApprove}>
              <CheckCheck className="mr-1 h-4 w-4" />
              {selectedIds.size}개 일괄 승인
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleCrawl} disabled={crawlJob.isPolling}>
            {crawlJob.isPolling ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
            크롤링
          </Button>
        </div>
      </div>

      {data && (
        <div className="mb-6 grid grid-cols-3 gap-4">
          <AdminStatCard label="상위 (≥80)" value={data.counts.tier1} />
          <AdminStatCard label="중위 (30~79)" value={data.counts.tier2} />
          <AdminStatCard label="하위 (<30)" value={data.counts.tier3} />
        </div>
      )}

      <AdminSection title="게시글 목록">
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-3 py-2 text-left w-8"><input type="checkbox" onChange={(e) => e.target.checked && data ? useInboxStore.getState().selectAll(data.posts) : clearSelection()} /></th>
                  <th className="px-3 py-2 text-left">제목</th>
                  <th className="px-3 py-2 text-left w-16">사이트</th>
                  <th className="px-3 py-2 text-right w-20">점수</th>
                  <th className="px-3 py-2 text-left w-16">티어</th>
                  <th className="px-3 py-2 text-center w-32">액션</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data?.posts.map((post) => (
                  <tr key={post.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={selectedIds.has(post.id)} onChange={() => toggleSelect(post.id)} />
                    </td>
                    <td className="px-3 py-2 font-medium text-gray-900 max-w-xs truncate">{post.title}</td>
                    <td className="px-3 py-2 text-gray-500">{post.siteCode}</td>
                    <td className="px-3 py-2 text-right font-mono">{Math.round(post.engagementScore)}</td>
                    <td className="px-3 py-2">{tierBadge(post.engagementScore)}</td>
                    <td className="px-3 py-2">
                      <div className="flex justify-center gap-1">
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleApprove(post.id)}>승인</Button>
                        <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => handleDecline(post.id)}>거절</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 py-3">
              <AdminPagination page={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          </div>
        )}
      </AdminSection>
    </div>
  )
}
