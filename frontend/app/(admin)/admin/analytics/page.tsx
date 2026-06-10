'use client'
import { useEffect, useRef, useState } from 'react'
import { analyticsApi, PerformanceRow } from '@/lib/api/analytics'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { toast } from 'sonner'
import { Loader2, RefreshCw } from 'lucide-react'

const PRESETS = [
  { value: 'hook_question',    label: '의문형 후킹' },
  { value: 'hook_exclamation', label: '감탄형 후킹' },
  { value: 'body_short',       label: '짧은 body' },
  { value: 'body_narrative',   label: '서사형 body' },
  { value: 'tone_formal',      label: '뉴스 말투' },
  { value: 'tone_casual',      label: '구어 말투' },
]

function usePollJob() {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => () => { if (timerRef.current !== null) clearInterval(timerRef.current) }, [])
  return (jobId: number, onDone: (r: unknown) => void, onError: () => void) => {
    if (timerRef.current !== null) clearInterval(timerRef.current)
    timerRef.current = setInterval(async () => {
      try {
        const job = await analyticsApi.pollJob(jobId)
        if (job.status === 'DONE') { clearInterval(timerRef.current!); timerRef.current = null; onDone(job.result) }
        if (job.status === 'ERROR') { clearInterval(timerRef.current!); timerRef.current = null; onError() }
      } catch { clearInterval(timerRef.current!); timerRef.current = null; onError() }
    }, 2000)
  }
}

