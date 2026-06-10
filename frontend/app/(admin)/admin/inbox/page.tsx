'use client'

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { inboxApi } from '@/lib/api/inbox'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Post } from '@/lib/types'
import { useInboxStore } from '@/lib/store/inboxStore'
import { usePollingJob } from '@/lib/hooks/usePollingJob'
import { Loader2, RefreshCw, CheckCheck, X, Eye, Image as ImageIcon, Search } from 'lucide-react'

const SITE_CODES = ['nate_pann', 'bobaedream', 'dcinside', 'fmkorea']

interface PostStats { views?: number; likes?: number; comments_count?: number }

function getTier(score: number) {
  if (score >= 80) return 'tier1'
  if (score >= 30) return 'tier2'
  return 'tier3'
}

function tierBadge(score: number) {
  const t = getTier(score)
  if (t === 'tier1') return <Badge variant="success">상위</Badge>
  if (t === 'tier2') return <Badge variant="warning">중위</Badge>
  return <Badge variant="outline">하위</Badge>
}

export default function InboxPage() {
  const [data, setData] = useState<{ posts: Post[]; total: number; counts: { tier1: number; tier2: number; tier3: number } } | null>(null)
  const [loading, setLoading] = useState(true)
  const [crawlJobId, setCrawlJobId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Post | null>(null)
  const [siteFilter, setSiteFilter] = useState('all')
  const [tierFilter, setTierFilter] = useState('all')
  const [searchInput, setSearchInput] = useState('')
  const [activeQ, setActiveQ] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const { page, selectedIds, toggleSelect, clearSelection, setPage } = useInboxStore()

  const crawlJob = usePollingJob(crawlJobId, (id) => inboxApi.pollJob(id))

  const load = async () => {
    try {
      setLoading(true)
      const res = await inboxApi.list({
        page,
        size: 20,
        siteCode: siteFilter !== 'all' ? siteFilter : undefined,
        tier: tierFilter !== 'all' ? tierFilter : undefined,
        q: activeQ.trim() || undefined,
      })
      setData(res)
    } catch { toast.error('수신함 로드 실패') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [page, siteFilter, tierFilter, activeQ])

  const handleFilterChange = () => {
    setPage(0)
    clearSelection()
  }

  const handleSearch = () => {
    setActiveQ(searchInput.trim())
    handleFilterChange()
  }

  useEffect(() => {
    if (crawlJob.status === 'DONE') { toast.success('크롤링 완료'); load() }
    if (crawlJob.status === 'ERROR') toast.error('크롤링 실패')
  }, [crawlJob.status])

  const handleApprove = async (id: number) => {
    try { await inboxApi.approve(id); toast.success('승인됨'); setDetail(null); load() }
    catch { toast.error('승인 실패') }
  }

  const handleDecline = async (id: number) => {
    try { await inboxApi.decline(id); toast.success('거절됨'); setDetail(null); load() }
    catch { toast.error('거절 실패') }
  }

  const handleBatchApprove = async () => {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    const result = await inboxApi.batch(ids, 'approve')
    if (result.failed?.length > 0) {
      toast.warning(`${result.processed}개 성공, ${result.failed.length}개 실패`)
    } else {
      toast.success(`${result.processed}개 승인`)
    }
    clearSelection(); load()
  }

  const handleCrawl = async () => {
    const res = await inboxApi.triggerCrawl()
    setCrawlJobId(res.jobId)
    toast.info('크롤링 시작...')
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
        <div className="mb-4 grid grid-cols-3 gap-4">
          <AdminStatCard label="상위 (≥80)" value={data.counts.tier1} />
          <AdminStatCard label="중위 (30~79)" value={data.counts.tier2} />
          <AdminStatCard label="하위 (<30)" value={data.counts.tier3} />
        </div>
      )}

      {/* 필터 바 */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={siteFilter} onValueChange={(v) => { setSiteFilter(v); handleFilterChange() }}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue placeholder="전체 사이트" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 사이트</SelectItem>
            {SITE_CODES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={tierFilter} onValueChange={(v) => { setTierFilter(v); handleFilterChange() }}>
          <SelectTrigger className="h-8 w-28 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 티어</SelectItem>
            <SelectItem value="tier1">상위 (≥80)</SelectItem>
            <SelectItem value="tier2">중위 (30~79)</SelectItem>
            <SelectItem value="tier3">하위 (&lt;30)</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex flex-1 gap-1">
          <Input
            ref={searchRef}
            className="h-8 max-w-xs text-xs"
            placeholder="제목 검색..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
          />
          <Button size="sm" variant="outline" className="h-8 px-2" onClick={handleSearch}>
            <Search className="h-3.5 w-3.5" />
          </Button>
          {(siteFilter !== 'all' || tierFilter !== 'all' || activeQ) && (
            <Button
              size="sm"
              variant="ghost"
              className="h-8 px-2 text-xs text-gray-500"
              onClick={() => {
                setSiteFilter('all'); setTierFilter('all')
                setSearchInput(''); setActiveQ('')
                handleFilterChange()
              }}
            >
              초기화
            </Button>
          )}
        </div>
      </div>

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
                  <th className="px-3 py-2 text-center w-40">액션</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data?.posts.map((post) => {
                  const stats = (post.stats ?? {}) as PostStats
                  const imgCount = Array.isArray(post.images) ? post.images.length : 0
                  return (
                    <tr key={post.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={selectedIds.has(post.id)} onChange={() => toggleSelect(post.id)} />
                      </td>
                      <td className="px-3 py-2 max-w-md">
                        <button
                          onClick={() => setDetail(post)}
                          className="group flex items-center gap-2 text-left font-medium text-gray-900 hover:text-blue-600"
                          title="내용 보기"
                        >
                          <span className="truncate">{post.title}</span>
                          {imgCount > 0 && (
                            <span className="flex shrink-0 items-center gap-0.5 text-xs text-gray-400">
                              <ImageIcon className="h-3 w-3" />{imgCount}
                            </span>
                          )}
                        </button>
                        <div className="mt-0.5 text-xs text-gray-400">
                          조회 {stats.views ?? 0} · 추천 {stats.likes ?? 0} · 댓글 {stats.comments_count ?? 0}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-gray-500">{post.siteCode}</td>
                      <td className="px-3 py-2 text-right font-mono">{Math.round(post.engagementScore)}</td>
                      <td className="px-3 py-2">{tierBadge(post.engagementScore)}</td>
                      <td className="px-3 py-2">
                        <div className="flex justify-center gap-1">
                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setDetail(post)}>
                            <Eye className="mr-1 h-3 w-3" />보기
                          </Button>
                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleApprove(post.id)}>승인</Button>
                          <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => handleDecline(post.id)}>거절</Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="px-4 py-3">
              <AdminPagination page={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          </div>
        )}
      </AdminSection>

      <PostDetailDrawer
        post={detail}
        onClose={() => setDetail(null)}
        onApprove={handleApprove}
        onDecline={handleDecline}
      />
    </div>
  )
}

function PostDetailDrawer({
  post, onClose, onApprove, onDecline,
}: {
  post: Post | null
  onClose: () => void
  onApprove: (id: number) => void
  onDecline: (id: number) => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    if (post) window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [post, onClose])

  if (!post) return null

  const stats = (post.stats ?? {}) as PostStats
  const images = Array.isArray(post.images) ? (post.images as string[]) : []

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* panel */}
      <div className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        {/* header */}
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-6 py-4">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline">{post.siteCode}</Badge>
              {tierBadge(post.engagementScore)}
              <span className="text-xs text-gray-400">점수 {Math.round(post.engagementScore)}</span>
            </div>
            <h2 className="text-lg font-semibold leading-snug text-gray-900">{post.title}</h2>
          </div>
          <button onClick={onClose} className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700" title="닫기 (Esc)">
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
