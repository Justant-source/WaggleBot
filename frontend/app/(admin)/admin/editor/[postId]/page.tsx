'use client'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { editorApi } from '@/lib/api/editor'
import { Button } from '@/components/ui/button'
import { usePollingJob } from '@/lib/hooks/usePollingJob'
import { useEditorStore } from '@/lib/store/editorStore'
import type { ScriptData } from '@/lib/types'
import { Loader2, Save, CheckCircle, Play } from 'lucide-react'

export default function EditorDetailPage({ params }: { params: { postId: string } }) {
  const id = Number(params.postId)
  const [loading, setLoading] = useState(true)
  const [post, setPost] = useState<{ title: string } | null>(null)
  const [generateJobId, setGenerateJobId] = useState<number | null>(null)
  const [ttsJobId, setTtsJobId] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const { script, dirty, setScript, updateField, markClean } = useEditorStore()

  const genJob = usePollingJob(generateJobId, (jid) => editorApi.pollJob(jid))
  const ttsJob = usePollingJob(ttsJobId, (jid) => editorApi.pollJob(jid))

  useEffect(() => {
    editorApi.get(id).then((res) => {
      setPost({ title: res.post.title })
      if (res.script) setScript(res.script)
      setLoading(false)
    })
  }, [id])

  useEffect(() => {
    if (genJob.status === 'DONE') {
      const scriptJson = genJob.result?.script_json as string
      if (scriptJson) try { setScript(JSON.parse(scriptJson)) } catch {}
      toast.success('대본 생성 완료')
    }
    if (genJob.status === 'ERROR') toast.error('대본 생성 실패')
  }, [genJob.status])

  useEffect(() => {
    if (ttsJob.status === 'DONE') {
      const path = ttsJob.result?.preview_path as string
      if (path && audioRef.current) {
        audioRef.current.src = `/media/tmp/preview_${id}.mp3?t=${Date.now()}`
        audioRef.current.play()
      }
      toast.success('TTS 미리듣기 준비 완료')
    }
  }, [ttsJob.status])

  const handleSave = async () => {
    if (!script) return
    await editorApi.saveScript(id, script)
    markClean(); toast.success('저장됨')
  }

  const handleGenerate = async () => {
    const res = await editorApi.generate(id)
    setGenerateJobId(res.jobId); toast.info('대본 생성 중...')
  }

  const handleTtsPreview = async () => {
    const res = await editorApi.ttsPreview(id)
    setTtsJobId(res.jobId); toast.info('TTS 생성 중...')
  }

  const handleConfirm = async () => {
    await editorApi.confirm(id)
    toast.success('확정됨 — APPROVED 상태로 전환')
  }

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>

  return (
    <div className="max-w-2xl">
      <h1 className="mb-2 text-xl font-semibold text-gray-900">{post?.title}</h1>
      <div className="mb-4 flex gap-2">
        <Button size="sm" variant="outline" onClick={handleGenerate} disabled={genJob.isPolling}>
          {genJob.isPolling ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null} AI 대본 생성
        </Button>
        <Button size="sm" variant="outline" onClick={handleTtsPreview} disabled={ttsJob.isPolling}>
          {ttsJob.isPolling ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Play className="mr-1 h-4 w-4" />} TTS 미리듣기
        </Button>
        <Button size="sm" variant="outline" onClick={handleSave} disabled={!dirty}>
          <Save className="mr-1 h-4 w-4" /> 저장
        </Button>
        <Button size="sm" onClick={handleConfirm}>
          <CheckCircle className="mr-1 h-4 w-4" /> 확정
        </Button>
      </div>
      <audio ref={audioRef} controls className="mb-4 w-full" />
      {script && (
        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <div>
            <label className="text-xs font-medium text-gray-500">Hook</label>
            <textarea
              className="mt-1 w-full rounded border border-gray-200 p-2 text-sm"
              rows={2}
              value={script.hook}
              onChange={(e) => updateField('hook', e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500">Closer</label>
            <textarea
              className="mt-1 w-full rounded border border-gray-200 p-2 text-sm"
              rows={2}
              value={script.closer}
              onChange={(e) => updateField('closer', e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500">Mood</label>
            <input className="mt-1 w-full rounded border border-gray-200 p-2 text-sm" value={script.mood} onChange={(e) => updateField('mood', e.target.value)} />
          </div>
        </div>
      )}
    </div>
  )
}
