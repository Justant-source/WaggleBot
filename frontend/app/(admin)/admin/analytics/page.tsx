'use client'
import { useEffect, useState } from 'react'
import { analyticsApi } from '@/lib/api/analytics'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminStatCard } from '@/components/admin/AdminStatCard'
import { Button } from '@/components/ui/button'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'

export default function AnalyticsPage() {
  const [funnel, setFunnel] = useState<Record<string, number>>({})
  const [insightJobId, setInsightJobId] = useState<number | null>(null)
  const [insightLoading, setInsightLoading] = useState(false)
  const [insightText, setInsightText] = useState('')

  useEffect(() => { analyticsApi.funnel().then(setFunnel) }, [])

  const funnelData = Object.entries(funnel).map(([name, value]) => ({ name: name.replace('_', ' '), value }))

  const handleInsights = async () => {
    setInsightLoading(true)
    const res = await analyticsApi.insights()
    setInsightJobId(res.jobId)
    const poll = setInterval(async () => {
      const job = await analyticsApi.pollJob(res.jobId)
      if (job.status === 'DONE') {
        setInsightText(JSON.stringify(job.result, null, 2))
        setInsightLoading(false); clearInterval(poll)
      }
      if (job.status === 'ERROR') { toast.error('인사이트 실패'); setInsightLoading(false); clearInterval(poll) }
    }, 2000)
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
            <Bar dataKey="value" fill="#3b82f6" radius={[4,4,0,0]} />
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
    </div>
  )
}
