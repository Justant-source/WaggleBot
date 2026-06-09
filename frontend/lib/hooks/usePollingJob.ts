'use client'
import { useEffect, useRef, useState } from 'react'
import type { Job, JobStatus } from '@/lib/types'

interface PollingState {
  status: JobStatus | null
  result: Record<string, unknown> | null
  error: string | null
  isPolling: boolean
}

type FetchFn = (jobId: number) => Promise<Job>

export function usePollingJob(jobId: number | null, fetchFn: FetchFn, intervalMs = 2000): PollingState {
  const [state, setState] = useState<PollingState>({
    status: null, result: null, error: null, isPolling: false,
  })
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return
    setState((s) => ({ ...s, isPolling: true }))

    const poll = async () => {
      try {
        const job = await fetchFn(jobId)
        setState({ status: job.status, result: job.result, error: job.error, isPolling: job.status === 'PENDING' || job.status === 'RUNNING' })
        if (job.status === 'DONE' || job.status === 'ERROR') {
          if (timerRef.current) clearInterval(timerRef.current)
        }
      } catch (e) {
        setState({ status: 'ERROR', result: null, error: String(e), isPolling: false })
        if (timerRef.current) clearInterval(timerRef.current)
      }
    }

    poll()
    timerRef.current = setInterval(poll, intervalMs)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [jobId])

  return state
}