export default function AnalyticsPage() {
  const [funnel, setFunnel] = useState<Record<string, number>>({})
  const [perf, setPerf] = useState<PerformanceRow[]>([])
  const [perfLoading, setPerfLoading] = useState(false)
  const [insightLoading, setInsightLoading] = useState(false)
  const [insightText, setInsightText] = useState('')
  // A/B 생성
  const [abName, setAbName] = useState('')
  const [abPresetA, setAbPresetA] = useState('hook_question')
  const [abPresetB, setAbPresetB] = useState('hook_exclamation')
  const [abCreateLoading, setAbCreateLoading] = useState(false)
  const [abCreateResult, setAbCreateResult] = useState('')
  // A/B 평가
  const [abGroupId, setAbGroupId] = useState('')
  const [abLoading, setAbLoading] = useState(false)
  const [abResult, setAbResult] = useState('')
  const poll = usePollJob()

  useEffect(() => { analyticsApi.funnel().then(setFunnel) }, [])

  const loadPerf = async () => {
    setPerfLoading(true)
    try { setPerf(await analyticsApi.performance()) }
    catch { toast.error('성과 데이터 로드 실패') }
    finally { setPerfLoading(false) }
  }
  useEffect(() => { loadPerf() }, [])

  const funnelData = Object.entries(funnel).map(([name, value]) => ({
    name: name.replace(/_/g, ' '),
    value,
  }))

  const handleInsights = async () => {
    setInsightLoading(true)
    try {
      const res = await analyticsApi.insights()
      poll(res.jobId,
        (r) => { setInsightText(JSON.stringify(r, null, 2)); setInsightLoading(false) },
        () => { toast.error('인사이트 실패'); setInsightLoading(false) },
      )
    } catch { toast.error('요청 실패'); setInsightLoading(false) }
  }

  const handleAbCreate = async () => {
    if (!abName.trim()) { toast.error('테스트 이름을 입력하세요'); return }
    if (abPresetA === abPresetB) { toast.error('A와 B는 다른 프리셋이어야 합니다'); return }
    setAbCreateLoading(true)
    setAbCreateResult('')
    try {
      const res = await analyticsApi.abCreate(abName.trim(), abPresetA, abPresetB)
      poll(res.jobId,
        (r) => {
          const result = r as { group_id: string }
          setAbCreateResult(`생성됨: ${result.group_id}`)
          setAbGroupId(result.group_id)
          setAbName('')
          setAbCreateLoading(false)
          toast.success('A/B 테스트 생성됨')
        },
        () => { toast.error('생성 실패'); setAbCreateLoading(false) },
      )
    } catch { toast.error('요청 실패'); setAbCreateLoading(false) }
  }

  const handleAbAction = async (action: 'evaluate' | 'apply') => {
    if (!abGroupId.trim()) { toast.error('Group ID를 입력하세요'); return }
    setAbLoading(true)
    setAbResult('')
    try {
      const res = action === 'evaluate'
        ? await analyticsApi.abEvaluate(abGroupId.trim())
        : await analyticsApi.abApplyWinner(abGroupId.trim())
      poll(res.jobId,
        (r) => { setAbResult(JSON.stringify(r, null, 2)); setAbLoading(false); toast.success(action === 'evaluate' ? '평가 완료' : '승자 반영 완료') },
        () => { toast.error('작업 실패'); setAbLoading(false) },
      )
    } catch { toast.error('요청 실패'); setAbLoading(false) }
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">분석</h1>

      <AdminSection title="파이프라인 퍼널">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={funnelData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </AdminSection>

      <AdminSection title="YouTube 성과" action={
        <Button size="sm" variant="outline" onClick={loadPerf} disabled={perfLoading}>
          {perfLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      }>
        {perf.length === 0 ? (
          <p className="text-sm text-gray-400">업로드된 영상 없음 (UPLOADED 상태 게시글 필요)</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-gray-500">
                  <th className="pb-2 pr-4 font-medium">제목</th>
                  <th className="pb-2 pr-4 font-medium text-right">조회수</th>
                  <th className="pb-2 pr-4 font-medium text-right">좋아요</th>
                  <th className="pb-2 font-medium text-right">댓글</th>
                </tr>
              </thead>
              <tbody>
                {perf.map((row) => (
                  <tr key={row.postId} className="border-b last:border-0">
                    <td className="py-2 pr-4 max-w-xs truncate" title={row.title}>
                      {row.videoId ? (
                        <a
                          href={`https://youtube.com/watch?v=${row.videoId}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {row.title}
                        </a>
                      ) : row.title}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">{row.analytics.views.toLocaleString()}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{row.analytics.likes.toLocaleString()}</td>
                    <td className="py-2 text-right tabular-nums">{row.analytics.comments.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AdminSection>

      <AdminSection title="AI 인사이트" action={
        <Button size="sm" onClick={handleInsights} disabled={insightLoading}>
          {insightLoading && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} 인사이트 생성
        </Button>
      }>
        {insightText ? (
          <pre className="rounded bg-gray-50 p-3 text-xs overflow-auto max-h-64">{insightText}</pre>
        ) : (
          <p className="text-sm text-gray-400">인사이트 생성 버튼을 클릭하세요</p>
        )}
      </AdminSection>

      <AdminSection title="A/B 테스트 생성">
        <div className="max-w-lg space-y-3">
          <Input
            placeholder="테스트 이름 (예: hook 스타일 실험 2026-06)"
            value={abName}
            onChange={(e) => setAbName(e.target.value)}
          />
          <div className="flex gap-2">
            <div className="flex-1">
              <p className="mb-1 text-xs text-gray-500">변형 A</p>
              <Select value={abPresetA} onValueChange={setAbPresetA}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PRESETS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <p className="mb-1 text-xs text-gray-500">변형 B</p>
              <Select value={abPresetB} onValueChange={setAbPresetB}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PRESETS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button size="sm" onClick={handleAbCreate} disabled={abCreateLoading}>
            {abCreateLoading && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} 테스트 생성
          </Button>
          {abCreateResult && <p className="text-xs text-green-600">{abCreateResult}</p>}
        </div>
      </AdminSection>

      <AdminSection title="A/B 테스트 평가">
        <div className="max-w-lg space-y-3">
          <div className="flex gap-2">
            <Input
              className="flex-1"
              placeholder="Group ID (예: ab_3f2a1b4c)"
              value={abGroupId}
              onChange={(e) => setAbGroupId(e.target.value)}
            />
            <Button size="sm" variant="outline" onClick={() => handleAbAction('evaluate')} disabled={abLoading}>
              {abLoading && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} 평가 실행
            </Button>
            <Button size="sm" onClick={() => handleAbAction('apply')} disabled={abLoading}>
              승자 반영
            </Button>
          </div>
          {abResult ? (
            <pre className="rounded bg-gray-50 p-3 text-xs overflow-auto max-h-40">{abResult}</pre>
          ) : (
            <p className="text-sm text-gray-400">테스트 생성 후 Group ID가 자동 입력됩니다</p>
          )}
        </div>
      </AdminSection>
    </div>
  )
}
