'use client'

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { inboxApi } from '@/lib/api/inbox'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { AiFitnessBadge } from '@/components/inbox/AiFitnessBadge'
import { ScoreBreakdown } from '@/components/inbox/ScoreBreakdown'
import { TriageDrawer } from '@/components/inbox/TriageDrawer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Post } from '@/lib/types'
import { useInboxStore } from '@/lib/store/inboxStore'
import { usePollingJob } from '@/lib/hooks/usePollingJob'
import { Loader2, RefreshCw, CheckCheck, X, Image as ImageIcon, Search, Sparkles, XCircle } from 'lucide-react'

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

/** axios 에러에서 사용자에게 보여줄 원인 문자열 추출 (DevTools 없이 진단 가능하도록). */
function apiErr(e: any): string {
  if (e?.response) {
    const d = e.response.data
    const msg = (d && (d.error || d.message)) || ''
    return `HTTP ${e.response.status}${msg ? ` · ${msg}` : ''}`
  }
  if (e?.code === 'ECONNABORTED') return '시간 초과(timeout)'
  return e?.message || '네트워크 오류(응답 없음)'
}

export default function InboxPage() {
  const [data, setData] = useState<{ posts: Post[]; total: number; counts: { tier1: number; tier2: number; tier3: number } } | null>(null)
  const [siteCodes, setSiteCodes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [crawlJobId, setCrawlJobId] = useState<number | null>(null)
  const [detailIdx, setDetailIdx] = useState<number | null>(null)
  const [siteFilter, setSiteFilter] = useState('all')
  const [tierFilter, setTierFilter] = useState('all')
  const [searchInput, setSearchInput] = useState('')
  const [activeQ, setActiveQ] = useState('')
  const [sort, setSort] = useState<'score' | 'ai_score' | 'newest'>('score')
  const [todayOnly, setTodayOnly] = useState(false)
  const [recommendedOnly, setRecommendedOnly] = useState(false)
  const [analyzingIds, setAnalyzingIds] = useState<Set<number>>(new Set())
  const [batchAnalyzing, setBatchAnalyzing] = useState(false)
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map())

  const detail = detailIdx !== null ? data?.posts[detailIdx] ?? null : null

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
        sort,
        since: todayOnly ? new Date(new Date().setHours(0, 0, 0, 0)).toISOString() : undefined,
        recommended: recommendedOnly || undefined,
      })
      setData(res)
    } catch { toast.error('수신함 로드 실패') }
    finally { setLoading(false) }
  }

  useEffect(() => { inboxApi.sites().then(setSiteCodes).catch(() => {}) }, [])
  useEffect(() => { load() }, [page, siteFilter, tierFilter, activeQ, sort, todayOnly, recommendedOnly])

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
    // Optimistic removal
    setData((prev) => {
      if (!prev) return prev
      const newPosts = prev.posts.filter((p) => p.id !== id)
      return { ...prev, posts: newPosts, total: prev.total - 1 }
    })
    setDetailIdx((prev) => {
      if (prev === null) return null
      const newLen = (data?.posts.length ?? 1) - 1
      return Math.min(prev, newLen - 1) < 0 ? null : Math.min(prev, newLen - 1)
    })
    try {
      await inboxApi.approve(id)
      toast.success('승인됨')
    } catch (e) {
      toast.error(`승인 실패 — ${apiErr(e)}`)
      load()
    }
  }

  const handleDecline = async (id: number) => {
    // Optimistic removal
    setData((prev) => {
      if (!prev) return prev
      const newPosts = prev.posts.filter((p) => p.id !== id)
      return { ...prev, posts: newPosts, total: prev.total - 1 }
    })
    setDetailIdx((prev) => {
      if (prev === null) return null
      const newLen = (data?.posts.length ?? 1) - 1
      return Math.min(prev, newLen - 1) < 0 ? null : Math.min(prev, newLen - 1)
    })
    try {
      await inboxApi.decline(id)
      toast.success('거절됨')
    } catch (e) {
      toast.error(`거절 실패 — ${apiErr(e)}`)
      load()
    }
  }

  const handleBatchApprove = async () => {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    try {
      const result = await inboxApi.batch(ids, 'approve')
      if (result.failed?.length > 0) {
        toast.warning(`${result.processed}개 성공, ${result.failed.length}개 실패`)
      } else {
        toast.success(`${result.processed}개 승인`)
      }
      clearSelection(); load()
    } catch { toast.error('일괄 승인 실패') }
  }

  const handleBatchDecline = async () => {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    try {
      const result = await inboxApi.batch(ids, 'decline')
      if (result.failed?.length > 0) {
        toast.warning(`${result.processed}개 성공, ${result.failed.length}개 실패`)
      } else {
        toast.success(`${result.processed}개 거절`)
      }
      clearSelection(); load()
    } catch { toast.error('일괄 거절 실패') }
  }

  const handleBatchAnalyze = async () => {
    setBatchAnalyzing(true)
    try {
      const unanalyzed = data?.posts.filter((p) => p.aiScore === null || p.aiScore === undefined) ?? []
      if (!unanalyzed.length) { toast.info('분석할 게시글이 없습니다'); return }
      const result = await inboxApi.analyzeBatch({ ids: unanalyzed.map((p) => p.id) })
      toast.success(`${result.enqueued}개 분석 요청됨`)
      setTimeout(load, 3000)
    } catch { toast.error('일괄 분석 요청 실패') }
    finally { setBatchAnalyzing(false) }
  }

  const handleAnalyzeRequest = async (id: number) => {
    setAnalyzingIds((prev) => new Set([...prev, id]))
    try {
      await inboxApi.analyze(id)
      toast.success('분석 요청됨')
      setTimeout(load, 3000)
    } catch { toast.error('분석 요청 실패') }
    finally {
      setAnalyzingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleCrawl = async () => {
    try {
      const res = await inboxApi.triggerCrawl()
      setCrawlJobId(res.jobId)
      toast.info('크롤링 시작...')
    } catch { toast.error('크롤링 요청 실패') }
  }

  // Keyboard triage
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.isComposing) return
      const target = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable) return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const len = data?.posts.length ?? 0
      switch (e.key) {
        case 'j':
        case 'ArrowDown': {
          e.preventDefault()
          setDetailIdx((prev) => {
            const next = prev === null ? (len > 0 ? 0 : null) : Math.min(prev + 1, len - 1)
            if (next !== null) {
              const row = rowRefs.current.get(data!.posts[next].id)
              row?.scrollIntoView({ block: 'nearest' })
            }
            return next
          })
          break
        }
        case 'k':
        case 'ArrowUp': {
          e.preventDefault()
          setDetailIdx((prev) => {
            if (prev === null) return null
            const next = Math.max(prev - 1, 0)
            const row = rowRefs.current.get(data!.posts[next].id)
            row?.scrollIntoView({ block: 'nearest' })
            return next
          })
          break
        }
        case 'a':
        case 'Enter': {
          if (detail) { e.preventDefault(); handleApprove(detail.id) }
          break
        }
        case 'd': {
          if (detail) { e.preventDefault(); handleDecline(detail.id) }
          break
        }
        case 'Escape': {
          setDetailIdx(null)
          break
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [data?.posts, detail, detailIdx])

  // Blur active element when drawer opens
  useEffect(() => {
    if (detailIdx !== null) {
      ;(document.activeElement as HTMLElement)?.blur()
    }
  }, [detailIdx])

  const totalPages = data ? Math.ceil(data.total / 20) : 1
  const hasActiveFilters = siteFilter !== 'all' || tierFilter !== 'all' || activeQ || todayOnly || recommendedOnly

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">수신함</h1>
        <div className="flex gap-2">
          {selectedIds.size > 0 && (
            <>
              <Button size="sm" onClick={handleBatchApprove}>
                <CheckCheck className="mr-1 h-4 w-4" />
                {selectedIds.size}개 일괄 승인
              </Button>
              <Button size="sm" variant="outline" className="text-red-600" onClick={handleBatchDecline}>
                <XCircle className="mr-1 h-4 w-4" />
                {selectedIds.size}개 일괄 거절
              </Button>
            </>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={handleBatchAnalyze}
            disabled={batchAnalyzing}
          >
            {batchAnalyzing
              ? <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              : <Sparkles className="mr-1 h-4 w-4" />
            }
            미분석 일괄 분석
          </Button>
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
            {siteCodes.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
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
        <Select value={sort} onValueChange={(v) => { setSort(v as typeof sort); handleFilterChange() }}>
          <SelectTrigger className="h-8 w-28 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="score">점수순</SelectItem>
            <SelectItem value="ai_score">AI점수순</SelectItem>
            <SelectItem value="newest">최신순</SelectItem>
          </SelectContent>
        </Select>
        {/* 오늘 수집 토글 칩 */}
        <button
          onClick={() => { setTodayOnly((v) => !v); handleFilterChange() }}
          className={`h-8 rounded-full border px-3 text-xs font-medium transition-colors ${
            todayOnly
              ? 'bg-blue-600 text-white border-blue-600'
              : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
          }`}
        >
          오늘 수집
        </button>
        {/* 추천만 토글 칩 */}
        <button
          onClick={() => { setRecommendedOnly((v) => !v); handleFilterChange() }}
          className={`h-8 rounded-full border px-3 text-xs font-medium transition-colors ${
            recommendedOnly
              ? 'bg-amber-500 text-white border-amber-500'
              : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
          }`}
        >
          ★ 추천만
        </button>
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
          {hasActiveFilters && (
            <Button
              size="sm"
              variant="ghost"
              className="h-8 px-2 text-xs text-gray-500"
              onClick={() => {
                setSiteFilter('all'); setTierFilter('all')
                setSearchInput(''); setActiveQ('')
                setSort('score'); setTodayOnly(false); setRecommendedOnly(false)
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
                  <th className="px-3 py-2 text-left w-8">
                    <input
                      type="checkbox"
                      onChange={(e) =>
                        e.target.checked && data ? useInboxStore.getState().selectAll(data.posts) : clearSelection()
                      }
                    />
                  </th>
                  <th className="px-3 py-2 text-left">제목</th>
                  <th className="px-3 py-2 text-left w-16">사이트</th>
                  <th className="px-3 py-2 text-right w-20">점수</th>
                  <th className="px-3 py-2 text-left w-16">티어</th>
                  <th className="px-3 py-2 text-center w-28">AI 적합도</th>
                  <th className="px-3 py-2 text-center w-40">액션</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data?.posts.map((post, idx) => {
                  const stats = (post.stats ?? {}) as PostStats
                  const imgCount = Array.isArray(post.images) ? post.images.length : 0
                  const isSelected = selectedIds.has(post.id)
                  const isActive = detailIdx === idx
                  return (
                    <tr
                      key={post.id}
                      ref={(el) => { if (el) rowRefs.current.set(post.id, el); else rowRefs.current.delete(post.id) }}
                      aria-selected={isActive}
                      className={`hover:bg-gray-50 transition-colors ${isActive ? 'bg-blue-50 ring-1 ring-inset ring-blue-200' : ''}`}
                    >
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(post.id)} />
                      </td>
                      <td className="px-3 py-2 max-w-md">
                        <button
                          onClick={() => setDetailIdx(idx)}
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
                      <td className="px-3 py-2 text-right">
                        <ScoreBreakdown post={post} />
                      </td>
                      <td className="px-3 py-2">{tierBadge(post.engagementScore)}</td>
                      <td className="px-3 py-2 text-center">
                        <AiFitnessBadge
                          post={post}
                          onAnalyzeRequest={() => handleAnalyzeRequest(post.id)}
                          isAnalyzing={analyzingIds.has(post.id)}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex justify-center gap-1">
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

      <TriageDrawer
        post={detail}
        posts={data?.posts ?? []}
        detailIdx={detailIdx}
        onClose={() => setDetailIdx(null)}
        onApprove={handleApprove}
        onDecline={handleDecline}
        onNavigate={setDetailIdx}
        onAnalyzeRequest={handleAnalyzeRequest}
        analyzingIds={analyzingIds}
      />
    </div>
  )
}
