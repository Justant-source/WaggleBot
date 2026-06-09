'use client'
import { useEffect, useState } from 'react'
import { llmLogsApi } from '@/lib/api/llmLogs'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Badge } from '@/components/ui/badge'
import type { LlmLog } from '@/lib/types'
import { Loader2 } from 'lucide-react'

export default function LlmLogsPage() {
  const [logs, setLogs] = useState<LlmLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    llmLogsApi.list({ page, size: 20 }).then((res) => {
      setLogs(res.content); setTotal(res.totalElements)
    }).finally(() => setLoading(false))
  }, [page])

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">LLM 이력</h1>
      <AdminSection title={`총 ${total}건`}>
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">callType</th>
                  <th className="px-3 py-2 text-left">모델</th>
                  <th className="px-3 py-2 text-right">시간(ms)</th>
                  <th className="px-3 py-2 text-center">성공</th>
                  <th className="px-3 py-2 text-left">생성일</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-mono text-xs">{log.callType}</td>
                    <td className="px-3 py-2 text-gray-500 text-xs">{log.modelName ?? '-'}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{log.durationMs ?? '-'}</td>
                    <td className="px-3 py-2 text-center">
                      <Badge variant={log.success ? 'success' : 'destructive'}>
                        {log.success ? '성공' : '실패'}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{new Date(log.createdAt).toLocaleString('ko-KR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 py-3">
              <AdminPagination page={page} totalPages={Math.ceil(total / 20)} onPageChange={setPage} />
            </div>
          </div>
        )}
      </AdminSection>
    </div>
  )
}
