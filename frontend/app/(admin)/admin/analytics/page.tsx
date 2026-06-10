'use client'
import { useEffect, useState } from 'react'
import { analyticsApi } from '@/lib/api/analytics'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'

function usePollJob() {
  const poll = (jobId: number, onDone: (result: unknown) => void, onError: () => void) => {
    const timer = setInterval(async () => {
      const job = await analyticsApi.pollJob(jobId)
      if (job.status === 'DONE') { clearInterval(timer); onDone(job.result) }
      if (job.status === 'ERROR') { clearInterval(timer); onError() }
    }, 2000)
  }
  return poll
}

export default function AnalyticsPage() {
  const [funnel, setFunnel] = useState<Record<string, number>>({})
  const [insightLoading, setInsightLoading] = useState(false)
  const [insightText, setInsightText] = useState('')
  const [abGroupId, setAbGroupId] = useState('')
  const [abLoading, setAbLoading] = useState(false)
  const [abResult, setAbResult] = useState('')
  const poll = usePollJob()

  useEffect(() => { analyticsApi.funnel().then(setFunnel) }, [])

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

      <AdminSection title="A/B 테스트">
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
            <p className="text-sm text-gray-400">
              config/ab_tests.json에서 Group ID를 확인하세요
            </p>
          )}
        </div>
      </AdminSection>
    </div>
  )
}
