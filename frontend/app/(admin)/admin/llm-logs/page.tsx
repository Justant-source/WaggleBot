'use client'
import { useEffect, useState } from 'react'
import { llmLogsApi } from '@/lib/api/llmLogs'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { LlmLog } from '@/lib/types'
import { Loader2, ChevronDown, ChevronUp } from 'lucide-react'

const CALL_TYPES = [
  'chunk', 'generate_script', 'scene_director', 'video_prompt',
  'translate', 'comment_summarize', 'feedback',
]

function LogRow({ log }: { log: LlmLog }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetail = log.promptText || log.rawResponse

  return (
    <>
      <tr
        className={`hover:bg-gray-50 ${hasDetail ? 'cursor-pointer' : ''}`}
        onClick={() => hasDetail && setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 font-mono text-xs">{log.callType}</td>
        <td className="px-3 py-2 text-gray-500 text-xs">{log.modelName ?? '-'}</td>
        <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">{log.durationMs ?? '-'}</td>
        <td className="px-3 py-2 text-center">
          <Badge variant={log.success ? 'success' : 'destructive'}>
            {log.success ? '성공' : '실패'}
          </Badge>
        </td>
        <td className="px-3 py-2 text-gray-400 text-xs">{new Date(log.createdAt).toLocaleString('ko-KR')}</td>
        <td className="px-3 py-2 text-gray-300 w-6">
          {hasDetail && (expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={6} className="px-3 py-3">
            {log.errorMessage && (
              <pre className="mb-2 max-h-24 overflow-auto whitespace-pre-wrap break-all rounded bg-red-50 p-2 text-xs text-red-700">
                {log.errorMessage}
              </pre>
            )}
            {log.promptText && (
              <details className="mb-2">
                <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-700">프롬프트</summary>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-white p-2 text-xs text-gray-700 border border-gray-100">
                  {log.promptText}
                </pre>
              </details>
            )}
            {log.rawResponse && (
              <details>
                <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-700">응답</summary>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-white p-2 text-xs text-gray-700 border border-gray-100">
                  {log.rawResponse}
                </pre>
              </details>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function LlmLogsPage() {
  const [logs, setLogs] = useState<LlmLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [callTypeFilter, setCallTypeFilter] = useState<string>('all')
  const [successFilter, setSuccessFilter] = useState<string>('all')

  useEffect(() => {
    setLoading(true)
    setPage(0)
  }, [callTypeFilter, successFilter])

  useEffect(() => {
    setLoading(true)
    llmLogsApi.list({
      page,
      size: 20,
      callType: callTypeFilter !== 'all' ? callTypeFilter : undefined,
      success: successFilter !== 'all' ? successFilter === 'true' : undefined,
    }).then((res) => {
      setLogs(res.content); setTotal(res.totalElements)
    }).finally(() => setLoading(false))
  }, [page, callTypeFilter, successFilter])

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">LLM 이력</h1>
      <AdminSection title={`총 ${total}건`} action={
        <div className="flex gap-2">
          <Select value={callTypeFilter} onValueChange={setCallTypeFilter}>
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue placeholder="callType 필터" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">전체 callType</SelectItem>
              {CALL_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={successFilter} onValueChange={setSuccessFilter}>
            <SelectTrigger className="h-8 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">전체</SelectItem>
              <SelectItem value="true">성공만</SelectItem>
              <SelectItem value="false">실패만</SelectItem>
            </SelectContent>
          </Select>
        </div>
      }>
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
                  <th className="w-6" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {logs.map((log) => <LogRow key={log.id} log={log} />)}
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
